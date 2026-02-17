from __future__ import annotations

import json
import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dotenv import load_dotenv
from app.config.settings import settings
from app.services.core.search_filters import (
    format_number,
    calculate_avg_metric,
    calculate_rate,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env")

# Use settings module for consistency (it handles .env loading properly)
BRIGHTDATA_API_KEY = settings.BRIGHTDATA_API_KEY
BRIGHTDATA_DATASET_ID = settings.BRIGHTDATA_DATASET_ID
BRIGHTDATA_API_BASE = settings.BRIGHTDATA_API_BASE
BRIGHTDATA_SCRAPE_PATH = settings.BRIGHTDATA_SCRAPE_PATH
BRIGHTDATA_TRIGGER_PATH = settings.BRIGHTDATA_TRIGGER_PATH
BRIGHTDATA_TIMEOUT_SECONDS = settings.BRIGHTDATA_TIMEOUT_SECONDS
BRIGHTDATA_TRIGGER_TIMEOUT_SECONDS = getattr(settings, "BRIGHTDATA_TRIGGER_TIMEOUT_SECONDS", 45)  # trigger POST (quick); polling uses BRIGHTDATA_TIMEOUT_SECONDS

# Gemini API key for post analysis
GEMINI_API_KEY = settings.GEMINI_API_KEY

# Construct URLs only if we have dataset_id (otherwise they will be None/invalid)
# Prefer trigger (async): returns snapshot_id immediately, no 1-min sync limit. Then poll snapshot.
if BRIGHTDATA_DATASET_ID:
    _query = f"dataset_id={BRIGHTDATA_DATASET_ID}&notify=false&include_errors=true"
    BRIGHTDATA_SCRAPE_URL = f"{BRIGHTDATA_API_BASE.rstrip('/')}{BRIGHTDATA_SCRAPE_PATH}?{_query}"
    BRIGHTDATA_TRIGGER_URL = f"{BRIGHTDATA_API_BASE.rstrip('/')}{BRIGHTDATA_TRIGGER_PATH}?{_query}"
else:
    BRIGHTDATA_SCRAPE_URL = None
    BRIGHTDATA_TRIGGER_URL = None
# Legacy name for code that still references BRIGHTDATA_URL
BRIGHTDATA_URL = BRIGHTDATA_SCRAPE_URL

logger = logging.getLogger(__name__)


# ============================================================================
# OPENAI LOCATION SEARCH
# ============================================================================

def _search_location_with_openai(influencer_name: str, username: str = None, profile_url: str = None) -> Optional[str]:
    """
    Use OpenAI to search for the influencer's location based on their name, username, or URL.
    
    Args:
        influencer_name: The influencer's name (e.g., "Leonardo DiCaprio")
        username: Instagram username (e.g., "leonardodicaprio")
        profile_url: Instagram profile URL
    
    Returns:
        Location string (e.g., "Los Angeles, California, USA") or None if not found
    """
    try:
        from app.services.llm.openai_utils import get_openai_client, get_openai_model
        client = get_openai_client()
        model = get_openai_model()
        
        # Build search query
        search_terms = []
        if influencer_name and influencer_name.strip():
            search_terms.append(influencer_name.strip())
        if username and username.strip():
            search_terms.append(f"@{username.strip()}")
        if profile_url and profile_url.strip():
            search_terms.append(profile_url.strip())
        
        if not search_terms:
            logger.warning("⚠️ No search terms provided for location search")
            return None
        
        search_query = " ".join(search_terms)
        
        prompt = f"""You are an expert at finding accurate location information for public figures and influencers.

Given this information: {search_query}

Find the PRIMARY location where this person is based or lives. This could be:
- Their current city and country (e.g., "Los Angeles, California, USA")
- Their hometown (e.g., "Mumbai, Maharashtra, India")
- Their country if they're a national figure (e.g., "USA" or "India")

IMPORTANT RULES:
- Return ONLY the location name, nothing else
- Use format: "City, State/Province, Country" or "City, Country" or just "Country" if specific city is unknown
- Be accurate - use real, verifiable information
- If you cannot find reliable location information, return "Unknown"
- Do NOT guess or make up locations

Respond with ONLY the location string, no additional text or explanation."""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert at finding accurate location information. Return only the location name."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=100
        )
        
        location = response.choices[0].message.content.strip()
        
        # Clean up the response
        location = location.strip('"').strip("'").strip()
        
        # Validate location is not empty or generic
        if location and location.lower() not in ['unknown', 'n/a', 'not found', 'none', '']:
            # Check if it's still the default "India" - if so, try to get more specific
            if location.lower() == 'india':
                logger.debug(f"   ⚠️ Location search returned generic 'India' for {search_query}, trying more specific search")
                # Try a more specific search
                specific_prompt = f"""Find the specific city or state in India where this person is from: {search_query}
                
Return format: "City, State, India" or "City, India" or just "India" if no specific city found.
Return ONLY the location, nothing else."""
                
                specific_response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": "You are an expert at finding specific location information in India."},
                        {"role": "user", "content": specific_prompt}
                    ],
                    temperature=0.1,
                    max_tokens=100
                )
                specific_location = specific_response.choices[0].message.content.strip().strip('"').strip("'").strip()
                if specific_location and specific_location.lower() not in ['unknown', 'n/a', 'not found', 'none', '']:
                    location = specific_location
            
            logger.info(f"✅ OpenAI found location for {search_query}: {location}")
            return location
        else:
            logger.warning(f"⚠️ OpenAI location search returned empty/invalid result for {search_query}")
            return None
            
    except Exception as e:
        logger.warning(f"⚠️ OpenAI location search failed for {search_query}: {e}")
        return None


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

# Using imports from search_filters instead of local compatibility wrapper
from app.services.core.search_filters import (
    extract_username_from_url as _extract_username_from_url,
    normalize_profile_url,
    normalize_instagram_url
)



# ============================================================================
# BRIGHTDATA SCRAPER (format_number, calculate_avg_metric, calculate_rate from search_filters)
# ============================================================================

def _log_brightdata_error_details(status_code: int, error_text: str) -> None:
    """Log BrightData API error details per official docs (troubleshooting)."""
    error_lower = (error_text or "").lower()
    if status_code == 400:
        if "customer is not active" in error_lower or "not active" in error_lower:
            logger.error("ISSUE: BrightData account is not active! Check dashboard and subscription.")
        elif "unauthorized" in error_lower or "invalid" in error_lower or "authentication" in error_lower:
            logger.error("ISSUE: Authentication failed. Verify API key in BrightData dashboard.")
        elif "dataset" in error_lower or "dataset_id" in error_lower:
            logger.error("ISSUE: Dataset configuration problem. Verify dataset_id and dataset access.")
        else:
            logger.error("ISSUE: Bad Request. Check request format, dataset_id, or API key.")
    elif status_code == 401:
        logger.error("ISSUE: Unauthorized. Verify API key and permissions.")
    elif status_code == 403:
        logger.error("ISSUE: Forbidden. Check account permissions and subscription.")
    elif status_code == 404:
        logger.error("ISSUE: Dataset or snapshot not found. Verify dataset_id.")
    elif status_code == 429:
        logger.error("ISSUE: Rate limit or too many parallel jobs. Wait or reduce concurrency.")


def scraper_b_csv_brightdata(influencers: List[Dict[str, str]], parsed_query: Dict, skip_ai_processing: bool = False) -> List[Dict]:
    """
    Scraper B – BrightData enrichment for CSV influencers
    Fully stable version with NDJSON support + required default fields.
    """

    if not influencers:
        logger.warning("⚠ No influencers provided")
        return []

    # Extract and normalize URLs from influencer entries
    # BrightData requires full Instagram URLs: https://www.instagram.com/username/
    url_list = []
    influencer_map = {}  # Map normalized URLs to influencer data for later merging

    # normalize_profile_url and normalize_instagram_url are now imported from search_filters
    # Local definitions removed to prevent duplication


    for inf in influencers:
        # Support both 'profile_url' and 'profile_link' fields
        profile_url_raw = inf.get('profile_url') or inf.get('profile_link') or inf.get('url')

        if not profile_url_raw:
            logger.warning(f"Skipping influencer {inf.get('name', 'unknown')}: no profile_url/profile_link found")
            continue

        # Normalize for BrightData API (with www.)
        normalized_url = normalize_instagram_url(profile_url_raw)

        if normalized_url:
            url_list.append(normalized_url)
            # Store with normalized key (without www.) for matching later
            normalized_key = normalize_profile_url(profile_url_raw)
            if normalized_key:
                influencer_map[normalized_key] = inf
            logger.debug(f"Normalized URL: {profile_url_raw} → {normalized_url}")
        else:
            logger.warning(f"Skipping influencer {inf.get('name', 'unknown')}: could not normalize URL '{profile_url_raw}'")

    if not url_list:
        logger.warning("⚠ No valid URLs found")
        return []

    # Validate configuration before making API call
    if not BRIGHTDATA_API_KEY:
        logger.error("❌ BRIGHTDATA_API_KEY is not set in environment variables")
        logger.error("   Check your .env file for BRIGHTDATA_API_KEY")
        return []
    if not BRIGHTDATA_DATASET_ID:
        logger.error("❌ BRIGHTDATA_DATASET_ID is not set in environment variables")
        logger.error("   Check your .env file for BRIGHTDATA_DATASET_ID")
        return []
    if not BRIGHTDATA_TRIGGER_URL:
        logger.error("❌ BRIGHTDATA_TRIGGER_URL could not be constructed (missing dataset_id)")
        return []
    
    logger.info(f"Sending {len(url_list)} URLs to BrightData")
    logger.debug(f"   URLs to process: {url_list[:5]}{'...' if len(url_list) > 5 else ''}")
    
    # Log configuration (mask sensitive data)
    api_key_preview = f"{BRIGHTDATA_API_KEY[:10]}...{BRIGHTDATA_API_KEY[-5:]}" if len(BRIGHTDATA_API_KEY) > 15 else "TOO_SHORT"
    logger.debug(f"   API Key: {api_key_preview}")
    logger.debug(f"   Dataset ID: {BRIGHTDATA_DATASET_ID}")
    logger.debug(f"   API Base: {BRIGHTDATA_API_BASE}")
    logger.debug(f"   Scrape Path: {BRIGHTDATA_SCRAPE_PATH}")
    logger.debug(f"   Trigger URL: {BRIGHTDATA_TRIGGER_URL}")

    # Prepare headers and data for synchronous POST request
    # Format: {"input": [{"url": "https://www.instagram.com/username"}, ...]}
    headers = {
        "Authorization": f"Bearer {BRIGHTDATA_API_KEY}",
        "Content-Type": "application/json"
    }

    # Format URLs as array of objects with "url" field (BrightData API format)
    input_data = [{"url": url} for url in url_list]
    # Async trigger endpoint expects body = raw array; sync scrape expects {"input": array}
    trigger_body = json.dumps(input_data)

    logger.info(f"📤 Scraping {len(url_list)} profiles...")
    logger.info(f"   API Endpoint (async trigger): {BRIGHTDATA_TRIGGER_URL}")
    logger.info(f"   Profiles to scrape: {', '.join([_extract_username_from_url(u) or u for u in url_list[:5]])}{'...' if len(url_list) > 5 else ''}")

    # ----------------------------------------------------
    # STEP 1: Trigger async job (official docs: use /trigger to avoid 1-min sync limit)
    # https://docs.brightdata.com/api-reference/web-scraper-api/synchronous-requests
    # Sync /scrape has 1-minute server timeout; trigger returns snapshot_id immediately.
    # ----------------------------------------------------
    try:
        logger.info("🔄 Calling BrightData API (async trigger)...")
        trigger_response = requests.post(
            BRIGHTDATA_TRIGGER_URL,
            headers=headers,
            data=trigger_body,
            timeout=BRIGHTDATA_TRIGGER_TIMEOUT_SECONDS
        )

        logger.info(f"📡 BrightData trigger response: Status {trigger_response.status_code}")
        logger.debug(f"   Response headers: {dict(trigger_response.headers)}")

        snapshot_id = None
        if trigger_response.status_code == 200:
            try:
                rj = trigger_response.json()
                snapshot_id = rj.get("snapshot_id") or rj.get("id") or rj.get("job_id")
                if snapshot_id:
                    logger.info(f"   📋 Snapshot ID: {snapshot_id} (polling for results...)")
            except Exception as e:
                logger.debug(f"   Could not parse trigger response JSON: {e}")
        elif trigger_response.status_code == 202:
            # Sync scrape sometimes returns 202 when over 1 min; same handling
            try:
                rj = trigger_response.json()
                snapshot_id = rj.get("snapshot_id") or rj.get("id") or rj.get("job_id")
                if snapshot_id:
                    logger.info(f"   📋 Snapshot ID (202): {snapshot_id}")
            except Exception as e:
                logger.debug(f"   Could not parse 202 response JSON: {e}")

        if not snapshot_id:
            error_text = (trigger_response.text or "")[:500]
            logger.error("="*70)
            logger.error(f"❌ BRIGHTDATA: Trigger failed or no snapshot_id - Status {trigger_response.status_code}")
            logger.error(f"   Response: {error_text}")
            logger.error("   Action: Falling back to discovery/Spreadd data only")
            logger.error("="*70)
            if trigger_response.status_code in (400, 401, 403, 404, 429):
                _log_brightdata_error_details(trigger_response.status_code, error_text)
            return []

        # ----------------------------------------------------
        # STEP 2: Poll snapshot until ready (per official docs: poll GET /datasets/v3/snapshot/:snapshot_id)
        # Snapshot may take 1–3+ min for large batches; use longer poll window.
        # ----------------------------------------------------
        snapshot_url = f"{BRIGHTDATA_API_BASE}/datasets/v3/snapshot/{snapshot_id}?format=json"
        logger.info("🔄 Polling snapshot endpoint until ready...")
        max_retries = 16
        retry_delay = 15
        response = None
        for attempt in range(1, max_retries + 1):
            logger.info(f"   ⏳ Waiting {retry_delay}s before poll {attempt}/{max_retries}...")
            time.sleep(retry_delay)

            try:
                poll_response = requests.get(
                    snapshot_url,
                    headers=headers,
                    timeout=BRIGHTDATA_TIMEOUT_SECONDS
                )
                logger.info(f"   📡 Snapshot poll status: {poll_response.status_code}")

                if poll_response.status_code == 200:
                    # Check for "still building" message in body (docs: status "building", try again in 10s)
                    try:
                        body = poll_response.json()
                        if isinstance(body, dict):
                            msg = (body.get("message") or body.get("status") or "")
                            if "building" in str(msg).lower() or "not ready" in str(msg).lower():
                                logger.info(f"   ⏳ Snapshot still building (attempt {attempt}/{max_retries})...")
                                if attempt == max_retries:
                                    logger.warning("   ⚠️ Snapshot not ready after max polls")
                                    return []
                                continue
                    except Exception:
                        pass
                    logger.info(f"   ✅ Snapshot ready after ~{attempt * retry_delay}s")
                    response = poll_response
                    break
                elif poll_response.status_code in (202, 204):
                    logger.info(f"   ⏳ Still processing (attempt {attempt}/{max_retries})...")
                    if attempt == max_retries:
                        logger.warning("   ⚠️ Snapshot not ready after max polls")
                        return []
                elif poll_response.status_code == 404:
                    logger.warning(f"   ⚠️ Snapshot {snapshot_id} not found (404)")
                    return []
                else:
                    logger.error(f"   ❌ Snapshot error: {poll_response.status_code} - { (poll_response.text or '')[:300]}")
                    return []
            except requests.exceptions.Timeout:
                logger.warning(f"   ⏳ Poll {attempt} timed out")
                if attempt == max_retries:
                    return []
            except Exception as e:
                logger.warning(f"   ⏳ Poll {attempt} failed: {e}")
                if attempt == max_retries:
                    return []

        if response is None:
            logger.warning("   ⚠️ Snapshot not ready after all polls")
            return []

        # ----------------------------------------------------
        # STEP 3: Parse snapshot response (same as before)
        # ----------------------------------------------------
        if response.status_code != 200:
            error_text = response.text[:2000] if response.text else "No error message"
            content_type = response.headers.get('Content-Type', 'unknown')
            logger.error("="*70)
            logger.error(f"❌ BRIGHTDATA: API ERROR - Status {response.status_code}")
            logger.error("="*70)
            logger.error(f"   Content-Type: {content_type}")
            logger.error(f"   Response: {error_text}")
            logger.error(f"   Action: Falling back to Spreadd data only")
            logger.error("="*70)

            # Check for specific error messages
            if response.status_code == 400:
                error_lower = error_text.lower()
                if "customer is not active" in error_lower or "not active" in error_lower:
                    logger.error("ISSUE: BrightData account is not active!")
                    logger.error("SOLUTION: Log into BrightData dashboard and check:")
                    logger.error("   • Account status (should be 'Active')")
                    logger.error("   • Subscription/trial status")
                    logger.error("   • API token permissions")
                    logger.error("   • Zone configuration (if using SDK)")
                    logger.error(f"   • Dataset ID being used: {BRIGHTDATA_DATASET_ID}")
                    logger.error(f"   • API Base URL: {BRIGHTDATA_API_BASE}")
                    logger.error(f"   • Scrape Path: {BRIGHTDATA_SCRAPE_PATH}")
                    logger.error("   • Try regenerating API token in BrightData dashboard")
                    logger.error("   • Verify dataset_id exists and is accessible")
                elif "unauthorized" in error_lower or "invalid" in error_lower or "authentication" in error_lower:
                    logger.error("ISSUE: Authentication failed (400)")
                    logger.error("SOLUTION: Check API key format and validity")
                    logger.error(f"   • API Key format: {BRIGHTDATA_API_KEY[:10]}...{BRIGHTDATA_API_KEY[-5:] if len(BRIGHTDATA_API_KEY) > 15 else 'SHORT'}")
                    logger.error("   • Verify API key in BrightData dashboard")
                    logger.error("   • Check if API key has proper permissions for dataset scraping")
                elif "dataset" in error_lower or "dataset_id" in error_lower:
                    logger.error("ISSUE: Dataset configuration problem (400)")
                    logger.error(f"SOLUTION: Verify dataset_id is correct: {BRIGHTDATA_DATASET_ID}")
                    logger.error("   • Check dataset exists in BrightData dashboard")
                    logger.error("   • Verify dataset is configured for Instagram scraping")
                    logger.error("   • Check dataset permissions for your account")
                else:
                    logger.error("ISSUE: Bad Request (400)")
                    logger.error("Check: Request format, dataset_id, or API key validity")
                    logger.error(f"   Full error: {error_text[:500]}")
            elif response.status_code == 401:
                logger.error("ISSUE: Unauthorized (401)")
                logger.error("SOLUTION: Verify API key is correct and has proper permissions")
            elif response.status_code == 403:
                logger.error("ISSUE: Forbidden (403)")
                logger.error("SOLUTION: Check account permissions and subscription status")
            elif response.status_code == 429:
                logger.error("ISSUE: Rate limit exceeded (429)")
                logger.error("SOLUTION: Wait before retrying or upgrade plan")

            return []

        # Robust JSON/NDJSON parsing with fallback
        raw = response.text.strip()
        brightdata_results = []

        try:
            # Try normal JSON parse first
            results_data = response.json()

            # DEBUG: Log the actual response structure
            logger.info(f"🔍 DEBUG: Response type: {type(results_data)}")
            logger.info(f"🔍 DEBUG: Response top-level keys: {list(results_data.keys()) if isinstance(results_data, dict) else 'Not a dict'}")

            def _looks_scraped(record: Dict) -> bool:
                return any(
                    k in record
                    for k in ['account', 'followers', 'profile_url', 'profile_image_link', 'posts', 'biography']
                )

            # Handle common structures, preferring scraped data over echoed input
            if isinstance(results_data, list):
                brightdata_results = results_data
            elif isinstance(results_data, dict):
                # Prefer explicit result containers first
                if 'data' in results_data and isinstance(results_data['data'], list):
                    brightdata_results = results_data['data']
                elif 'results' in results_data and isinstance(results_data['results'], list):
                    brightdata_results = results_data['results']
                # If the whole dict already looks like a scraped profile, keep it
                elif _looks_scraped(results_data):
                    brightdata_results = [results_data]
                # Some APIs wrap the scraped object under another key; try to collect list-like values
                else:
                    maybe = []
                    for v in results_data.values():
                        if isinstance(v, list):
                            maybe.extend(v)
                    if maybe and any(_looks_scraped(v) for v in maybe if isinstance(v, dict)):
                        brightdata_results = maybe
                    elif 'input' in results_data:
                        # Only fall back to echoed input if nothing scraped was found
                        input_data = results_data['input']
                        if isinstance(input_data, list):
                            brightdata_results = input_data
                        elif isinstance(input_data, dict):
                            brightdata_results = (
                                input_data.get('url', [])
                                if isinstance(input_data.get('url'), list)
                                else [input_data]
                            )
                        else:
                            brightdata_results = [input_data] if input_data else []
                    else:
                        # Last resort: treat top-level dict as single record
                        brightdata_results = [results_data]
        except (ValueError, json.JSONDecodeError):
            # Not standard JSON — try NDJSON: split lines and parse each line
            logger.debug("BrightData response is not standard JSON, trying NDJSON parsing...")
            brightdata_results = []
            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    brightdata_results.append(json.loads(line))
                except (ValueError, json.JSONDecodeError):
                    # Ignore invalid NDJSON lines but log
                    logger.debug(f"Skipping invalid NDJSON line (truncated): {line[:200]}")

        logger.info(f"📥 BrightData API Response: Received {len(brightdata_results)} result(s)")
        logger.debug(f"   Response type: {type(brightdata_results).__name__}")

        # CRITICAL: Check if BrightData is actually returning data or just echoing input
        url_only = [
            (len(r.keys()) == 1 and 'url' in r)
            for r in brightdata_results
            if isinstance(r, dict)
        ]
        if url_only and all(url_only):
            logger.error("="*70)
            logger.error("❌ BRIGHTDATA: NO DATA RECEIVED - Only returning input URL")
            logger.error("="*70)
            logger.error(f"   Dataset ID: {BRIGHTDATA_DATASET_ID}")
            logger.error("   Status: BrightData dataset is NOT scraping Instagram profiles")
            logger.error("   Issue: Dataset is only echoing the input URL, no profile data")
            logger.error("   Solution: Configure your BrightData dataset to scrape Instagram profile data")
            logger.error("   Action: Falling back to Spreadd data only")
            logger.error("="*70)
            return []  # Return empty - merge will use Spreadd data
        
        # Check if we have actual data
        has_data_count = 0
        no_data_count = 0
        for idx, result in enumerate(brightdata_results, 1):
            if isinstance(result, dict):
                # Check for key data fields
                has_followers = result.get('followers') not in [None, 0, '', 'N/A']
                has_biography = result.get('biography') not in [None, '', 'N/A']
                has_posts = bool(result.get('posts'))
                has_account = bool(result.get('account'))
                
                if has_followers or has_biography or has_posts or has_account:
                    has_data_count += 1
                    posts_list = result.get('posts') or []
                    logger.info(f"   ✅ Result {idx}: HAS DATA - followers={result.get('followers', 'N/A')}, biography={'Yes' if has_biography else 'No'}, posts={len(posts_list)}")
                else:
                    no_data_count += 1
                    logger.warning(f"   ⚠️ Result {idx}: NO DATA - only has keys: {list(result.keys())[:10]}")
        
        # Summary logging
        logger.info("="*70)
        if has_data_count > 0:
            logger.info(f"✅ BRIGHTDATA: SUCCESS - {has_data_count}/{len(brightdata_results)} profile(s) have data")
            if no_data_count > 0:
                logger.warning(f"   ⚠️ {no_data_count} profile(s) returned without data")
        else:
            logger.error(f"❌ BRIGHTDATA: FAILED - No data received for any profile")
            logger.error("   All results are empty or only contain URL")
        logger.info("="*70)


        # Process the results
        results: List[Dict] = []

        # Process each result and merge with influencer data
        for idx, brightdata_data in enumerate(brightdata_results, 1):
            # Try to find matching influencer by URL (with normalization)
            profile_url_raw = brightdata_data.get('profile_url') or brightdata_data.get('url') or ''
            profile_url = normalize_profile_url(profile_url_raw)

            if not profile_url:
                # If no URL in response, try to match by index
                if idx <= len(url_list):
                    profile_url_raw = url_list[idx - 1]
                    profile_url = normalize_profile_url(profile_url_raw)
                else:
                    logger.warning(f"[{idx}/{len(brightdata_results)}] Cannot match result to influencer, skipping...")
                    continue

            # Try normalized URL match first
            inf = influencer_map.get(profile_url, {})

            # Fallback: try extract username and match by username (case-insensitive)
            if not inf:
                uname = _extract_username_from_url(profile_url_raw) or _extract_username_from_url(brightdata_data.get('url', '') or '')
                if uname:
                    inf = next((v for v in influencer_map.values() if (v.get('username', '').lower() == uname.lower())), {})
                    if inf:
                        logger.debug(f"Matched by username fallback: @{uname}")

            if not inf:
                logger.warning(f"[{idx}/{len(brightdata_results)}] Cannot match result to influencer (URL: {profile_url_raw}), skipping...")
                continue
            username = inf.get("username") or brightdata_data.get('username') or _extract_username_from_url(profile_url_raw) or f"user_{idx}"
            name = inf.get("name") or brightdata_data.get('account') or username
            profile_link = inf.get("profile_link") or inf.get("profile_url") or profile_url_raw

            # Use `or 0` pattern to handle explicitly stored None values
            followers = brightdata_data.get('followers') or 0
            followers_formatted = format_number(followers) if isinstance(followers, (int, float)) else str(followers)

            # Calculate engagement rate
            # BrightData returns avg_engagement already as a percentage value
            # e.g., 0.65 means 0.65%, 48.63 means 48.63%
            # DO NOT multiply by 100 - use as-is
            # Use `or 0` pattern to handle explicitly stored None values
            avg_engagement = brightdata_data.get('avg_engagement') or 0
            if isinstance(avg_engagement, (int, float)) and avg_engagement > 0:
                engagement_rate = f"{avg_engagement:.2f}%"
            else:
                engagement_rate = str(avg_engagement) if avg_engagement else "N/A"

            # Extract profile picture from BrightData response (support multiple possible keys)
            def _first_non_empty(data: Dict, keys: list[str]):
                for k in keys:
                    val = data.get(k)
                    if val not in [None, "", "N/A"]:
                        return val
                return None

            def _find_value_by_key_pattern(obj, patterns):
                """Recursively search for the first non-empty value whose key matches any pattern."""
                try:
                    if isinstance(obj, dict):
                        for k, v in obj.items():
                            if any(p.lower() in str(k).lower() for p in patterns):
                                if v not in [None, "", "N/A"]:
                                    return v
                            # Recurse into nested structures
                            nested = _find_value_by_key_pattern(v, patterns)
                            if nested not in [None, "", "N/A"]:
                                return nested
                    elif isinstance(obj, list):
                        for item in obj:
                            nested = _find_value_by_key_pattern(item, patterns)
                            if nested not in [None, "", "N/A"]:
                                return nested
                except Exception:
                    pass
                return None

            profile_pic_url = _first_non_empty(brightdata_data, [
                'profile_image_link',
                'profile_pic_url',
                'profile_pic',
                'profile_image',
                'profile_picture',
                'profile_picture_url',
                'image_url',
                'avatar',
            ])
            if not profile_pic_url:
                profile_pic_url = _find_value_by_key_pattern(brightdata_data, ['image', 'avatar', 'picture', 'photo'])

            # Fallback to existing influencer image when BrightData lacks one
            if not profile_pic_url:
                profile_pic_url = (
                    inf.get("profile_pic_url")
                    or inf.get("profile_image")
                    or inf.get("image")
                )
            if not profile_pic_url:
                logger.debug(
                    f"⚠ BrightData missing profile_image for @{username}. "
                    f"Keys present: {list(brightdata_data.keys())}"
                )

            # Derive NICHE and Location from profile data rather than poisoning
            # them with the parsed_query values. This prevents cases where a
            # generic influencer (e.g. Selena Gomez) is incorrectly tagged as a
            # highly specific query niche (e.g. "Cricket") and slipping through
            # niche from profile data.
            niche_value = (
                inf.get("NICHE")
                or inf.get("niche")
                or brightdata_data.get('business_category_name')
                or brightdata_data.get('category_name')
                or ''
            )
            # OPTIMIZED: Skip AI processing during enrichment if requested (will be done later for top N only)
            location_value = (
                inf.get("Location")
                or inf.get("location")
            )
            
            # Only do location search if skip_ai_processing is False (for backward compatibility)
            if not skip_ai_processing:
                # If location is missing or is the default "India", search for it using OpenAI
                if not location_value or location_value in ['India', 'N/A', 'Unknown', '']:
                    logger.info(f"   🔍 Location missing or default for @{username}, searching with OpenAI...")
                    openai_location = _search_location_with_openai(
                        influencer_name=name or username,
                        username=username,
                        profile_url=profile_link
                    )
                    if openai_location:
                        location_value = openai_location
                        logger.info(f"   ✅ Updated location for @{username}: {location_value}")
                    else:
                        # Fallback to parsed_query location only if OpenAI search failed
                        location_value = parsed_query.get('location', 'Unknown')
                        logger.warning(f"   ⚠️ OpenAI location search failed for @{username}, using fallback: {location_value}")
                else:
                    logger.debug(f"   ✅ Using existing location for @{username}: {location_value}")
            else:
                # Use fallback location if AI processing is skipped
                if not location_value or location_value in ['India', 'N/A', 'Unknown', '']:
                    location_value = parsed_query.get('location', 'Unknown')
                    logger.debug(f"   ⏭️ Skipping location search for @{username} (will process later for top N)")

            biography_val = _first_non_empty(brightdata_data, [
                'biography',
                'bio',
                'profile_biography',
                'description',
                'about',
            ]) or 'N/A'
            if biography_val in [None, "", "N/A"]:
                biography_val = _find_value_by_key_pattern(brightdata_data, ['bio', 'about', 'description'])
            if biography_val in [None, "", "N/A"]:
                biography_val = inf.get("biography") or inf.get("bio") or 'N/A'
            if not biography_val:
                biography_val = 'N/A'
            if biography_val in [None, "", "N/A"]:
                logger.debug(
                    f"⚠ BrightData missing biography for @{username}. "
                    f"Keys present: {list(brightdata_data.keys())}"
                )

            # DEBUG: Log what we're extracting from BrightData
            logger.debug(f"   🔍 Extracting for @{username}:")
            logger.debug(f"      → biography from BD: {biography_val[:50] if biography_val and biography_val != 'N/A' else 'N/A'}...")
            from app.services.legacy.brightdata import extract_posts_and_count
            posts_for_display, posts_count_val = extract_posts_and_count(brightdata_data)
            posts_data = brightdata_data.get('posts') or []  # raw for calculate_avg_metric
            logger.debug(f"      → posts from BD: {len(posts_data)} items")
            logger.debug(f"      → niche_value: {niche_value}")
            logger.debug(f"      → location_value: {location_value}")

            # Handle None values for following - CRITICAL FIX
            following_val = brightdata_data.get('following')
            if following_val is None or following_val == 'N/A':
                following_formatted = 'N/A'
            elif isinstance(following_val, (int, float)):
                following_formatted = format_number(following_val)
            else:
                following_formatted = str(following_val) if following_val not in (None, '', 'N/A') else 'N/A'
            
            # Handle None values for highlights_count - CRITICAL FIX
            highlights_count_val = brightdata_data.get('highlights_count')
            if highlights_count_val is None or highlights_count_val == 'N/A':
                highlights_count_val = 0
            else:
                try:
                    if isinstance(highlights_count_val, (int, float)):
                        highlights_count_val = int(highlights_count_val)
                    elif isinstance(highlights_count_val, str):
                        highlights_count_str = highlights_count_val.strip().replace(',', '').replace('+', '')
                        if highlights_count_str and highlights_count_str.upper() != 'N/A':
                            highlights_count_val = int(float(highlights_count_str))
                        else:
                            highlights_count_val = 0
                    else:
                        highlights_count_val = 0
                except (TypeError, ValueError):
                    highlights_count_val = 0
            
            merged = {
                "NAME": brightdata_data.get('account', name),
                "Id": username,
                "PROFILE_LINK": brightdata_data.get('profile_url', profile_link),
                "profile_pic_url": profile_pic_url,
                "profile_image": profile_pic_url,
                "image": profile_pic_url,
                "platform": "instagram",
                "followers": followers_formatted,
                "following": following_formatted,
                "posts_count": posts_count_val,
                "average_likes": calculate_avg_metric(posts_data, 'likes'),
                "average_comments": calculate_avg_metric(posts_data, 'comments'),
                "engagement_rate": engagement_rate,
                "is_verified": brightdata_data.get('is_verified', False),
                "is_business_account": brightdata_data.get('is_business_account', False),
                "is_professional_account": brightdata_data.get('is_professional_account', False),
                "biography": biography_val,
                "external_url": (brightdata_data.get('external_url') or ['N/A'])[0] if isinstance(brightdata_data.get('external_url'), list) else (brightdata_data.get('external_url') or 'N/A'),
                "business_category_name": brightdata_data.get('business_category_name', 'N/A'),
                "category_name": brightdata_data.get('category_name', 'N/A'),
                "highlights_count": highlights_count_val,
                "is_joined_recently": brightdata_data.get('is_joined_recently', False),
                "real_followers_percentage": str(brightdata_data.get('real_followers_percentage', brightdata_data.get('real_followers_pct', brightdata_data.get('authentic_followers_pct', 'N/A')))),
                "suspicious_followers_percentage": str(brightdata_data.get('suspicious_followers_percentage', brightdata_data.get('suspicious_followers_pct', brightdata_data.get('fake_followers_pct', 'N/A')))),
                "Location": location_value or "N/A",
                "niche_hint": inf.get("niche_hint", parsed_query.get('niche', '')),  # Keep for discovery, not identity
                "location_hint": inf.get("location_hint", parsed_query.get('location', '')),
                "RATE": calculate_rate(followers_formatted),
                "posts": posts_for_display,  # Normalized for UI: image_url, caption, likes, comments, etc.
                "source": "csv_brightdata"
            }
            
            # -------------------------------------------------------------------------
            # IDENTITY RESOLUTION (canonical helper – safe from sync/async contexts)
            # -------------------------------------------------------------------------
            if not skip_ai_processing:
                try:
                    from app.services.analysis.industry_standards import run_identity_resolution_sync
                    identity = run_identity_resolution_sync(
                        profile_url=profile_link,
                        username=username,
                        full_name=merged.get("NAME"),
                        biography=merged.get("biography"),
                        external_url=merged.get("external_url"),
                        timeout_seconds=10,
                    )
                    merged["NICHE"] = identity["profession"]
                    merged["identity_confidence"] = identity["confidence"]
                    merged["identity_source"] = identity["source"]
                    merged["identity_reason"] = identity.get("reason", "")
                except Exception as e:
                    logger.warning("Identity resolution failed for @%s: %s", username, e)
                    merged["NICHE"] = niche_value or "Digital Creator"
                    merged["identity_confidence"] = 0.0
                    merged["identity_source"] = "error_fallback"
                    merged["identity_reason"] = str(e)
            else:
                # Use basic niche from scraped data if AI processing is skipped
                merged["NICHE"] = niche_value or "Digital Creator"
                merged["identity_confidence"] = 0.0
                merged["identity_source"] = "deferred"
                merged["identity_reason"] = "Will be processed later for top N"
                logger.debug(f"   ⏭️ Skipping identity resolution for @{username} (will process later for top N)")

            # 🆕 ADD POST ANALYSIS & HASHTAG METRICS
            # OPTIMIZED: Skip post analysis if skip_ai_processing is True (will be done later for top N only)
            if not skip_ai_processing:
                from app.services.analysis.post_analysis import add_post_metrics_to_result
                
                # Get Gemini client for post analysis (if API key is available)
                gemini_client = None
                if GEMINI_API_KEY and GEMINI_API_KEY.strip():
                    try:
                        from google import genai
                        import os
                        api_key = GEMINI_API_KEY.strip()
                        # Set API key in environment (for compatibility)
                        os.environ["GEMINI_API_KEY"] = api_key
                        # Pass API key directly to Client constructor (required by newer SDK)
                        gemini_client = genai.Client(api_key=api_key)
                        logger.debug(f"   ✅ Gemini client initialized for post analysis")
                    except Exception as client_error:
                        logger.warning(f"   ⚠️ Could not initialize Gemini client for post analysis: {client_error}")
                        gemini_client = None
                else:
                    logger.debug(f"   ⚠️ GEMINI_API_KEY not set or empty, skipping post analysis")
                
                try:
                    merged = add_post_metrics_to_result(merged, gemini_client)
                    if gemini_client:
                        # Check if post analysis was actually successful
                        post_analysis = merged.get("post_analysis", {})
                        if post_analysis.get("post_analysis_available") is True:
                            logger.info(f"   ✅ Post analysis completed for @{username} (Gemini AI)")
                        else:
                            reason = post_analysis.get("reason", "Unknown")
                            logger.debug(f"   ℹ️ Post analysis not available for @{username}: {reason}")
                    else:
                        logger.debug(f"   ✅ Added hashtag analysis for @{username} (LLM analysis skipped - no API key)")
                except Exception as e:
                    logger.warning(f"   ⚠️ Could not add post analysis for @{username}: {e}")
                    # Add empty analysis if failed
                    merged = add_post_metrics_to_result(merged, None)
            else:
                # Add empty post analysis structure if AI processing is skipped
                from app.services.analysis.post_analysis import add_post_metrics_to_result
                merged = add_post_metrics_to_result(merged, None)
                logger.debug(f"   ⏭️ Skipping post analysis for @{username} (will process later for top N)")

            results.append(merged)
            logger.debug(f"   [{idx}/{len(brightdata_results)}] ✅ Processed @{username}: {followers_formatted} followers")

    except requests.exceptions.Timeout:
        logger.error("="*70)
        logger.error(f"❌ BRIGHTDATA: TIMEOUT - Request timed out after {BRIGHTDATA_TIMEOUT_SECONDS}s")
        logger.error("="*70)
        logger.error("   Action: Falling back to Spreadd data only")
        logger.error("="*70)
        return []
    except requests.exceptions.RequestException as e:
        logger.error("="*70)
        logger.error(f"❌ BRIGHTDATA: REQUEST ERROR - {type(e).__name__}: {str(e)}")
        logger.error("="*70)
        logger.error("   Action: Falling back to Spreadd data only")
        logger.error("="*70)
        return []
    except Exception as e:
        logger.error("="*70)
        logger.error(f"❌ BRIGHTDATA: PROCESSING ERROR - {type(e).__name__}: {str(e)}")
        logger.error("="*70)
        logger.error("   Action: Falling back to Spreadd data only")
        logger.error("="*70)
        return []

    # Final summary logging
    logger.info("="*70)
    if len(results) > 0:
        logger.info(f"✅ BRIGHTDATA: SUCCESS - Processed {len(results)} profile(s) with data")
        logger.info(f"   Profiles enriched: {', '.join([r.get('Id', 'unknown') for r in results[:5]])}{'...' if len(results) > 5 else ''}")
    else:
        logger.warning(f"⚠️ BRIGHTDATA: NO RESULTS - {len(brightdata_results)} response(s) but 0 processed")
        logger.warning("   Possible reasons:")
        logger.warning("   • BrightData returned empty/invalid data")
        logger.warning("   • URL matching failed")
        logger.warning("   • No profiles returned")
        logger.warning("   → System will use Spreadd data only")
    logger.info("="*70)
    
    return results
