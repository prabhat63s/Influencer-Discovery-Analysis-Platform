"""
Streaming Pipeline Orchestrator
================================
Real-time streaming with discovery, enrichment, ranking, and results.

Pipeline flow: User Query → SerpAPI → BrightData → merge → UI; Spreadd (authenticity) runs in parallel after merge.

Event Flow:
1. Discovery: Emit each discovered influencer
2. Scraping: SerpAPI first (progress per influencer), then BrightData
3. Merge: SerpAPI + BrightData; then Spreadd in parallel (authenticity score)
4. Profiles phase: Emit each profile included
5. Ranking: Emit final rankings
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from datetime import datetime
from typing import Dict, List, Optional, AsyncGenerator

from app.services.reporting.monitoring_service import SearchMetrics, monitoring
from app.services.scrapers.spreadd_service import AsyncSpreaddChecker, run_spreadd_parallel
from app.services.scrapers.serpapi_service import GoogleSearch
from app.services.scrapers.search_scrapers import discover_influencers_from_prompt
from app.services.core.search_filters import (
    extract_snippet_metrics as _extract_snippet_metrics,
    extract_rate_range as _extract_rate_range,
)
from app.services.scrapers.brightdata_scraper import scraper_b_csv_brightdata
from app.services.core.search_filters import (
    remove_duplicates,
    merge_results,
    parse_rate_to_int,
    parse_followers_to_int
)

logger = logging.getLogger(__name__)
# Toggle verbose streaming logs via env (default: off)
VERBOSE_STREAM_LOGS = os.getenv("VERBOSE_STREAM_LOGS", "false").lower() == "true"


async def run_streaming_pipeline(
    user_query: str,
    conversation_id: str,
    num_results: int = 3,
    influencers: Optional[List[Dict]] = None,
    direct_link_mode: bool = False
) -> AsyncGenerator[Dict, None]:
    """
    Streaming pipeline that yields events at every step.

    - influencers: Pre-built list (e.g. direct link search).
    - direct_link_mode: When True, use only provided influencers and exact username match.

    Yields: status, discovery_start, influencer_discovered, scraping_*, profiles_phase,
            profile_included, influencer_ranked, complete, error.
    """

    metrics = monitoring.get_metrics(conversation_id)
    metrics.query = user_query
    metrics.timestamp = datetime.now().isoformat()
    pipeline_start = time.time()

    try:
        # STEP 1: Parse query
        # ============================================================
        # ============================================================
        # DIRECT PROFILE MODE: Skip discovery, use only provided influencers
        # ============================================================
        is_direct_profile_mode = (
            user_query == "DIRECT_PROFILE_SEARCH" or 
            user_query == "DIRECT_LINK_SEARCH" or
            (influencers is not None and len(influencers) > 0)
        )
        
        if is_direct_profile_mode and influencers is not None:
            logger.info(f"🔗 STREAMING: DIRECT_PROFILE mode - skipping discovery")
            logger.info(f"   [DIRECT_PROFILE_MODE_ACTIVATED] - Discovery disabled, SerpAPI search disabled")
            
            # GUARD CLAUSE: Enforce direct profile mode
            disable_discovery = True
            serpapi_search = False
            
            if not disable_discovery or serpapi_search:
                logger.warning("⚠️ [VIOLATION] Direct profile mode violated - discovery or SerpAPI should be disabled!")
            
            # Create minimal parsed_query for direct profile search
            parsed_query = {
                'num_results': len(influencers),
                'niche': 'Direct Profile Search',
                'location': 'India',
                'min_followers': None,
                'max_followers': None,
                'search_queries': [],  # EMPTY - no discovery queries
                'original_query': user_query,
                'search_mode': 'DIRECT_PROFILE'
            }
            num_results = len(influencers)

            yield {
                'type': 'status',
                'stage': 'direct_profile',
                'message': f'Analyzing {len(influencers)} Instagram profile(s)...'
            }

        else:
            # Normal query parsing
            yield {
                'type': 'status',
                'stage': 'parsing',
                'message': 'Analyzing your query with AI...'
            }

            from app.services.llm.gemini_utils import parse_query_with_gemini

            if VERBOSE_STREAM_LOGS:
                logger.info(f"🔍 BEFORE parse_query_with_gemini - num_results = {num_results}")
            parsed_query = parse_query_with_gemini(user_query, metrics)
            if VERBOSE_STREAM_LOGS:
                logger.info(f"🔍 AFTER parse_query_with_gemini - parsed_query.get('num_results') = {parsed_query.get('num_results')}")

            # Override num_results with value from parsed query (user's request)
            parsed_num_results = parsed_query.get('num_results')
            if VERBOSE_STREAM_LOGS:
                logger.info(f"🔍 parsed_num_results = {parsed_num_results}, type = {type(parsed_num_results)}")
            if parsed_num_results:
                num_results = int(parsed_num_results)

        yield {
            'type': 'query_parsed',
            'niche': parsed_query.get('niche'),
            'location': parsed_query.get('location'),
            'min_followers': parsed_query.get('min_followers'),
            'max_followers': parsed_query.get('max_followers'),
            'num_results': num_results
        }

        # STEP 2: Discovery
        search_start = time.time()

        # ============================================================
        # INTELLIGENT DETECTION: Check if pre-built influencer list provided
        # ============================================================
        if influencers is not None:
            logger.info(f"🔗 STREAMING: Using pre-built influencer list ({len(influencers)} profiles)")
            yield {
                'type': 'discovery_start',
                'message': f'Analyzing {len(influencers)} Instagram profile(s)...'
            }

            discovered = influencers
            metrics.total_influencers_discovered = len(discovered)

            # Emit each provided influencer
            for idx, inf in enumerate(discovered, 1):
                yield {
                    'type': 'influencer_discovered',
                    'index': idx,
                    'total': len(discovered),
                    'name': inf.get('name'),
                    'username': inf.get('username'),
                    'profile_link': inf.get('profile_link'),
                    'followers': inf.get('followers', 'N/A'),
                    'niche': 'Unknown',
                    'location': 'Unknown'
                }
                await asyncio.sleep(0.1)

        else:
            # Normal discovery flow (ONLY if not DIRECT_PROFILE mode)
            # GUARD CLAUSE: Prevent discovery in direct profile mode
            if parsed_query.get('search_mode') == 'DIRECT_PROFILE':
                logger.error("❌ [VIOLATION] Attempted discovery in DIRECT_PROFILE mode - this should never happen!")
                yield {'type': 'error', 'message': 'Invalid search mode: discovery attempted in direct profile mode'}
                return
            
            yield {
                'type': 'discovery_start',
                'message': f'Searching for {parsed_query["niche"]} influencers in {parsed_query["location"]}...'
            }

            discovered = await discover_influencers_from_prompt(parsed_query)

            if not discovered:
                yield {'type': 'error', 'message': 'No influencers discovered'}
                return

            # Emit each discovered influencer
            for idx, inf in enumerate(discovered, 1):
                yield {
                    'type': 'influencer_discovered',
                    'index': idx,
                    'total': len(discovered),
                    'name': inf.get('name'),
                    'username': inf.get('username'),
                    'profile_link': inf.get('profile_link'),
                    'followers': inf.get('followers', 'N/A'),
                    'niche': parsed_query.get('niche'),
                    'location': parsed_query.get('location')
                }
                await asyncio.sleep(0.1)  # Small delay for UI

            metrics.total_influencers_discovered = len(discovered)

        # Record discovery/search time
        metrics.search_time_seconds = time.time() - search_start

        # STEP 3: Scraping
        scrape_start = time.time()
        yield {
            'type': 'scraping_start',
            'message': f'Validating {len(discovered)} influencer profiles...',
            'total': len(discovered)
        }

        # Run scrapers with progress updates
        scraper_a_results = []
        scraper_b_results = []

        # Flow: User Query → SerpAPI → BrightData → UI; Spreadd (authenticity) runs in parallel after merge
        progress_queue = asyncio.Queue()

        async def progress_cb(msg, idx, total, username=None, profile_link=None, completed=False, enriched_data=None):
            await progress_queue.put({
                'type': 'scraping_progress',
                'scraper': 'serpapi',
                'message': msg,
                'index': idx,
                'total': total,
                'username': username,
                'profile_link': profile_link,
                'completed': completed,
                'enriched_data': enriched_data
            })

        async def scraper_task():
            return await scraper_a_serpapi_only_streaming(
                discovered, parsed_query, metrics, progress_cb
            )
        
        # Start scraper and yield progress events as they arrive
        scraper_future = asyncio.create_task(scraper_task())
        
        # Yield progress events in real-time
        while not scraper_future.done() or not progress_queue.empty():
            try:
                # Get progress event with short timeout
                event = await asyncio.wait_for(progress_queue.get(), timeout=0.05)
                yield event
            except asyncio.TimeoutError:
                # If scraper is done and queue is empty, break
                if scraper_future.done() and progress_queue.empty():
                    break
                # Otherwise continue waiting
                continue
        
        # Get final results from Scraper A (SerpAPI only)
        scraper_a_results = await scraper_future

        # Scraper B (BrightData) - run after SerpAPI for full profile (posts, bio, etc.)
        scraper_b_results = []
        if discovered:
            yield {
                'type': 'status',
                'message': 'BrightData: deep profile analysis...'
            }
            logger.info("="*70)
            logger.info(f"🔄 BRIGHTDATA: Starting enrichment for {len(discovered)} profile(s)")
            logger.info("="*70)
            loop = asyncio.get_event_loop()
            # OPTIMIZED: Skip AI processing during enrichment (will process only top N later)
            scraper_b_task = loop.run_in_executor(
                None, scraper_b_csv_brightdata, discovered, parsed_query, True  # skip_ai_processing=True
            )
            try:
                scraper_b_results = await scraper_b_task
                if scraper_b_results:
                    logger.info(f"✅ BRIGHTDATA: Successfully enriched {len(scraper_b_results)} profile(s)")
                else:
                    logger.warning(f"⚠️ BRIGHTDATA: No results returned (will use Spreadd data only)")
            except Exception as e:
                logger.error(f"❌ BRIGHTDATA: Exception occurred - {type(e).__name__}: {str(e)}")
                scraper_b_results = []
            if isinstance(scraper_b_results, Exception):
                logger.error(f"❌ BRIGHTDATA: Task returned exception - {scraper_b_results}")
                scraper_b_results = []

        # Scraping complete - record timing
        metrics.scraping_time_seconds = time.time() - scrape_start

        yield {
            'type': 'scraping_complete',
            'serpapi_results': len(scraper_a_results),
            'brightdata_results': len(scraper_b_results)
        }

        # STEP 4: Merge
        yield {
            'type': 'status',
            'stage': 'merging',
            'message': 'Merging results from multiple sources...'
        }

        merged = merge_results(scraper_a_results, scraper_b_results, [])
        unique = remove_duplicates(merged)

        if metrics:
            metrics.total_influencers_after_dedup = len(unique)
            metrics.profiles_enriched = len(scraper_b_results)
            metrics.brightdata_calls = len(scraper_b_results)

        yield {
            'type': 'merge_complete',
            'merged': len(merged),
            'unique': len(unique)
        }

        # Spreadd (authenticity score) in parallel – merge into results for UI
        if unique:
            yield {
                'type': 'status',
                'stage': 'authenticity',
                'message': 'Fetching authenticity scores (Spreadd)...'
            }
            await run_spreadd_parallel(unique, metrics)
            yield {
                'type': 'status',
                'stage': 'authenticity_complete',
                'message': 'Authenticity scores ready'
            }

        # STEP 5: Profiles phase — include all, emit each for UI
        phase_start = time.time()

        if direct_link_mode:
            if VERBOSE_STREAM_LOGS:
                logger.info(f"Direct link mode: processing {len(unique)} profiles")
            yield {
                'type': 'profiles_phase',
                'message': 'Direct link search...',
                'total': len(unique)
            }
            is_direct_profile = (
                user_query == "DIRECT_PROFILE_SEARCH" or
                user_query == "DIRECT_LINK_SEARCH" or
                parsed_query.get('search_mode') == 'DIRECT_PROFILE'
            )
            if is_direct_profile and influencers and len(influencers) > 0:
                target_usernames = set()
                for inf in influencers:
                    username = inf.get("username") or inf.get("Id") or inf.get("name", "")
                    if username:
                        target_usernames.add(username.lower().lstrip("@"))
                exact_matches = [
                    inf for inf in unique
                    if (inf.get("Id") or inf.get("username") or inf.get("NAME") or inf.get("name", "")).lower().lstrip("@") in target_usernames
                ]
                if exact_matches:
                    profiles = exact_matches
                    logger.info(f"Direct link: {len(exact_matches)} exact username match(es)")
                else:
                    profiles = unique[:1]
                    logger.warning("Exact username match not found, using first result")
            else:
                profiles = list(unique)
            for idx, inf in enumerate(unique, 1):
                yield {
                    'type': 'profile_included',
                    'index': idx,
                    'total': len(unique),
                    'name': inf.get('NAME'),
                    'username': inf.get('Id'),
                    'profile_link': inf.get('PROFILE_LINK') or inf.get('profile_link'),
                    'followers': inf.get('followers', 'N/A'),
                    'passed': True,
                    'reason': 'Direct link'
                }
                await asyncio.sleep(0.05)
        else:
            yield {
                'type': 'profiles_phase',
                'message': 'Rendering all profiles...',
                'total': len(unique)
            }
            profiles = list(unique)
            for idx, inf in enumerate(unique, 1):
                yield {
                    'type': 'profile_included',
                    'index': idx,
                    'total': len(unique),
                    'name': inf.get('NAME'),
                    'username': inf.get('Id'),
                    'profile_link': inf.get('PROFILE_LINK') or inf.get('profile_link'),
                    'followers': inf.get('followers', 'N/A'),
                    'passed': True,
                    'reason': 'Included'
                }
                await asyncio.sleep(0.05)
            logger.info(f"Rendering all: {len(profiles)} profiles")

        if len(unique) == 0:
            yield {
                'type': 'error',
                'message': 'No influencers found'
            }
            return

        # STEP 6: Sorting and ranking
        yield {
            'type': 'status',
            'stage': 'ranking',
            'message': 'Ranking influencers by relevance...'
        }

        # Sort by relevance
        from app.services.core.search_filters import _calculate_relevance_score
        ranked_with_scores = [
            (inf, _calculate_relevance_score(inf, parsed_query))
            for inf in profiles
        ]
        ranked_with_scores.sort(key=lambda x: x[1], reverse=True)

        final_num_results = parsed_query.get('num_results', 3)
        top_results = ranked_with_scores[:final_num_results]
        logger.info(f"Top {final_num_results}: " + ", ".join([f"@{inf.get('Id')} ({score:.0f})" for inf, score in top_results]))

        for rank, (inf, score) in enumerate(ranked_with_scores[:10], 1):
            yield {
                'type': 'influencer_ranked',
                'rank': rank,
                'name': inf.get('NAME'),
                'username': inf.get('Id'),
                'profile_link': inf.get('PROFILE_LINK'),
                'followers': inf.get('followers'),
                'score': round(score, 2),
                'is_top_result': rank <= final_num_results
            }
            await asyncio.sleep(0.1)

        metrics.sort_time_seconds = time.time() - phase_start

        is_direct_profile_single = (
            (user_query == "DIRECT_PROFILE_SEARCH" or user_query == "DIRECT_LINK_SEARCH" or parsed_query.get('search_mode') == 'DIRECT_PROFILE') and
            influencers and len(influencers) == 1
        )
        if is_direct_profile_single:
            target_username = (influencers[0].get("username") or influencers[0].get("Id") or influencers[0].get("name", "")).lower().lstrip("@")
            exact_matches = []
            for inf, score in ranked_with_scores:
                result_username = (
                    inf.get("Id") or 
                    inf.get("username") or 
                    inf.get("NAME", "") or 
                    inf.get("name", "")
                ).lower().lstrip("@")
                
                if result_username == target_username:
                    exact_matches.append((inf, score))
                    break  # Only need one exact match
            
            if exact_matches:
                final_results = [inf for inf, score in exact_matches[:1]]
                logger.info(f"DIRECT_PROFILE: exact match @{target_username}")
            else:
                final_results = [inf for inf, score in ranked_with_scores[:1]]
                logger.warning(f"Exact match not found for @{target_username}, using first result")
        else:
            final_results = [inf for inf, score in ranked_with_scores[:final_num_results]]

        # ========================================================================
        # STEP 8: AI PROCESSING - Only for top N selected influencers (PARALLEL)
        # ========================================================================
        yield {
            'type': 'status',
            'stage': 'ai_processing',
            'message': f'Running AI analysis for top {len(final_results)} influencers...'
        }
        
        try:
            from app.services.llm.ai_processing import process_ai_tasks_parallel
            logger.info(f"🚀 Processing AI tasks in parallel for {len(final_results)} top influencers...")
            final_results = await process_ai_tasks_parallel(final_results, parsed_query)
            logger.info(f"✅ AI processing completed for {len(final_results)} influencers")
        except ImportError:
            logger.warning("⚠️ AI processing module not available, skipping")
        except Exception as e:
            logger.error(f"❌ AI processing failed: {e}")
            # Continue with results even if AI processing fails

        # ========================================================================
        # SINGLE ENTRY POINT: Start industry standards discovery (exactly once)
        # CRITICAL: Only run for single profile searches, NOT for top 3/5 searches
        # Top 3/5 searches use internal comparison (comparing results against each other)
        # ========================================================================
        industry_standards_started = False
        try:
            from app.services.analysis.industry_standards import (
                ENABLE_INDUSTRY_STANDARDS,
                start_industry_standards_discovery
            )
            
            # CRITICAL: Only start industry standards for single profile searches (len == 1)
            # Top 3/5 searches should NOT trigger industry standards - they use internal comparison
            is_single_profile_search = len(final_results) == 1
            
            if final_results and ENABLE_INDUSTRY_STANDARDS and is_single_profile_search:
                # Use single authoritative entry point - ensures exactly one execution per conversation
                industry_standards_started = start_industry_standards_discovery(
                    results=final_results,
                    parsed_query=parsed_query,
                    conversation_id=conversation_id
                )
                if industry_standards_started:
                    logger.info("✅ Industry standards discovery started (single profile search only)")
            elif len(final_results) > 1:
                logger.info(f"⏭️ Skipping industry standards discovery: {len(final_results)} results (top 3/5 search - will use internal comparison)")
        except ImportError:
            # Industry standards module not available, skip
            pass
        except Exception as e:
            logger.warning(f"⚠️ Failed to start industry standards discovery: {e}")

        # ========================================================================
        # PROFESSION PEERS FOR TOP SEARCHES (BACKGROUND TASK)
        # ========================================================================
        # For top N searches (2-5 results) where we don't have industry peers,
        # trigger background discovery of "Profession Peers" (5x followers)
        is_top_search = len(final_results) >= 2 and len(final_results) <= 5
        is_direct_username_search = (
            user_query == "DIRECT_PROFILE_SEARCH" or 
            user_query == "DIRECT_LINK_SEARCH" or 
            parsed_query.get('search_mode') == 'DIRECT_PROFILE'
        )
        
        if is_top_search and not is_direct_username_search and final_results:
            try:
                from app.services.analysis.industry_standards import start_profession_peers_background
                
                # Use first result as anchor
                anchor_for_peer_discovery = final_results[0]
                
                # Start background task (fire and forget)
                asyncio.create_task(
                    start_profession_peers_background(
                        anchor=anchor_for_peer_discovery,
                        parsed_query=parsed_query,
                        conversation_id=conversation_id,
                        follower_multiplier=5.0
                    )
                )
                logger.info(f"🚀 Triggered background profession peers discovery for {conversation_id}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to trigger profession peers background task: {e}")

        # ENHANCEMENT: For direct profile searches, ensure niche is set correctly
        # Identity resolution should have run in brightdata_scraper.py, but ensure it's set even if BrightData failed
        if user_query == "DIRECT_PROFILE_SEARCH" or user_query == "DIRECT_LINK_SEARCH":
            for inf in final_results:
                # Check if NICHE is already set by identity resolution (from brightdata_scraper.py)
                current_niche = inf.get('NICHE') or inf.get('niche')
                
                # If niche is missing or is a placeholder, try to get it from scraped data or run identity resolution
                if not current_niche or current_niche in ('N/A', 'Direct Link Search', 'Direct Profile Search', 'General', '', None):
                    # Try to get from scraped data first
                    scraped_niche = (
                        inf.get('business_category_name') or
                        inf.get('category_name')
                    )
                    
                    if scraped_niche and scraped_niche not in ('N/A', 'Direct Link Search', 'General', '', None):
                        inf['NICHE'] = scraped_niche
                        inf['niche'] = scraped_niche
                        logger.debug(f"   Updated NICHE for @{inf.get('Id')} from scraped data: {scraped_niche}")
                    else:
                        # If still missing, run identity resolution via canonical sync helper
                        try:
                            from app.services.analysis.industry_standards import run_identity_resolution_sync
                            profile_url = inf.get('PROFILE_LINK') or inf.get('profile_link', '')
                            username = inf.get('Id') or inf.get('username', '')
                            if profile_url and username:
                                logger.info("   🔍 Running identity resolution for @%s (niche missing)", username)
                                identity = run_identity_resolution_sync(
                                    profile_url=profile_url,
                                    username=username,
                                    full_name=inf.get('NAME'),
                                    biography=inf.get('biography'),
                                    external_url=inf.get('external_url'),
                                    timeout_seconds=10,
                                )
                                inf['NICHE'] = identity['profession']
                                inf['niche'] = identity['profession']
                                inf['identity_confidence'] = identity['confidence']
                                inf['identity_source'] = identity['source']
                                inf['identity_reason'] = identity.get('reason', '')
                                logger.info("   ✅ Set NICHE for @%s via identity resolution: %s", username, identity['profession'])
                            else:
                                # Fallback if we can't run identity resolution
                                inf['NICHE'] = 'Digital Creator'
                                inf['niche'] = 'Digital Creator'
                                logger.warning(f"   ⚠️ Could not run identity resolution for @{inf.get('Id')}, set to 'Digital Creator'")
                        except Exception as e:
                            logger.warning(f"   ⚠️ Identity resolution failed for @{inf.get('Id')}: {e}")
                            inf['NICHE'] = 'Digital Creator'
                            inf['niche'] = 'Digital Creator'

                # NOTE: Location is already searched in brightdata_scraper.py during enrichment
                # No need to search again here to avoid duplicate OpenAI calls
                # Location search happens in brightdata_scraper.py, no duplicate search needed
                scraped_location = inf.get('Location') or inf.get('location')
                if not scraped_location or scraped_location in ['India', 'N/A', 'Unknown', '']:
                    logger.debug(f"   ℹ️ Location for @{inf.get('Id')} is {scraped_location} (already processed during enrichment)")

        # CRITICAL FIX: Ensure anchor is marked even if industry standards didn't complete yet
        if final_results and not final_results[0].get("industry_anchor"):
            # Mark first result as anchor (will be used for industry comparison)
            final_results[0]["industry_anchor"] = True
            logger.info(f"✅ Tagged anchor (fallback): @{final_results[0].get('Id', 'unknown')}")
        
        metrics.influencers_returned = len(final_results)
        metrics.total_time_seconds = time.time() - pipeline_start

        # ============================================================
        # LOG MONITORING METRICS
        # ============================================================
        try:
            monitoring_metrics = metrics.to_monitoring_dict()
            # Ensure all required fields are present
            required_fields = ["web_searches", "profiles_enriched", "authenticity_checks", "tokens_used", "ai_calls"]
            for field in required_fields:
                if field not in monitoring_metrics:
                    monitoring_metrics[field] = 0
                    logger.debug(f"   Added missing field {field} = 0")
            monitoring.log_search(conversation_id, user_query, monitoring_metrics)
            logger.info(f"✅ Monitoring metrics logged for {conversation_id}")
        except Exception as monitoring_error:
            logger.error(f"❌ Failed to log monitoring metrics: {monitoring_error}", exc_info=True)

        yield {
            'type': 'selection_complete',
            'selected': len(final_results),
            'total_discovered': len(discovered),
            'total_profiles': len(profiles)
        }

        # ========================================================================
        # STEP 8: Mark anchor and set industry comparison status
        # ========================================================================
        # CRITICAL: Always mark anchor immediately (peers will appear via status polling)
        if final_results and not final_results[0].get("industry_anchor"):
            final_results[0]["industry_anchor"] = True
            logger.info(f"✅ Tagged anchor: @{final_results[0].get('Id', 'unknown')}")
        
        # Set industry comparison status based on discovery start
        if industry_standards_started:
            industry_comparison_status = {
                "status": "processing",
                "reason": "Processing industry standards..."
            }
            logger.info("✅ Industry standards discovery started - status set to 'processing'")
        else:
            industry_comparison_status = {
                "status": "pending",
                "reason": "Finding industry standards..."
            }
        
        # Each result may include 'posts' (list of {image_url, caption, likes, comments, ...}) for post-display workflow
        yield {
            'type': 'complete',
            'results': final_results,
            'metrics': {
                'total_time': round(metrics.total_time_seconds, 2),
                'discovered': metrics.total_influencers_discovered,
                'returned': metrics.influencers_returned,
                'success_rate': round(metrics.calculate_success_rate(), 1)
            },
            'industry_comparison': industry_comparison_status
        }

    except Exception as e:
        logger.exception(f"Streaming pipeline error: {e}")
        yield {
            'type': 'error',
            'message': str(e)
        }

async def scraper_a_serpapi_only_streaming(
    influencers: List[Dict[str, str]],
    parsed_query: Dict,
    metrics: Optional[SearchMetrics],
    progress_callback
) -> List[Dict]:
    """
    Scraper A: SerpAPI only (no Spreadd). Used for flow: User Query → SerpAPI → BrightData → UI.
    Spreadd (authenticity score) runs in parallel after merge.
    """
    from app.services.core.search_filters import calculate_rate
    from app.config.settings import settings
    SERP_API_KEY = settings.SERP_API_KEY

    if not influencers:
        return []

    niche = parsed_query.get('niche') or "General"
    location = parsed_query.get('location') or "India"
    results: List[Dict] = []

    for idx, inf in enumerate(influencers, 1):
        username = inf.get("username")
        if not username:
            continue

        profile_link = inf.get("profile_link") or f"https://instagram.com/{username}"
        await progress_callback(
            f"SerpAPI @{username}...",
            idx,
            len(influencers),
            username=username,
            profile_link=profile_link
        )
        await asyncio.sleep(0.1)

        serp_params = {
            "api_key": SERP_API_KEY,
            "engine": "google",
            "q": f"{username} instagram",
            "location": location,
            "google_domain": "google.co.in",
            "gl": "in",
            "hl": "en",
            "num": 3,
        }
        loop = asyncio.get_event_loop()
        serp_data = await loop.run_in_executor(
            None, lambda: GoogleSearch(serp_params).get_dict()
        )
        if metrics:
            metrics.serpapi_calls += 1

        serp_metrics = {}
        rate_range = {}
        if "error" not in serp_data:
            organic = serp_data.get("organic_results", [])
            if organic:
                first_result = organic[0]
                snippet = first_result.get("snippet", "")
                title = first_result.get("title", "")
                snippet_metrics = _extract_snippet_metrics(snippet)
                serp_metrics.update(snippet_metrics)
                combined_text = f"{title} {snippet}".strip()
                extracted_rate = _extract_rate_range(combined_text)
                if extracted_rate:
                    rate_range = extracted_rate

        followers_str = serp_metrics.get("followers_serp", "0")
        min_rate = rate_range.get("min_rate")
        max_rate = rate_range.get("max_rate")
        if min_rate is not None:
            primary_rate = min_rate
            rate_display = f"₹{min_rate:,}"
            if max_rate and max_rate != min_rate:
                rate_display = f"₹{min_rate:,} - ₹{max_rate:,}"
        else:
            primary_rate = parse_rate_to_int(calculate_rate(followers_str))
            rate_display = calculate_rate(followers_str)

        from app.utils.image_utils import extract_profile_image
        combined_data = {**inf, **serp_metrics}
        profile_pic_url = extract_profile_image(combined_data, username, "pipeline_orchestrator_streaming")

        merged = {
            "NAME": inf.get("name", username),
            "Id": username,
            "PROFILE_LINK": inf.get("profile_link") or profile_link,
            "profile_pic_url": profile_pic_url,
            "profile_image": profile_pic_url,
            "image": profile_pic_url,
            "platform": "instagram",
            "followers": serp_metrics.get("followers_serp", "N/A"),
            "following": serp_metrics.get("following_serp", "N/A"),
            "posts_count": serp_metrics.get("posts_serp", "N/A"),
            "average_likes": "N/A",
            "average_comments": "N/A",
            "engagement_rate": "N/A",
            "real_followers_percentage": "N/A",
            "suspicious_followers_percentage": "N/A",
            "NICHE": niche,
            "Location": location,
            "niche_hint": inf.get("niche_hint", niche),
            "location_hint": inf.get("location_hint", location),
            "RATE": rate_display,
            "min_rate": min_rate,
            "max_rate": max_rate,
            "rate": primary_rate,
            "serp_followers": serp_metrics.get("followers_serp"),
            "source": "csv_serpapi"
        }
        results.append(merged)
        await progress_callback(
            f"Completed @{username}",
            idx,
            len(influencers),
            username=username,
            profile_link=profile_link,
            completed=True,
            enriched_data=merged
        )
        await asyncio.sleep(0.15)

    return results


async def scraper_a_serpapi_spreadd_streaming(
    influencers: List[Dict[str, str]],
    parsed_query: Dict,
    metrics: Optional[SearchMetrics],
    progress_callback
) -> List[Dict]:
    """
    Legacy: SerpAPI + Spreadd per influencer (sequential). Prefer flow: SerpAPI → BrightData → UI, then Spreadd in parallel.
    """
    from app.services.core.search_filters import calculate_rate
    from app.config.settings import settings
    SERP_API_KEY = settings.SERP_API_KEY

    if not influencers:
        return []

    niche = parsed_query.get('niche') or "General"
    location = parsed_query.get('location') or "India"

    checker = None
    try:
        checker = AsyncSpreaddChecker(headless=True)
    except Exception as e:
        logger.warning(f"⚠️ Could not initialize Chrome driver: {e}. Continuing without Spreadd enrichment.")

    results: List[Dict] = []

    try:
        for idx, inf in enumerate(influencers, 1):
            username = inf.get("username")
            if not username:
                continue

            profile_link = inf.get("profile_link") or f"https://instagram.com/{username}"
            await progress_callback(
                f"Analyzing @{username}...",
                idx,
                len(influencers),
                username=username,
                profile_link=profile_link
            )
            await asyncio.sleep(0.1)

            serp_params = {
                "api_key": SERP_API_KEY,
                "engine": "google",
                "q": f"{username} instagram",
                "location": location,
                "google_domain": "google.co.in",
                "gl": "in",
                "hl": "en",
                "num": 3,
            }
            loop = asyncio.get_event_loop()
            serp_data = await loop.run_in_executor(
                None, lambda: GoogleSearch(serp_params).get_dict()
            )
            if metrics:
                metrics.serpapi_calls += 1

            serp_metrics = {}
            rate_range = {}
            if "error" not in serp_data:
                organic = serp_data.get("organic_results", [])
                if organic:
                    first_result = organic[0]
                    snippet = first_result.get("snippet", "")
                    title = first_result.get("title", "")
                    snippet_metrics = _extract_snippet_metrics(snippet)
                    serp_metrics.update(snippet_metrics)
                    combined_text = f"{title} {snippet}".strip()
                    extracted_rate = _extract_rate_range(combined_text)
                    if extracted_rate:
                        rate_range = extracted_rate

            spreadd_data = None
            if checker:
                try:
                    spreadd_data = await checker.check_username(username)
                    if metrics:
                        metrics.spreadd_calls += 1
                except Exception as e:
                    logger.warning(f"⚠️ Spreadd check failed for @{username}: {e}")

            if not spreadd_data:
                spreadd_data = {
                    "username": username,
                    "followers": "N/A",
                    "posts": "N/A",
                    "engagement_rate": "N/A"
                }

            followers_str = spreadd_data.get("followers", serp_metrics.get("followers_serp", "0"))
            min_rate = rate_range.get("min_rate")
            max_rate = rate_range.get("max_rate")
            if min_rate is not None:
                primary_rate = min_rate
                rate_display = f"₹{min_rate:,}"
                if max_rate and max_rate != min_rate:
                    rate_display = f"₹{min_rate:,} - ₹{max_rate:,}"
            else:
                primary_rate = parse_rate_to_int(calculate_rate(followers_str))
                rate_display = calculate_rate(followers_str)

            from app.utils.image_utils import extract_profile_image
            combined_data = {**inf, **serp_metrics, **spreadd_data}
            profile_pic_url = extract_profile_image(combined_data, username, "pipeline_orchestrator_streaming")

            merged = {
                "NAME": inf.get("name", username),
                "Id": username,
                "PROFILE_LINK": inf.get("profile_link") or profile_link,
                "profile_pic_url": profile_pic_url,
                "profile_image": profile_pic_url,
                "image": profile_pic_url,
                "platform": "instagram",
                "followers": spreadd_data.get("followers", serp_metrics.get("followers_serp", "N/A")),
                "following": spreadd_data.get("following", serp_metrics.get("following_serp", "N/A")),
                "posts_count": spreadd_data.get("posts", serp_metrics.get("posts_serp", "N/A")),
                "average_likes": spreadd_data.get("avg_likes", "N/A"),
                "average_comments": spreadd_data.get("avg_comments", "N/A"),
                "engagement_rate": spreadd_data.get("engagement_rate", "N/A"),
                "real_followers_percentage": spreadd_data.get("real_followers_percentage", "N/A"),
                "suspicious_followers_percentage": spreadd_data.get("suspicious_followers_percentage", "N/A"),
                "NICHE": niche,
                "Location": location,
                "niche_hint": inf.get("niche_hint", niche),
                "location_hint": inf.get("location_hint", location),
                "RATE": rate_display,
                "min_rate": min_rate,
                "max_rate": max_rate,
                "rate": primary_rate,
                "serp_followers": serp_metrics.get("followers_serp"),
                "source": "csv_serpapi_spreadd"
            }
            results.append(merged)
            await progress_callback(
                f"Completed @{username}",
                idx,
                len(influencers),
                username=username,
                profile_link=profile_link,
                completed=True,
                enriched_data=merged
            )
            await asyncio.sleep(0.15)

    finally:
        if checker:
            try:
                checker.close()
            except Exception as e:
                logger.warning(f"Error closing Chrome driver: {e}")

    return results


# Helper for async yielding in callback
async def async_yield(data):
    """Helper to yield data in async context"""
    pass  # This will be handled by the generator
