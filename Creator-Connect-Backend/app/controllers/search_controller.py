from __future__ import annotations

import asyncio
import json
import logging
from typing import Optional

from fastapi import APIRouter, Body, Form, Header, HTTPException, status
from pydantic import BaseModel, Field

from app.models.schema import ChatPromptResponse
from app.services.core.prompt_service import (
    convert_dynamic_search_to_standard_format,
    persist_dynamic_results,
    record_dynamic_results,
)
from app.services.core.slot_filler_service import InfluencerSlotFiller

# Router removed - Logic only
# router = APIRouter(prefix=PREFIX_SEARCH, tags=["2. Search"])
logger = logging.getLogger(__name__)

# Store slot filler instances per conversation
_slot_filler_instances = {}


from app.config.api_routes import SEARCH_DEFAULTS
from app.config.settings import settings
from app.utils.safe_response import client_safe_500_message


async def get_default_filter_values():
    """
    Returns the default values for niche, location, and followers range.
    """
    from app.services.core.slot_filler_service import InfluencerSlotFiller
    
    return {
        "niche": InfluencerSlotFiller.DEFAULT_NICHE or "",
        "location": InfluencerSlotFiller.DEFAULT_LOCATION,
        "followers_range": InfluencerSlotFiller.DEFAULT_FOLLOWERS_RANGE,
    }


async def dynamic_search_prompt_only(
    query: str = Form(...),
    conversation_id: str = Form("default"),
    niche: str = Form(None),
    location: str = Form(None),
    followers_range: str = Form(None),
) -> ChatPromptResponse:
    """
    **Discover NEW influencers from the web using natural language prompt with Q&A**

    Unlike static search (CSV), this discovers influencers in real-time.
    Uses an interactive Q&A flow to collect required information.

    **How it works:**
    1. Submit your initial query (e.g., "fashion influencers in Paris")
    2. System asks questions if more info needed (niche, location, follower range)
    3. Answer the questions in subsequent requests
    4. When complete, discovers and scrapes influencers from multiple sources

    **Example Flow:**
    - **Request 1**: query="I need influencers" → Response: "What niche?"
    - **Request 2**: query="Fashion" → Response: "What location?"
    - **Request 3**: query="Paris" → Response: "Follower range?"
    - **Request 4**: query="10k-100k" → Response: [Search results with influencers]

    **Returns:**
    - Questions if info incomplete
    - Discovered influencers when search completes
    """
    if not query or not query.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Query parameter is required for prompt analysis.",
        )
    max_len = getattr(settings, "MAX_QUERY_LENGTH", 2000)
    if len(query) > max_len:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Query exceeds maximum length of {max_len} characters.",
        )

    try:
        logger.info("Dynamic prompt-only search")
        logger.debug(f"Conversation ID: {conversation_id}")

        # IMPORTANT: Use separate namespace for dynamic prompt to avoid conflicts
        # Static uses: "default", Dynamic CSV uses: "dynamic:default",
        # Dynamic Prompt uses: "dynamic-prompt:default"
        dynamic_prompt_conversation_id = f"dynamic-prompt:{conversation_id}"

        # Get or create slot filler for this conversation
        if dynamic_prompt_conversation_id not in _slot_filler_instances:
            _slot_filler_instances[dynamic_prompt_conversation_id] = InfluencerSlotFiller()

        slot_filler = _slot_filler_instances[dynamic_prompt_conversation_id]
        # DON'T reset - we need to maintain conversation state between requests
        # Only reset when search is complete or user explicitly starts a new search
        
        # Set advanced search values before processing (override prompt-extracted)
        # because _merge_extracted uses setdefault which only sets if key doesn't exist
        if niche is not None and niche.strip():
            slot_filler.filled_slots['niche'] = niche.strip()
        if location is not None and location.strip():
            slot_filler.filled_slots['location'] = location.strip()
        if followers_range is not None and followers_range.strip():
            slot_filler.filled_slots['followers_range'] = followers_range.strip()
        
        result = slot_filler.process_turn(query)

        # If incomplete, return questions
        if not result["complete"]:
            logger.info(f"Missing: {result.get('asking_for')}")

            return ChatPromptResponse(
                complete=False,
                filled_slots=result.get("filled_slots", {}),
                final_prompt=None,
                search_results=None,
                message=result.get("message"),
                next_question=result.get("next_question"),
                asking_for=result.get("asking_for"),
                missing_slots=result.get("missing_slots", []),
                missing_count=result.get("missing_count", 0)
            )

        # Complete - run dynamic search with final prompt
        final_prompt = result["final_prompt"]
        logger.info(f"All fields collected | Final prompt: {final_prompt}")

        # Import pipeline orchestrator (uses monitoring service)
        from app.services.core.pipeline_orchestrator import run_async_pipeline

        # Generate unique conversation_id for this prompt-only search
        # Use simple format: prompt_{conversation_id} for easy retrieval
        persistence_conversation_id = f"prompt_{conversation_id}"
        logger.debug(f"Using conversation_id for pipeline: {persistence_conversation_id}")

        # ============================================================
        # INTELLIGENT DETECTION: Check if this is a direct link search
        # ============================================================
        instagram_links = result.get("instagram_links")
        search_mode = result.get("filled_slots", {}).get("search_mode", "")
        is_direct_profile_search = (
            final_prompt == "DIRECT_PROFILE_SEARCH" or 
            final_prompt == "DIRECT_LINK_SEARCH" or
            search_mode == "DIRECT_PROFILE" or
            instagram_links
        )

        if is_direct_profile_search and instagram_links:
            logger.info("="*80)
            logger.info("DIRECT PROFILE SEARCH MODE")
            logger.info(f"   [DIRECT_PROFILE_MODE_ACTIVATED] - Discovery disabled, SerpAPI search disabled")
            logger.info("="*80)
            logger.info(f"Processing {len(instagram_links)} Instagram profile(s)")
            logger.info("Bypassing Q&A (direct link)")
            logger.info("="*80)

            # Build influencer seed objects for direct link search
            influencers = []
            for link in instagram_links:
                # Extract username from link
                username = link.rstrip("/").split("/")[-1]
                influencers.append({
                    "name": username,
                    "NAME": username,  # Add uppercase for consistency
                    "Id": username,    # Required for merge_results matching
                    "username": username,
                    "profile_link": link,
                    "PROFILE_LINK": link,
                    "profile_url": link,
                    "url": link,
                })

            try:
                # Run pipeline with SKIP_FILTERING mode
                search_results, metrics = await run_async_pipeline(
                    user_query="DIRECT_PROFILE_SEARCH",
                    csv_path=None,
                    influencers=influencers,
                    skip_analysis=True,
                    conversation_id=persistence_conversation_id,
                    direct_link_mode=True
                )
            except Exception as search_exc:
                logger.exception("Error during direct link search: %s", search_exc)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=client_safe_500_message(search_exc),
                ) from search_exc

        else:
            # ============================================================
            # UNIFIED SEARCH FLOW: Local DB -> Hybrid Web Fallback
            # ============================================================
            try:
                # 1. Parse query first to get parameters for local search
                # We reuse the parser from the pipeline logic, but expose it here briefly or inside service?
                # For simplicity, we stick to the existing pipeline structure but inject the check.
                
                # Import the service here to avoid circular imports if any
                from app.services.core.search_mode_service import SearchModeService
                from app.services.llm.gemini_utils import parse_query_with_gemini
                # We need a temporary metrics object for parsing
                from app.services.reporting.monitoring_service import monitoring
                temp_metrics = monitoring.get_metrics(persistence_conversation_id)
                
                parsed_query = parse_query_with_gemini(final_prompt, temp_metrics)
                
                # 2. Try Unified Search (Local First; workflow: full / partial / no match)
                local_results, source, remaining_count = await SearchModeService.unified_search(
                    user_query=final_prompt,
                    parsed_query=parsed_query,
                    conversation_id=persistence_conversation_id,
                    metrics=temp_metrics,
                )
                if local_results:
                    logger.info(
                        "Served %s results from %s (remaining=%s)",
                        len(local_results),
                        source,
                        remaining_count,
                    )
                    search_results = local_results
                    metrics = temp_metrics
                    # PARTIAL_MATCH: run pipeline for remainder per workflow (BrightData refresh already queued by SearchModeService)
                    if source == "PARTIAL_MATCH" and remaining_count > 0:
                        logger.info("Discovering %s more via pipeline (partial-match remainder)", remaining_count)
                        try:
                            pipeline_results, pipeline_metrics = await run_async_pipeline(
                                user_query=final_prompt,
                                csv_path=None,
                                influencers=None,
                                skip_analysis=True,
                                conversation_id=persistence_conversation_id,
                                direct_link_mode=False,
                                override_num_results=remaining_count,
                            )
                            if pipeline_results:
                                search_results = local_results + pipeline_results
                                logger.info("Appended %s pipeline results; total %s", len(pipeline_results), len(search_results))
                        except Exception as partial_exc:
                            logger.warning("Partial-match pipeline failed (keeping DB results only): %s", partial_exc)
                else:
                    # 3. Fallback to Web Discovery (Original Pipeline)
                    logger.info("🌍 Web Discovery Fallback Activated")
                    search_results, metrics = await run_async_pipeline(
                        user_query=final_prompt,
                        csv_path=None,
                        influencers=None,
                        skip_analysis=True,
                        conversation_id=persistence_conversation_id,
                        direct_link_mode=False
                    )
                    
                    # 4. Async Save to DB (Persistence)
                    # Handled automatically by pipeline_orchestrator since v2 upgrade
                    # if search_results:
                    #      from app.services.core.persistence_service import InfluencerPersistenceService
                    #      asyncio.create_task(InfluencerPersistenceService.bulk_save_influencers(search_results))

                
                # Log what we got back (for debugging)
                if search_results:
                    anchor_count = sum(1 for r in search_results if r.get("industry_anchor") is True)
                    peer_count = sum(1 for r in search_results if r.get("industry_standard") is True)
                    logger.info(f"Pipeline returned {len(search_results)} results: {anchor_count} anchor(s), {peer_count} peer(s)")
            except Exception as search_exc:
                logger.exception("Error during dynamic search pipeline: %s", search_exc)
                raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=client_safe_500_message(search_exc),
                ) from search_exc

        # ============================================================
        # PROCESS RESULTS (common for both flows)
        # ============================================================
        if not search_results:
            logger.warning("No influencers found matching the query")
            return ChatPromptResponse(
                complete=True,
                filled_slots=result.get("filled_slots", {}),
                final_prompt=final_prompt,
                search_results=[],
                message="No influencers found matching your criteria. Please try different parameters.",
                next_question=None,
                asking_for=None,
                missing_slots=[],
                missing_count=0
        )

        logger.info(f"Dynamic search completed: {len(search_results)} results")

        # ============================================================
        # LOG MONITORING METRICS
        # ============================================================
        # Metrics are already logged by pipeline_orchestrator.py
        # The pipeline returns SearchMetrics object which is logged automatically
        # No need to log again here - metrics are tracked in real-time during pipeline execution
        logger.debug(f"Monitoring metrics handled by pipeline for {dynamic_prompt_conversation_id}")

        # ============================================================
        # PERSIST RESULTS FOR /api/results/dynamic/prompt ENDPOINT
        # ============================================================
        import hashlib
        from datetime import datetime

        # persistence_conversation_id already set above
        logger.debug(f"Persisting results with conversation_id: {persistence_conversation_id}")

        # Convert results to format expected by persistence layer
        # Add standardized IDs to each result
        for search_result in search_results:
            profile_link = search_result.get("PROFILE_LINK") or search_result.get("profile_link", "")
            name = search_result.get("NAME") or search_result.get("name", "Unknown")
            niche = search_result.get("NICHE") or search_result.get("niche", "Unknown")
            location = search_result.get("Location") or search_result.get("location", "Unknown")

            # Generate ID (same logic as _compute_influencer_id)
            if profile_link:
                search_result["id"] = hashlib.md5(str(profile_link).encode()).hexdigest()[:12]
            else:
                unique_string = f"{name}_{location}_{niche}"
                search_result["id"] = hashlib.md5(unique_string.encode()).hexdigest()[:12]

        # Persist to storage/dynamic_results/{conversation_id}.json
        # Log what we're persisting (for debugging)
        anchor_count = sum(1 for r in search_results if r.get("industry_anchor") is True)
        peer_count = sum(1 for r in search_results if r.get("industry_standard") is True)
        logger.info(f"Persisting {len(search_results)} results: {anchor_count} anchor(s), {peer_count} peer(s)")
        
        record_dynamic_results(persistence_conversation_id, search_results)
        persist_dynamic_results(persistence_conversation_id, search_results)
        
        logger.info(f"Results persisted for conversation: {persistence_conversation_id}")

        # NOTE: Industry standards are now discovered and enriched IN-PARALLEL during main pipeline
        # No separate background task needed - all data comes in one response

        # Convert to standard format for ChatPromptResponse (matches static CSV format)
        standard_results = convert_dynamic_search_to_standard_format(search_results)
        logger.info(f"Results: {len(standard_results)} influencers")

        # Reset slot filler for next search (search is complete)
        slot_filler.reset()

        return ChatPromptResponse(
            complete=True,
            filled_slots=result.get("filled_slots", {}),
            final_prompt=final_prompt,
            search_results=standard_results,
            conversation_id=persistence_conversation_id,
            message=f"Successfully discovered and analyzed {len(standard_results)} influencers",
            next_question=None,
            asking_for=None,
            missing_slots=[],
            missing_count=0
        )

    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Error during prompt-only dynamic search: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=client_safe_500_message(exc),
        ) from exc


from app.models.schema import SearchResult

async def receive_influencers_webhook(
    influencers: list[SearchResult] = Body(...),
    count: int = Body(...),
    x_webhook_secret: str | None = Header(None, alias="X-Webhook-Secret"),
):
    """
    **INTERNAL WEBHOOK - DO NOT CALL DIRECTLY**

    This endpoint is **automatically called by the backend** when dynamic search completes.
    In production, set WEBHOOK_SECRET and send X-Webhook-Secret header to protect the endpoint.

    **Automatic Trigger:**
    - Called after `/api/dynamic-search/prompt` completes
    - Only if `ENDPOINT_URL` environment variable is configured

    **Purpose:**
    - Receives final sorted influencer results
    - logs discoveries for monitoring
    """
    webhook_secret = getattr(settings, "WEBHOOK_SECRET", "") or ""
    if webhook_secret and (not x_webhook_secret or x_webhook_secret != webhook_secret):
        logger.warning("Webhook rejected: missing or invalid X-Webhook-Secret")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or missing webhook secret",
        )
    try:
        logger.info("="*70)
        logger.info("📥 WEBHOOK: Received influencer data")
        logger.info("="*70)
        logger.info(f"   Count: {count}")
        logger.info(f"   Total influencers: {len(influencers)}")

        # Log sample of first influencer for debugging
        if influencers:
            first = influencers[0]
            logger.info(f"   Sample influencer:")
            logger.info(f"      - Name: {first.get('NAME', 'N/A')}")
            logger.info(f"      - Profile: {first.get('PROFILE_LINK', 'N/A')}")
            logger.info(f"      - Followers: {first.get('followers', 'N/A')}")
            logger.info(f"      - Engagement: {first.get('engagement_rate', 'N/A')}")
            logger.info(f"      - Location: {first.get('Location', 'N/A')}")

        # TODO: Add your custom processing logic here
        # Examples:
        # - Store in database
        # - Send to analytics service
        # - Trigger notifications
        # - Update dashboard

        logger.info("✅ Webhook processed successfully")
        logger.info("="*70)

        return {
            "status": "success",
            "message": "Influencers received successfully",
            "received_count": count,
            "processed": len(influencers)
        }

    except Exception as e:
        logger.exception("Error processing webhook: %s", e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=client_safe_500_message(e),
        ) from e
