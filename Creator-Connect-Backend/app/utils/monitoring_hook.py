"""
Monitoring Hook - Automatically log search metrics
Call this from pipeline orchestrator when search completes
"""

from app.services.reporting.monitoring_service import monitoring
from typing import Dict
import logging

logger = logging.getLogger(__name__)

def log_search_completion(
    conversation_id: str,
    query: str,
    web_searches: int,
    profiles_enriched: int,
    profiles_returned: int,
    tokens_used: int,
    time_breakdown: Dict[str, float]
):
    """
    Log a completed search with all metrics

    Usage in pipeline_orchestrator_streaming.py:

    from app.utils.monitoring_hook import log_search_completion

    # After search completes
    log_search_completion(
        conversation_id=conv_id,
        query=original_query,
        web_searches=num_serpapi_calls,
        profiles_enriched=num_brightdata_requests,
        profiles_returned=len(final_results),
        tokens_used=total_tokens,
        time_breakdown={
            "discovery": discovery_time,
            "enrichment": enrichment_time,
            "analysis": analysis_time
        }
    )
    """
    try:
        metrics = {
            "web_searches": web_searches,
            "profiles_enriched": profiles_enriched,
            "profiles_returned": profiles_returned,
            "tokens_used": tokens_used,
            "time_breakdown": time_breakdown
        }

        log_entry = monitoring.log_search(conversation_id, query, metrics)
        logger.info(f"✅ Logged search: {conversation_id} - Cost: ${log_entry['total_cost']:.4f}")

    except Exception as e:
        logger.error(f"❌ Failed to log search metrics: {e}")
