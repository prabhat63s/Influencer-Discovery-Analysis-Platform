"""
Search Scrapers Facade
======================
This module now serves as a facade, delegating to specialized services:
- `app.services.scrapers.serpapi_service`: For Google Search / SerpAPI interactions.
- `app.services.scrapers.spreadd_service`: For Spreadd.io authenticity checks.
- `app.services.core.search_filters`: For string extraction and utilities.

Legacy functions are maintained for backward compatibility where possible.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Any

from app.services.scrapers.serpapi_service import (
    scraper_a_serpapi_only,
    GoogleSearch, # Exposed for compatibility if needed
    SERP_API_KEY
)
from app.services.scrapers.spreadd_service import (
    AsyncSpreaddChecker,
    run_spreadd_parallel
)
from app.services.core.search_filters import (
    extract_username_from_url as _extract_username_from_url,
    extract_rate_range as _extract_rate_range,
    extract_snippet_metrics as _extract_snippet_metrics,
    parse_followers_to_int as _parse_followers_to_int
)

logger = logging.getLogger(__name__)


# ============================================================================
# DISCOVERY ROUTES
# ============================================================================

async def discover_influencers_from_prompt(parsed_query: Dict) -> List[Dict]:
    """
    Entry point: use canonical discovery in discovery_service.
    Delegates to discovery_service.discover_influencers_from_prompt.
    """
    try:
        from app.services.core.discovery_service import discover_influencers_from_prompt as _discover
        return await _discover(parsed_query)
    except Exception as e:
        logger.error(f"Discovery failed: {e}")
        return []


async def discover_influencers_from_serpapi(parsed_query: Dict) -> List[Dict]:
    """Fallback: retry canonical discovery."""
    return await discover_influencers_from_prompt(parsed_query)


# ============================================================================
# LEGACY COMPATIBILITY / COMBINED PIPELINES
# ============================================================================

async def scraper_a_serpapi_spreadd(
    target_influencers: List[Dict],
    parsed_query: Dict
) -> List[Dict]:
    """
    Legacy wrapper for "SerpAPI + Spreadd" combined flow.
    Refactored to use the new services sequentially.
    """
    logger.info("👉 Using refactored scraper_a_serpapi_spreadd (SerpAPI -> Spreadd)")
    
    # 1. Run SerpAPI Only
    results = await scraper_a_serpapi_only(target_influencers, parsed_query)
    
    # 2. Enrich with Spreadd Parallel
    if results:
        await run_spreadd_parallel(results)
        
    return results


# ============================================================================
# EXPORTS (Facade)
# ============================================================================

__all__ = [
    "AsyncSpreaddChecker",
    "run_spreadd_parallel",
    "scraper_a_serpapi_only",
    "scraper_a_serpapi_spreadd",
    "discover_influencers_from_prompt",
    "_extract_username_from_url",
    "_extract_rate_range", 
    "_extract_snippet_metrics"
]

# ============================================================================
# NEW: ENRICHMENT ONLY HELPER (For Background Jobs)
# ============================================================================

async def run_enrichment_only(profiles: List[Dict]) -> List[Dict]:
    """
    Run only the enrichment phase (e.g. Spreadd) on a list of profiles.
    Used by background workers to refresh data without re-searching.
    """
    if not profiles:
        return []

    logger.info(f"Background Enrichment: Processing {len(profiles)} profiles")
    
    # 1. Run Spreadd (Authenticity Check)
    await run_spreadd_parallel(profiles)
    
    # 2. Add other enrichments (BrightData, etc.) here in future
    
    return profiles

__all__.append("run_enrichment_only")
