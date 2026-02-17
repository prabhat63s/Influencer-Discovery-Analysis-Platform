"""
SerpAPI Service
===============
Centralized service for Google Search actions using SerpAPI.
Consolidates "Scraper A" logic for discovering and basic usage metrics.
"""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Dict, List, Optional, Any
import requests

from app.config.settings import settings
from app.services.reporting.monitoring_service import SearchMetrics
from app.services.core.search_filters import (
    extract_snippet_metrics,
    extract_rate_range,
    parse_rate_to_int,
    calculate_rate
)
from app.utils.image_utils import extract_profile_image

logger = logging.getLogger(__name__)

SERP_API_KEY = settings.SERP_API_KEY
SERPAPI_SEARCH_URL = settings.SERPAPI_SEARCH_URL or "https://serpapi.com/search"
SERPAPI_TIMEOUT = int(os.getenv("SERPAPI_TIMEOUT", "20"))


# ============================================================================
# SERPAPI WRAPPER
# ============================================================================

try:
    from serpapi import GoogleSearch as _SerpApiGoogleSearch
except ImportError:
    logger.warning("serpapi library not installed, using REST fallback")
    _SerpApiGoogleSearch = None


class _RequestsGoogleSearch:
    """Minimal robust wrapper around the SerpAPI REST endpoint."""

    def __init__(self, params: Dict):
        self._params = params
        self._serp_api_url = SERPAPI_SEARCH_URL

    def get_dict(self) -> Dict:
        """Execute the search and return the JSON dictionary."""
        try:
            response = requests.get(
                self._serp_api_url,
                params=self._params,
                timeout=SERPAPI_TIMEOUT,
            )
            response.raise_for_status()
            data = response.json()
            
            if "error" in data:
                raise ValueError(f"SerpAPI Error: {data['error']}")
                
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"❌ SerpAPI Connection Error: {e}")
            raise
        except ValueError as e:
            logger.error(f"❌ SerpAPI Data Error: {e}")
            raise


# Factory to get the best available searcher
def get_google_search(params: Dict):
    if _SerpApiGoogleSearch:
        return _SerpApiGoogleSearch(params)
    return _RequestsGoogleSearch(params)


# Alias for callers that use GoogleSearch
class GoogleSearch:
    """Thin wrapper so callers can use GoogleSearch(params).get_dict() like the serpapi library."""

    def __init__(self, params: Dict):
        self._searcher = get_google_search(params)

    def get_dict(self) -> Dict:
        return self._searcher.get_dict()


# ============================================================================
# SCRAPER LOGIC
# ============================================================================

async def scraper_a_serpapi_only(
    influencers: List[Dict[str, str]],
    parsed_query: Dict,
    metrics: Optional[SearchMetrics] = None
) -> List[Dict]:
    """
    Primary Scraper Function (Scraper A).
    Searches Google for each influencer to extract metrics from snippets.
    DOES NOT perform minimal Spreadd checks (that is handled separately).
    """
    if not influencers:
        return []

    if not SERP_API_KEY:
        logger.error("❌ SERP_API_KEY is missing. Cannot run Scraper A.")
        if metrics:
            metrics.add_error("Missing SERP_API_KEY")
        return []

    niche = parsed_query.get('niche') or "General"
    location = parsed_query.get('location') or "India"
    results: List[Dict] = []
    
    # Prepare tasks
    loop = asyncio.get_event_loop()
    serp_tasks = []
    
    logger.info(f"🔍 Scraper A: preparing searches for {len(influencers)} influencers...")

    for inf in influencers:
        username = inf.get("username")
        if not username:
            continue
            
        # Refined query for better snippet extraction
        query = f"{username} instagram {niche} {location}".strip()
        
        serp_params = {
            "api_key": SERP_API_KEY,
            "engine": "google",
            "q": query,
            "location": location,
            "google_domain": "google.co.in",
            "gl": "in",
            "hl": "en",
            "num": 3, # We significantly only need top results for the specific profile
        }
        
        # Create a deferred execution lambda
        task = loop.run_in_executor(None, lambda p=serp_params: get_google_search(p).get_dict())
        serp_tasks.append((inf, serp_params, task))

    if not serp_tasks:
        return []

    if metrics:
        metrics.serpapi_calls += len(serp_tasks)
    
    # Run in parallel
    serp_results_raw = await asyncio.gather(*[t for _, _, t in serp_tasks], return_exceptions=True)

    # Process results
    for idx, ((inf, _, _), serp_data) in enumerate(zip(serp_tasks, serp_results_raw), 1):
        username = inf.get("username")
        name = inf.get("name", username)
        
        extracted_data = {
            "followers_serp": "N/A",
            "following_serp": "N/A",
            "posts_serp": "N/A",
            "min_rate": None,
            "max_rate": None,
            "biography": None
        }
        
        if isinstance(serp_data, Exception):
            logger.warning(f"   ⚠️ Error collecting SerpAPI for {username}: {serp_data}")
        elif "error" in serp_data:
             logger.warning(f"   ⚠️ SerpAPI API Error for {username}: {serp_data['error']}")
        else:
            # Parse organic results
            organic = serp_data.get("organic_results", [])
            if organic:
                # 1. Extract Metrics from snippet
                first_result = organic[0]
                snippet = first_result.get("snippet", "")
                title = first_result.get("title", "")
                
                snippet_metrics = extract_snippet_metrics(snippet)
                extracted_data.update(snippet_metrics)
                
                # 2. Extract Rate
                combined_text = f"{title} {snippet}".strip()
                rate_info = extract_rate_range(combined_text)
                if rate_info:
                    extracted_data.update(rate_info)

                # 3. Extract Biography hint
                extracted_data["biography"] = snippet

        # Normalize Rate Display
        min_rate = extracted_data.get("min_rate")
        max_rate = extracted_data.get("max_rate")
        followers_str = extracted_data.get("followers_serp", "0")
        
        if min_rate is not None:
            primary_rate = min_rate
            rate_display = f"₹{min_rate:,}"
            if max_rate and max_rate != min_rate:
                rate_display = f"₹{min_rate:,} - ₹{max_rate:,}"
        else:
            # Fallback estimation
            primary_rate = parse_rate_to_int(calculate_rate(followers_str))
            rate_display = calculate_rate(followers_str) # Returns string like "₹10k - ₹15k"

        # Image extraction
        combined_source_data = {**inf, **extracted_data}
        if isinstance(serp_data, dict) and "organic_results" in serp_data:
             # Pass full serp data to utility if needed, but usually snippet is enough
             pass
        
        profile_pic_url = extract_profile_image(combined_source_data, username, "serpapi_service")

        # Construct standardized result object
        merged_result = {
            "NAME": name,
            "Id": username,
            "PROFILE_LINK": inf.get("profile_link", f"https://instagram.com/{username}"),
            "profile_pic_url": profile_pic_url,
            "profile_image": profile_pic_url,
            "image": profile_pic_url,
            "platform": "instagram",
            
            # Metrics
            "followers": extracted_data.get("followers_serp", "N/A"),
            "following": extracted_data.get("following_serp", "N/A"),
            "posts_count": extracted_data.get("posts_serp", "N/A"),
            "serp_followers": extracted_data.get("followers_serp"),
            
            # Placeholders for future enrichment
            "average_likes": "N/A",
            "average_comments": "N/A",
            "engagement_rate": "N/A",
            "real_followers_percentage": "N/A",
            "suspicious_followers_percentage": "N/A",
            
            # Meta
            "biography": inf.get("biography") or extracted_data.get("biography") or "N/A",
            "Location": inf.get("location_hint") or inf.get("Location") or "N/A",
            "niche_hint": inf.get("niche_hint", niche),
            "location_hint": inf.get("location_hint", location),
            
            # Rates
            "RATE": rate_display,
            "min_rate": min_rate,
            "max_rate": max_rate,
            "rate": primary_rate,
            
            "source": "csv_serpapi"
        }
        
        results.append(merged_result)
        # Small throttle to be kind to local resources if not hitting API limits
        await asyncio.sleep(0.01)

    logger.info(f"✅ Scraper A (SerpAPI) completed: {len(results)} results")
    return results
