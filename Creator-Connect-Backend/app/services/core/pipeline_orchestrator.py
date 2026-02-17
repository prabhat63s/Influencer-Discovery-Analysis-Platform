from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from app.services.reporting.monitoring_service import SearchMetrics, monitoring
from app.services.scrapers.spreadd_service import run_spreadd_parallel as _run_spreadd_parallel
from app.services.scrapers.search_scrapers import discover_influencers_from_prompt
from app.services.scrapers.brightdata_scraper import scraper_b_csv_brightdata
from app.models.exceptions import PipelineError, ValidationError
from app.services.core.persistence_service import InfluencerPersistenceService
from app.services.core.search_filters import (
    sort_results_by_relevance,
    remove_duplicates,
    merge_results,
    parse_rate_to_int,
    calculate_rate,
)

# Import dependencies
import os
import json
from dotenv import load_dotenv
from app.config.settings import settings
from app.services.llm.gemini_utils import parse_query_with_gemini

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env")

SERP_API_KEY = settings.SERP_API_KEY

logger = logging.getLogger(__name__)


# ============================================================================
# HELPER: LOAD CSV
# ============================================================================

def load_influencers_from_csv(csv_path: str, max_count: Optional[int] = None) -> List[Dict[str, str]]:
    """Load influencers from CSV file"""
    import pandas as pd

    logger.info(f"Loading influencers from CSV: {csv_path}")

    try:
        df = pd.read_csv(csv_path)

        if max_count:
            df = df.head(max_count)

        influencers = df.to_dict('records')
        logger.info(f"✅ Loaded {len(influencers)} influencers from CSV")
        return influencers

    except Exception as e:
        logger.error(f"Failed to load CSV: {e}")
        return []


# ============================================================================
# ENHANCED MAIN PIPELINE WITH COMPREHENSIVE MONITORING (calculate_rate from search_filters)
# ============================================================================

async def run_async_pipeline(
    user_query: str,
    csv_path: Optional[str] = None,
    influencers: Optional[List[Dict[str, str]]] = None,
    skip_analysis: bool = False,
    conversation_id: Optional[str] = None,
    direct_link_mode: bool = False,
    override_num_results: Optional[int] = None,
) -> Tuple[List[Dict], SearchMetrics]:
    """
    Pipeline: discovery, enrichment, merge/dedup, sort by relevance.
    direct_link_mode: use only provided influencers and exact username match (e.g. direct link search).
    override_num_results: when set (e.g. for partial-match remainder), cap discovery and return to this many.
    """
    # Initialize metrics
    if not conversation_id:
        conversation_id = f"conv_{int(time.time())}"

    metrics = monitoring.get_metrics(conversation_id)
    metrics.query = user_query
    metrics.timestamp = datetime.now().isoformat()

    pipeline_start = time.time()

    logger.info("\n" + "="*80)
    logger.info("🚀 PRODUCTION-GRADE PIPELINE")
    logger.info("="*80)
    logger.info(f"Conversation ID: {conversation_id}")
    logger.info(f"Query: {user_query}")

    try:
        # ============================================================
        # 1. PARSE QUERY
        # ============================================================
        # Skip parsing for direct link searches
        if user_query == "DIRECT_LINK_SEARCH" and influencers is not None:
            logger.info(f"\n📊 DIRECT LINK SEARCH MODE:")
            logger.info(f"   • Skipping query parsing")
            logger.info(f"   • Using {len(influencers)} pre-selected profiles")

            # Create minimal parsed_query for direct link search
            parsed_query = {
                'num_results': len(influencers),  # Return all provided profiles
                'niche': 'Direct Link Search',
                'location': 'N/A',
                'min_followers': None,
                'max_followers': None,
                'search_queries': [],
                'original_query': user_query
            }
            num_requested = len(influencers)

        else:
            # Normal query parsing
            parsed_query = parse_query_with_gemini(user_query, metrics)
            # Default to 500 to return more results by default
            num_requested = parsed_query.get('num_results', 500)
            if override_num_results is not None:
                num_requested = min(num_requested, max(1, override_num_results))
                parsed_query['num_results'] = num_requested
                logger.info(f"   • Override: returning at most {num_requested} (partial-match remainder)")

            # CRITICAL: Log the extracted num_results
            logger.info(f"\n📊 PARSED PARAMETERS:")
            logger.info(f"   • Requested results: {num_requested} (MUST return this many)")
            logger.info(f"   • Niche: {parsed_query['niche']}")
            logger.info(f"   • Location: {parsed_query['location']}")
            if parsed_query.get('min_followers'):
                logger.info(f"   • Min followers: {parsed_query['min_followers']:,}")
            if parsed_query.get('max_followers'):
                logger.info(f"   • Max followers: {parsed_query['max_followers']:,}")

        # ============================================================
        # 2. GET INFLUENCERS (Discovery or CSV)
        # ============================================================
        if influencers is not None:
            logger.info(f"\n📂 Using {len(influencers)} pre-loaded influencers")
            metrics.total_influencers_discovered = len(influencers)
        elif csv_path is not None:
            logger.info(f"\n📂 Loading influencers from CSV: {csv_path}")
            influencers = load_influencers_from_csv(csv_path, max_count=None)
            if not influencers:
                logger.error("❌ CSV file contained no valid influencers")
                metrics.add_error("CSV file empty or invalid")
                metrics.total_time_seconds = time.time() - pipeline_start
                return [], metrics
            metrics.total_influencers_discovered = len(influencers)
        else:
            # ============================================================
            # HYBRID DISCOVERY: Multiple passes with different strategies
            # ============================================================
            logger.info(f"\n🔍 HYBRID DISCOVERY: Multiple discovery passes...")
            
            MAX_PASSES = 2
            all_results = []
            pass_number = 1
            
            while pass_number <= MAX_PASSES:
                parsed_query["discovery_mode"] = (
                    "numeric" if pass_number == 1 else "authority"
                )
                
                # Regenerate search queries for current discovery mode
                from app.services.core.discovery_service import _generate_fallback_search_queries
                parsed_query['search_queries'] = _generate_fallback_search_queries(parsed_query)
                
                logger.info(f"\n🔁 Hybrid Discovery Pass {pass_number}/{MAX_PASSES} ({parsed_query['discovery_mode']} mode)")
                logger.info(f"   Using {len(parsed_query['search_queries'])} search queries")
                
                # Discover influencers with current mode
                discovered = await discover_influencers_from_prompt(parsed_query)
                if discovered:
                    logger.info(f"   ✅ Pass {pass_number}: Discovered {len(discovered)} profiles")
                    all_results.extend(discovered)
                    
                    # Check if we have enough discovered profiles (before scraping)
                    if len(all_results) >= num_requested * 2:
                        logger.info(f"   Sufficient profiles discovered ({len(all_results)} >= {num_requested * 2})")
                        break
                else:
                    logger.info(f"   ⚠️ Pass {pass_number}: No profiles discovered")
                
                pass_number += 1
            
            influencers = all_results
            if not influencers:
                logger.error("❌ No influencers discovered after all passes")
                metrics.add_error("Discovery returned 0 results after hybrid search")
                metrics.total_time_seconds = time.time() - pipeline_start
                return [], metrics
            metrics.total_influencers_discovered = len(influencers)

        logger.info(f"✅ Starting with {len(influencers)} influencers")

        # ============================================================
        # 3. RUN SCRAPERS (Enrichment) - WITH PRIORITIZATION
        # ============================================================
        logger.info(f"\n🔄 SCRAPING & ENRICHMENT...")
        scrape_start = time.time()

        # SMART DISCOVERY: Sort influencers by discovery quality score before scraping
        # Scrape high-quality profiles first for faster convergence
        if influencers and isinstance(influencers[0], dict) and 'discovery_quality_score' in influencers[0]:
            influencers_sorted = sorted(
                influencers,
                key=lambda x: x.get('discovery_quality_score', 0),
                reverse=True  # Highest quality first
            )
            logger.info(f"📊 Prioritized {len(influencers)} profiles by discovery quality")
            logger.info(f"   Top profile: @{influencers_sorted[0].get('username')} (score: {influencers_sorted[0].get('discovery_quality_score', 0)})")
            if len(influencers_sorted) > 1:
                logger.info(f"   Lowest profile: @{influencers_sorted[-1].get('username')} (score: {influencers_sorted[-1].get('discovery_quality_score', 0)})")
        else:
            influencers_sorted = influencers
            logger.debug("No discovery quality scores found, using original order")

        # Flow: Discovery (SerpAPI) → BrightData only → merge; no per-profile SerpAPI enrichment
        scraper_a_results = []  # Skip SerpAPI enrichment; go directly to BrightData after discovery

        scraper_b_results = []
        if influencers_sorted:
            logger.info("="*70)
            logger.info(f"🔄 BRIGHTDATA: Starting enrichment for {len(influencers_sorted)} profile(s)")
            logger.info("="*70)
            loop = asyncio.get_event_loop()
            scraper_b_task = loop.run_in_executor(
                None, scraper_b_csv_brightdata, influencers_sorted, parsed_query, True  # skip_ai_processing=True
            )
            try:
                scraper_b_results = await scraper_b_task
            except Exception as e:
                logger.error(f"❌ BRIGHTDATA: Exception - {type(e).__name__}: {str(e)}")
                metrics.add_error(f"Scraper B failed: {e}")
                scraper_b_results = []
            if isinstance(scraper_b_results, Exception):
                logger.error(f"❌ BRIGHTDATA: Task returned exception")
                scraper_b_results = []
            elif scraper_b_results:
                logger.info(f"✅ BRIGHTDATA: Successfully enriched {len(scraper_b_results)} profile(s)")
            else:
                logger.warning(f"⚠️ BRIGHTDATA: No results returned (will use SerpAPI data only)")

        metrics.scraping_time_seconds = time.time() - scrape_start
        logger.info(f"✅ BrightData completed: {len(scraper_b_results)} profile(s)")

        # ============================================================
        # 4. MERGE & DEDUPLICATE
        # ============================================================
        logger.info(f"\n🔄 MERGING & DEDUPLICATION...")
        merged_results = merge_results(scraper_a_results, scraper_b_results, [])

        if len(merged_results) == 0:
            logger.warning("⚠️ No results after merging")
            metrics.add_warning("Merge returned 0 results")
            metrics.total_time_seconds = time.time() - pipeline_start
            return [], metrics

        logger.info(f"   • Merged: {len(merged_results)} results")
        unique_results = remove_duplicates(merged_results)
        metrics.total_influencers_after_dedup = len(unique_results)
        logger.info(f"   • After dedup: {len(unique_results)} unique results")

        # Spreadd (authenticity) runs in BACKGROUND – UI shows BrightData first
        logger.info("🔄 Scheduling Spreadd (authenticity) in background...")
        try:
            loop = asyncio.get_event_loop()
            loop.create_task(_run_spreadd_parallel(unique_results, metrics))
        except Exception as e:
            logger.warning(f"⚠️ Could not start Spreadd background task: {e}")

        # ============================================================
        # 5. SORT BY RELEVANCE (BrightData-only; no Spreadd wait)
        # ============================================================
        logger.info(f"\nSort: {len(unique_results)} profiles")
        sorted_results = sort_results_by_relevance(unique_results, parsed_query, metrics)
        logger.info(f"   Sorted: {len(sorted_results)} results")

        # ============================================================
        # 6. FINAL SELECTION – Return ALL enriched profiles (no cap)
        # ============================================================
        logger.info(f"\n📊 FINAL SELECTION...")
        
        if len(sorted_results) == 0:
            logger.error("No results after sort")
            metrics.add_error("Zero results after sort")
            metrics.influencers_returned = 0
            metrics.total_time_seconds = time.time() - pipeline_start

            return [], metrics

        is_direct_username_search = (
            user_query == "DIRECT_LINK_SEARCH" or 
            (influencers is not None and len(influencers) == 1) or
            (direct_link_mode and influencers is not None)
        )
        
        if is_direct_username_search and influencers and len(influencers) == 1:
            # Single username: return exact match only
            target_username = influencers[0].get("username") or influencers[0].get("Id") or influencers[0].get("name", "").lower()
            exact_matches = []
            for result in sorted_results:
                result_username = (
                    result.get("username") or 
                    result.get("Id") or 
                    result.get("NAME", "") or 
                    result.get("name", "")
                ).lower()
                if result_username == target_username:
                    exact_matches.append(result)
            
            if exact_matches:
                final_results = exact_matches[:1]  # Return only the exact match
                logger.info(f"✅ Direct username search: Returning EXACT match for @{target_username}")
            else:
                # Fallback: return first result if exact match not found
                final_results = sorted_results[:1]
                logger.warning(f"⚠️ Exact username match not found, returning first result")
        else:
            # Return all enriched profiles; cap when override_num_results set (e.g. partial-match remainder)
            final_results = sorted_results
            if override_num_results is not None and len(final_results) > override_num_results:
                final_results = final_results[:override_num_results]
                logger.info(f"✅ Returning {len(final_results)} enriched profiles (capped for partial-match)")
            else:
                logger.info(f"✅ Returning all {len(final_results)} enriched profiles (BrightData)")
        
        # AI processing skipped before return – UI shows BrightData first; can run in background if needed
        
        # Log what we're returning
        logger.info(f"✅ Returning {len(final_results)} results (all enriched profiles)")

        # ========================================================================
        # OPTIMIZED INDUSTRY STANDARDS: Discover peers EARLY, enrich in PARALLEL
        # ========================================================================
        # CRITICAL: Skip industry standards for:
        # 1. Direct username/link searches
        # 2. Top 3/5 searches (they use internal comparison, not external industry peers)
        # Industry standards should ONLY run for single profile searches (len == 1)
        is_direct_username_search = (
            user_query == "DIRECT_LINK_SEARCH" or 
            (influencers is not None and len(influencers) == 1) or
            (direct_link_mode and influencers is not None)
        )
        
        # CRITICAL: Only run industry standards for single profile searches
        is_single_profile_search = len(final_results) == 1
        
        industry_peers = []
        if final_results and not is_direct_username_search and is_single_profile_search:
            try:
                from app.services.analysis.industry_standards import (
                    ENABLE_INDUSTRY_STANDARDS,
                    discover_industry_peers_early,
                    apply_follower_constraint,
                    rank_peers
                )
                from app.services.core.search_filters import parse_followers_to_int
                from app.services.scrapers.search_scrapers import scraper_a_serpapi_spreadd
                
                if ENABLE_INDUSTRY_STANDARDS:
                    anchor = final_results[0]
                    
                    # STEP 1: Discover peer usernames EARLY (OpenAI only, ~300-500ms)
                    logger.info("🔄 Starting early industry peer discovery...")
                    peer_influencers = await discover_industry_peers_early(anchor, parsed_query)
                    
                    if peer_influencers:
                        logger.info(f"✅ Discovered {len(peer_influencers)} industry peer usernames")
                        
                        # STEP 2: Enrich peers ONLY in parallel (anchor already enriched)
                        logger.info(f"🔄 Enriching {len(peer_influencers)} industry peers in parallel...")
                        
                        # Create scraping query for peers
                        scraping_query = parsed_query.copy()
                        profession = peer_influencers[0].get("_industry_profession", "")
                        if profession:
                            scraping_query["niche"] = profession
                        scraping_query["location"] = "Global"
                        
                        # Run enrichment in parallel (only for peers)
                        enriched_peers = await scraper_a_serpapi_spreadd(peer_influencers, scraping_query)
                        
                        if enriched_peers:
                            # STEP 3: Apply follower constraint
                            anchor_followers = parse_followers_to_int(anchor.get("followers", "0"))
                            filtered_peers = apply_follower_constraint(enriched_peers, anchor_followers)
                            
                            if filtered_peers:
                                # STEP 4: Rank and select top 2-3
                                ranked_peers = rank_peers(filtered_peers)
                                
                                # STEP 5: Tag peers
                                for peer in ranked_peers:
                                    peer["industry_standard"] = True
                                    peer["industry_profession"] = profession
                                    peer["industry_reference_for"] = anchor.get("Id") or anchor.get("username", "")
                                    peer["industry_anchor"] = False  # Mark as peer
                                
                                industry_peers = ranked_peers
                                logger.info(f"✅ Industry standards complete: {len(industry_peers)} peers ready")
                            else:
                                logger.info("ℹ️ No peers passed follower constraint")
                        else:
                            logger.warning("⚠️ Peer enrichment returned no results")
                    else:
                        logger.info("ℹ️ No industry peers discovered")
                        
            except Exception as e:
                logger.warning(f"⚠️ Industry standards discovery failed (non-blocking): {e}")
                import traceback
                logger.debug(traceback.format_exc())
                # Continue without industry peers - not a critical failure
        
        # Tag anchor
        if final_results:
            final_results[0]["industry_anchor"] = True
            if industry_peers:
                final_results[0]["industry_profession"] = industry_peers[0].get("industry_profession", "")
        
        # Combine anchor + peers for response
        # CRITICAL: For direct username searches, return ONLY the exact match (no peers, no extra results)
        if is_direct_username_search:
            final_results_with_peers = final_results  # Return only the exact username match
            logger.info(f"✅ Direct username search: Returning ONLY exact match (no industry peers, no extra results)")
        elif industry_peers:
            # Insert peers after anchor in final_results
            final_results_with_peers = [final_results[0]] + industry_peers + final_results[1:]
            logger.info(f"✅ Final results: 1 anchor + {len(industry_peers)} industry peers + {len(final_results)-1} other results")
        else:
            final_results_with_peers = final_results

        # ============================================================
        # PROFESSION PEERS FOR TOP SEARCHES (BACKGROUND TASK)
        # ============================================================
        # For top N searches (2-5 results) where we don't have industry peers,
        # trigger background discovery of "Profession Peers" (5x followers)
        is_top_search = len(final_results) >= 2 and len(final_results) <= 5
        if is_top_search and not is_direct_username_search and final_results:
            try:
                from app.services.analysis.industry_standards import start_profession_peers_background
                
                # Use first result as anchor
                anchor_for_peer_discovery = final_results[0]
                
                # Start background task (fire and forget)
                loop = asyncio.get_event_loop()
                loop.create_task(
                    start_profession_peers_background(
                        anchor=anchor_for_peer_discovery,
                        parsed_query=parsed_query,
                        conversation_id=conversation_id,
                        follower_multiplier=5.0  # 5x followers target
                    )
                )
                logger.info(f"🚀 Triggered background profession peers discovery for {conversation_id}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to trigger profession peers background task: {e}")


        metrics.influencers_returned = len(final_results_with_peers)
        metrics.total_time_seconds = time.time() - pipeline_start

        # ============================================================
        # 7. SAVE & LOG SUMMARY
        # ============================================================
        
        # 7a. Persist to Living Database (workflow: auto-save after pipeline)
        if final_results_with_peers:
            logger.info("Persisting %s influencers to Living Database...", len(final_results_with_peers))
            try:
                # DEBUG: Trace persistence
                logger.debug("Calling InfluencerPersistenceService.bulk_save_influencers...")
                saved_count = await InfluencerPersistenceService.bulk_save_influencers(final_results_with_peers)
                logger.info("Database updated: %s records saved/updated", saved_count)
            except (ValidationError, PipelineError) as e:
                logger.warning("Database persistence failed: code=%s message=%s", e.code, e.message)
                metrics.add_warning("Database save failed")
            except Exception as e:
                logger.exception("Database persistence error: %s", type(e).__name__)
                metrics.add_warning("Database save failed")
        else:
            logger.warning("No results to persist to Living Database (final_results_with_peers is empty)")

        # Save for persistence (save final_results_with_peers to include industry peers)
        try:
            from app.services.core.prompt_service import persist_dynamic_results
            persist_dynamic_results(conversation_id, final_results_with_peers)
        except ImportError:
            logger.warning("⚠️ Could not import persist_dynamic_results")

        # ============================================================
        # 8. LOG MONITORING METRICS
        # ============================================================
        # Extract metrics and log to monitoring service
        try:
            monitoring_metrics = metrics.to_monitoring_dict()
            monitoring.log_search(conversation_id, user_query, monitoring_metrics)
            logger.info(f"✅ Monitoring metrics logged for {conversation_id}")
        except Exception as monitoring_error:
            logger.error(f"❌ Failed to log monitoring metrics: {monitoring_error}")

        # Log comprehensive metrics
        metrics.log_summary()

        logger.info("\n" + "="*80)
        logger.info(f"✅ PIPELINE COMPLETE")
        logger.info("="*80)
        results_to_return = final_results_with_peers if industry_peers else final_results
        logger.info(f"📊 Results: {len(results_to_return)} returned (all enriched profiles)")
        if industry_peers:
            logger.info(f"   Includes {len(industry_peers)} industry peers (enriched in parallel)")
        logger.info(f"⏱️ Time: {metrics.total_time_seconds:.1f}s")
        logger.info(f"📈 Discovery: {metrics.total_influencers_discovered} → "
                   f"{len(unique_results)} unique → "
                   f"{len(sorted_results)} filtered → "
                   f"{len(results_to_return)} returned")
        
        # Log sample results
        if results_to_return:
            logger.info(f"\n📋 SAMPLE RESULTS:")
            for i, r in enumerate(results_to_return[:3], 1):
                logger.info(f"   {i}. {r.get('NAME')} - "
                          f"{r.get('NICHE')} | "
                          f"{r.get('followers')} followers | "
                          f"{r.get('engagement_rate')} engagement")
        
        logger.info("="*80 + "\n")

        return results_to_return, metrics

    except Exception as e:
        logger.exception(f"❌ Pipeline error: {e}")
        metrics.add_error(f"Pipeline exception: {e}")
        metrics.total_time_seconds = time.time() - pipeline_start
        return [], metrics
