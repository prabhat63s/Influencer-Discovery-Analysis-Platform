from __future__ import annotations

import asyncio
import aiohttp
import json
import logging
import os
import re
import ssl
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from google import genai
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from app.config.settings import settings
from app.services.core.search_filters import (
    format_number,
    calculate_avg_metric,
    calculate_rate,
    parse_rate_to_int,
    parse_followers_to_int,
    extract_username_from_url as _extract_username_from_url,
    extract_rate_range as _extract_rate_range,
    extract_snippet_metrics as _extract_snippet_metrics,
    remove_duplicates,
    sort_results_by_relevance,
    merge_results,
    parse_percentage as _parse_percentage,
    normalize_profile_url,
    location_match,
    extract_usernames_from_urls
)
from app.services.llm.gemini_utils import get_gemini_client, parse_query_with_gemini
from app.services.scrapers.spreadd_service import AsyncSpreaddChecker, run_spreadd_parallel
from app.services.scrapers.serpapi_service import scraper_a_serpapi_only, get_google_search
from app.services.scrapers.brightdata_scraper import scraper_b_csv_brightdata as scraper_b_brightdata

# ========================================================================
# CONFIGURATION (SerpAPI/BrightData/Spreadd – single source in settings)
# ========================================================================

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env")

GEMINI_API_KEY = settings.GEMINI_API_KEY
GEMINI_MODEL = settings.GEMINI_MODEL
SERP_API_KEY = settings.SERP_API_KEY
BRIGHTDATA_API_KEY = settings.BRIGHTDATA_API_KEY
BRIGHTDATA_DATASET_ID = settings.BRIGHTDATA_DATASET_ID
BRIGHTDATA_API_BASE = settings.BRIGHTDATA_API_BASE
BRIGHTDATA_SCRAPE_PATH = settings.BRIGHTDATA_SCRAPE_PATH
SERPAPI_SEARCH_URL = settings.SERPAPI_SEARCH_URL
SPREADD_URL = settings.SPREADD_URL
ENDPOINT_URL = settings.ENDPOINT_URL
INSTAGRAM_BASE_URL = settings.INSTAGRAM_BASE_URL
BRIGHTDATA_TIMEOUT_SECONDS = settings.BRIGHTDATA_TIMEOUT_SECONDS
SERPAPI_TIMEOUT = settings.SERPAPI_TIMEOUT

BRIGHTDATA_URL = (
    f"{BRIGHTDATA_API_BASE.rstrip('/')}{BRIGHTDATA_SCRAPE_PATH}"
    f"?dataset_id={BRIGHTDATA_DATASET_ID}&notify=false&include_errors=true"
)

if not GEMINI_API_KEY:
    raise RuntimeError("Missing Gemini API key. Set GEMINI_API_KEY in .env")

logger = logging.getLogger(__name__)

# ========================================================================
# LOGGING AND SERP HELPERS (SerpAPI via serpapi_service – no local duplicate)
# ========================================================================

def log_section(title: str, level: str = "info"):
    """Log a section header."""
    separator = "=" * 70
    if level == "info":
        logger.info(f"\n{separator}\n{title}\n{separator}")
    elif level == "warning":
        logger.warning(f"\n{separator}\n{title}\n{separator}")
    elif level == "error":
        logger.error(f"\n{separator}\n{title}\n{separator}")

# ========================================================================
# QUERY PARSING
# ========================================================================

# parse_query_with_gemini imported from gemini_utils

def _validate_and_fix_parsed_query(parsed: Dict, original_query: str) -> Dict:
    """Validate and fix parsed query using LLM if fields are missing."""
    if 'num_results' not in parsed or parsed['num_results'] is None or parsed['num_results'] < 1:
        # Enhanced pattern to match more variations
        num_match = re.search(r'(?:top|find|get|show|list|give\s+me)\s*(\d+)|(\d+)\s*(?:influencers?|results?|creators?)', original_query.lower())
        if num_match:
            num_value = num_match.group(1) or num_match.group(2)
            parsed['num_results'] = int(num_value)
        else:
            parsed['num_results'] = 3

    parsed['num_results'] = min(parsed['num_results'], 50)

    # Use LLM to fill missing fields instead of keyword matching
    # NOTE: _infer_with_llm is ONLY for discovery/search queries, NOT for identity tagging
    # Identity is resolved via resolve_influencer_identity_with_openai() after enrichment
    if not parsed.get('niche') or parsed['niche'].lower() in ('null', 'none', ''):
        parsed['niche'] = _infer_with_llm(original_query, 'niche') or 'General'  # Discovery only

    if not parsed.get('location') or parsed['location'].lower() in ('null', 'none', ''):
        parsed['location'] = _infer_with_llm(original_query, 'location') or 'India'

    if 'search_queries' not in parsed or not parsed['search_queries'] or len(parsed['search_queries']) < 3:
        parsed['search_queries'] = _generate_fallback_search_queries(parsed)

    if parsed.get('min_followers') and parsed.get('max_followers'):
        if parsed['min_followers'] > parsed['max_followers']:
            parsed['min_followers'], parsed['max_followers'] = parsed['max_followers'], parsed['min_followers']

    parsed['original_query'] = original_query
    return parsed


def _create_fallback_parsed_query(user_query: str, reason: str) -> Dict:
    """Create fallback parsed query using LLM when initial parsing fails."""
    logger.info(f"Using LLM fallback parsing. Reason: {reason}")

    # Retry with LLM using a simpler prompt
    try:
        client = get_gemini_client()
        if client is None:
            return _create_fallback_parsed_query(user_query, "Gemini client unavailable")
        simple_prompt = f"""Extract parameters from this query: "{user_query}"

Return JSON with: num_results (integer), niche (string), location (string), min_followers (integer or null), max_followers (integer or null).
Defaults: num_results=3, niche="General", location="India", min_followers=50000, max_followers=1000000."""
        full_prompt = f"You are a query parser. Return only valid JSON.\n\n{simple_prompt}"

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=full_prompt,
            config={"temperature": 0.0, "response_mime_type": "application/json"}
        )
        
        response_text = response.text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()
        
        parsed = json.loads(response_text)
        
        # Ensure required fields
        parsed['num_results'] = parsed.get('num_results', 3)
        parsed['niche'] = parsed.get('niche', 'General')
        parsed['location'] = parsed.get('location', 'India')
        parsed['min_followers'] = parsed.get('min_followers', 50000)
        parsed['max_followers'] = parsed.get('max_followers', 1000000)
        parsed['min_rate'] = None
        parsed['max_rate'] = None
        parsed['original_query'] = user_query
        parsed['search_queries'] = _generate_fallback_search_queries(parsed)
        
        logger.info(f"   LLM Fallback: {parsed['num_results']} {parsed['niche']} influencers in {parsed['location']}")
        return parsed
        
    except Exception as e:
        logger.warning(f"LLM fallback also failed: {e}, using minimal defaults")
        # Absolute minimal fallback - only if LLM completely fails
        return {
            'num_results': 3,
            'niche': 'General',
            'location': 'India',
            'min_followers': 50000,
            'max_followers': 1000000,
            'min_rate': None,
            'max_rate': None,
            'original_query': user_query,
            'search_queries': _generate_fallback_search_queries({
                'niche': 'General',
                'location': 'India',
                'min_followers': 50000,
                'max_followers': 1000000
            })
        }


def _infer_with_llm(query: str, field: str) -> Optional[str]:
    """Infer field value using LLM instead of keyword matching."""
    try:
        client = get_gemini_client()
        prompt = f"""Extract the {field} from this query: "{query}"

Return only the {field} value as a JSON object: {{"{field}": "value"}}
For niche: return capitalized name (e.g., "Finance", "Fitness", "Beauty")
For location: return location name (e.g., "Mumbai", "Delhi", "India")
If not found, return null."""
        full_prompt = f"You are a query parser. Return only valid JSON.\n\n{prompt}"

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=full_prompt,
            config={"temperature": 0.0, "response_mime_type": "application/json"}
        )
        
        response_text = response.text.strip()
        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()
        
        result = json.loads(response_text)
        value = result.get(field)
        return value if value and value.lower() not in ('null', 'none', '') else None
        
    except Exception as e:
        logger.debug(f"LLM inference failed for {field}: {e}")
        return None


def _generate_fallback_search_queries(parsed: Dict) -> List[str]:
    """
    Generate fallback search queries based on parsed parameters.
    CRITICAL FIX: Now generates queries HEAVILY BIASED toward the HIGH END of follower range.
    """
    niche = parsed.get('niche', 'General').lower()
    location = parsed.get('location', 'India')
    min_followers = parsed.get('min_followers', 50000)
    max_followers = parsed.get('max_followers', 1000000)

    niche_terms = {
        'finance': ['finance expert', 'personal finance creator', 'investment advisor', 'money coach'],
        'fitness': ['fitness trainer', 'gym coach', 'workout instructor', 'health coach'],
        'beauty': ['makeup artist', 'beauty blogger', 'skincare expert', 'MUA'],
        'fashion': ['fashion blogger', 'style influencer', 'fashion designer', 'outfit creator'],
        'food': ['food blogger', 'chef', 'recipe creator', 'foodie'],
        'tech': ['tech reviewer', 'gadget expert', 'tech blogger', 'software developer'],
        'travel': ['travel blogger', 'travel vlogger', 'wanderer', 'travel creator'],
        'gaming': ['gamer', 'esports player', 'gaming streamer', 'gaming content creator'],
        'lifestyle': ['lifestyle blogger', 'lifestyle vlogger', 'daily vlogger', 'lifestyle influencer'],
        'parenting': ['parenting blogger', 'mom blogger', 'dad blogger', 'family vlogger'],
        'education': ['educator', 'teacher', 'career coach', 'educational content creator'],
        'entertainment': ['comedian', 'entertainer', 'meme creator', 'comedy content creator'],
        'music': ['musician', 'singer', 'music artist', 'music producer'],
        'sports': ['athlete', 'sports player', 'sports coach', 'sports commentator'],
        'business': ['entrepreneur', 'business owner', 'startup founder', 'business coach'],
        'art': ['artist', 'digital artist', 'illustrator', 'painter'],
        'photography': ['photographer', 'photo blogger', 'camera expert', 'visual artist'],
        'pet': ['pet influencer', 'dog blogger', 'cat vlogger', 'pet trainer'],
        'general': ['content creator', 'influencer', 'creator', 'blogger']
    }

    terms = niche_terms.get(niche, niche_terms['general'])

    # Check for authority mode (PART 2: Hybrid Discovery)
    discovery_mode = parsed.get('discovery_mode', 'numeric')
    
    if discovery_mode == 'authority':
        # Authority mode: use quality/status indicators instead of follower counts
        follower_indicators = [
            "verified",
            "famous",
            "top creator",
            "popular",
            "official",
            "celebrity",
            "established",
            "influencer"
        ]
    else:
        # Numeric mode: Generate follower indicators HEAVILY BIASED toward upper end
        follower_indicators = []
        
        def format_follower_count(count):
            """Format follower count for search queries"""
            if count >= 1000000:
                return f"{count / 1000000:.1f}M followers"
            elif count >= 1000:
                return f"{int(count / 1000)}k followers"
            return f"{count} followers"

        if min_followers and max_followers:
            range_size = max_followers - min_followers
            
            # Calculate HIGH percentiles (80th, 90th, 95th, 98th) - heavily favor upper end
            percentile_80 = min_followers + int(range_size * 0.80)  # For 400k-900k → 800k
            percentile_90 = min_followers + int(range_size * 0.90)  # For 400k-900k → 850k
            percentile_95 = min_followers + int(range_size * 0.95)  # For 400k-900k → 875k
            percentile_98 = min_followers + int(range_size * 0.98)  # For 400k-900k → 890k
            
            # Generate indicators focusing on HIGH END ONLY
            follower_indicators = [
                format_follower_count(percentile_98),  # e.g., "890k followers" - VERY close to max
                format_follower_count(percentile_95),  # e.g., "875k followers"
                format_follower_count(percentile_90),  # e.g., "850k followers"
                format_follower_count(max_followers),  # e.g., "900k followers" - exact max
                format_follower_count(percentile_80),  # e.g., "800k followers"
                "popular",                          # Generic high-quality term
                "verified",                         # Quality indicator
                "top creator",                      # High-status term
            ]
        elif max_followers:
            # For "under X" queries, target 70-95% of max
            target_70 = int(max_followers * 0.70)
            target_85 = int(max_followers * 0.85)
            target_95 = int(max_followers * 0.95)
            
            follower_indicators = [
                format_follower_count(target_95),
                format_follower_count(target_85),
                format_follower_count(target_70),
                "popular",
                "established"
            ]
        else:
            # Fallback: generic high-quality indicators
            follower_indicators = ["popular", "verified", "established", "top creator"]

    queries = []
    
    # Generate diverse queries using HIGH follower counts
    for i, term in enumerate(terms[:4]):  # Max 4 niche terms
        if i < len(follower_indicators):
            indicator = follower_indicators[i]
            queries.append(f"{term} {location} {indicator} instagram")
        else:
            queries.append(f"{term} {location} instagram")
            
    # Add additional high-quality queries
    queries.extend([
        f"{niche} {location} verified instagram",
        f"top {niche} {location} instagram",
        f"{niche} creator {location} popular instagram"
    ])

    return queries[:10]  # Return max 10 queries

async def scraper_a_serpapi_spreadd(influencers: List[Dict[str, str]], parsed_query: Dict) -> List[Dict]:
    """
    Scraper A: SerpAPI enrichment + Spreadd.io (Refactored to use centralized services).
    """
    # Import locally to avoid top-level cycles if any
    from app.services.scrapers.serpapi_service import scraper_a_serpapi_only
    from app.services.scrapers.spreadd_service import run_spreadd_parallel
    import logging
    
    logger = logging.getLogger(__name__)
    logger.info("👉 Using centralized services for Scraper A")
    
    # 1. Run SerpAPI Only
    results = await scraper_a_serpapi_only(influencers, parsed_query)
    
    # 2. Enrich with Spreadd Parallel
    if results:
        await run_spreadd_parallel(results)
        
    return results

# scraper_b_brightdata imported from brightdata_scraper



# HELPER FUNCTIONS

# Helper functions imported from search_filters


# FILTER AND SORT RESULTS

def _validate_niche_with_llm(result: Dict, target_niche: str) -> bool:
    """
    DEPRECATED FOR IDENTITY: This function is ONLY for filtering/validation, NOT for identity assignment.
    Identity is now resolved via resolve_influencer_identity_with_openai() after enrichment.
    """
    """
    LLM-based niche validation using Gemini API.
    Returns True if influencer matches target niche with confidence >= 0.7.
    """
    from app.prompts import NICHE_VALIDATION_SYSTEM, NICHE_VALIDATION_USER_TEMPLATE

    # ========================================================================
    # PROFILE DATA PREPARATION
    # ========================================================================
    name = result.get('NAME', 'Unknown')
    username = result.get('Id', result.get('username', 'unknown'))
    biography = result.get('biography', 'No bio available')
    business_category = result.get('business_category_name', result.get('category_name', 'Not specified'))
    followers = result.get('followers', 'N/A')
    is_verified = result.get('is_verified', False)
    is_business = result.get('is_business_account', False)
    is_professional = result.get('is_professional_account', False)
    external_url = result.get('external_url', 'None')
    account_type = "Business" if is_business else "Professional" if is_professional else "Personal"

    prompt = NICHE_VALIDATION_USER_TEMPLATE.format(
        target_niche=target_niche.title(),
        name=name,
        username=username,
        biography=biography[:300],
        business_category=business_category,
        followers=followers,
        account_type=account_type,
        is_verified=is_verified,
        external_url=external_url
    )

    # ========================================================================
    # LLM VALIDATION WITH RETRY LOGIC
    # ========================================================================
    max_retries = 3
    base_delay = 1.0
    
    for attempt in range(max_retries):
        try:
            client = get_gemini_client()
            full_prompt = f"{NICHE_VALIDATION_SYSTEM}\n\n{prompt}"
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=full_prompt,
                config={"temperature": 0.1, "response_mime_type": "application/json"}
            )

            response_text = response.text.strip()
            validation_result = json.loads(response_text)

            is_match = validation_result.get('is_match', False)
            confidence = validation_result.get('confidence', 0.0)
            detected_niche = validation_result.get('detected_niche', 'Unknown')

            if is_match:
                logger.info(f"   ✓ LLM MATCH: {name} - {detected_niche} (confidence: {confidence:.0%})")

            return is_match and confidence >= 0.7

        except json.JSONDecodeError:
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))
                continue

        except Exception as e:
            error_str = str(e)
            
            # Extract JSON from error message if validation failed
            if 'failed_generation' in error_str or 'json_validate_failed' in error_str:
                json_match = re.search(r'\{[^{}]*"is_match"[^{}]*\}', error_str, re.DOTALL)
                if json_match:
                    try:
                        validation_result = json.loads(json_match.group(0))
                        is_match = validation_result.get('is_match', False)
                        confidence = validation_result.get('confidence', 0.0)
                        detected_niche = validation_result.get('detected_niche', 'Unknown')
                        logger.info(f"   ✓ LLM MATCH: {name} - {detected_niche} (confidence: {confidence:.0%})")
                        return is_match and confidence >= 0.7
                    except:
                        pass
            
            # Retry on transient errors
            is_retryable = (
                '400' in error_str or 
                'json_validate_failed' in error_str or 
                'max completion tokens' in error_str.lower() or
                'rate limit' in error_str.lower()
            )
            
            if is_retryable and attempt < max_retries - 1:
                time.sleep(base_delay * (2 ** attempt))
                continue
            else:
                logger.warning(f"   ⚠️ LLM niche validation failed for {name}: {error_str[:200]}")
                break

    # ========================================================================
    # FALLBACK: SIMPLE NICHE MATCH
    # ========================================================================
    # If LLM fails completely, check if target niche appears in profile data
    result_niche = str(result.get('NICHE', '')).lower()
    biography_lower = str(biography).lower()
    category_lower = str(business_category).lower()
    
    target_lower = target_niche.lower()
    return (target_lower in result_niche or 
            target_lower in biography_lower or 
            target_lower in category_lower)

# ========================================================================
# DATA PERSISTENCE
# ========================================================================

async def send_to_endpoint(data: List[Dict]):
    """Send results to API endpoint."""
    if not ENDPOINT_URL or not ENDPOINT_URL.startswith('http'):
        logger.info("ℹ️  External endpoint not configured, skipping delivery")
        return

    log_section("📤 SENDING TO ENDPOINT")

    try:
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        async with aiohttp.ClientSession() as session:
            async with session.post(
                ENDPOINT_URL,
                json={"influencers": data, "count": len(data)},
                headers={"Content-Type": "application/json"},
                ssl=ssl_context,
                timeout=aiohttp.ClientTimeout(total=30)
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    logger.info(f"✅ Successfully sent to endpoint: {result}")
                else:
                    response_text = await response.text()
                    logger.warning(f"⚠️ Endpoint returned status {response.status}")
    except Exception as e:
        logger.warning(f"⚠️ Could not send to endpoint: {e}")


def save_to_files(data: List[Dict]):
    """Save results (deprecated - now using temp_store)."""
    if data:
        logger.info(f"✅ {len(data)} influencers will be persisted via temp_store")

# ---------------------------------------------------------------------------
# INFLUENCER DISCOVERY (SerpAPI)
# Single structured query: site:instagram.com + niche + location + follower range.
# Geo (gl/location) is derived from parsed location so results match region.
# ---------------------------------------------------------------------------

# Results per request; filter=0 to avoid Google's "similar" collapsing.
# Target total profiles to discover (we paginate with start= to reach this).
TARGET_DISCOVERY_PROFILES = 100
# Results per SerpAPI page (Google typically returns up to 10 per page).
SERP_PAGE_SIZE = 10
SERP_DISCOVERY_NUM = SERP_PAGE_SIZE
SERP_DISCOVERY_FILTER = "0"

# Location string (as used in UI/parser) -> (SerpAPI location, country code gl).
_LOCATION_TO_SERP = {
    "india": ("India", "in"),
    "mumbai": ("Mumbai, Maharashtra, India", "in"),
    "delhi": ("Delhi, India", "in"),
    "bangalore": ("Bangalore, Karnataka, India", "in"),
    "chennai": ("Chennai, Tamil Nadu, India", "in"),
    "hyderabad": ("Hyderabad, Telangana, India", "in"),
    "kolkata": ("Kolkata, West Bengal, India", "in"),
    "pune": ("Pune, Maharashtra, India", "in"),
    "usa": ("United States", "us"),
    "us": ("United States", "us"),
    "united states": ("United States", "us"),
    "new york": ("New York, NY, USA", "us"),
    "los angeles": ("Los Angeles, CA, USA", "us"),
    "uk": ("United Kingdom", "uk"),
    "united kingdom": ("United Kingdom", "uk"),
    "london": ("London, England, UK", "uk"),
    "france": ("France", "fr"),
    "paris": ("Paris, Île-de-France, France", "fr"),
    "germany": ("Germany", "de"),
    "berlin": ("Berlin, Germany", "de"),
    "uae": ("United Arab Emirates", "ae"),
    "dubai": ("Dubai, UAE", "ae"),
    "singapore": ("Singapore", "sg"),
    "australia": ("Australia", "au"),
    "sydney": ("Sydney, NSW, Australia", "au"),
    "canada": ("Canada", "ca"),
    "toronto": ("Toronto, ON, Canada", "ca"),
}


def _serp_geo_for_location(location: str) -> tuple:
    """Resolve (SerpAPI location string, gl) for a given location. Default: India."""
    if not location or not str(location).strip():
        return "India", "in"
    key = str(location).strip().lower()
    return _LOCATION_TO_SERP.get(key, (location, "in"))


def _build_discovery_query(
    niche: str,
    location: str,
    min_followers: Optional[int],
    max_followers: Optional[int],
) -> str:
    """
    Build a single SerpAPI query: site:instagram.com "niche" "location" "min..max followers".
    Uses raw numbers for the range so Google can apply numeric filtering.
    """
    niche = (niche or "influencer").strip() or "influencer"
    location = (location or "India").strip() or "India"
    min_f = min_followers if min_followers is not None else 1000
    max_f = max_followers if max_followers is not None else 900000
    min_f = max(1, int(min_f))
    max_f = max(min_f, int(max_f))
    follower_part = f'"{min_f}..{max_f} followers"'
    return f'site:instagram.com "{niche}" "{location}" {follower_part}'


def _run_serp_search(params: Dict) -> List[Dict]:
    """Execute SerpAPI search (sync) via canonical serpapi_service; returns organic_results or []."""
    try:
        data = get_google_search(params).get_dict()
    except Exception as e:
        logger.warning("SerpAPI request failed: %s", e)
        return []
    if data.get("error"):
        logger.warning("SerpAPI error: %s", data.get("error"))
        return []
    return data.get("organic_results") or []


def _organic_results_to_influencers(
    organic_results: List[Dict],
    seen_usernames: set,
    niche_hint: str = "",
    location_hint: str = "",
) -> List[Dict]:
    """Parse SerpAPI organic results into influencer dicts; updates seen_usernames."""
    from app.utils.image_utils import extract_profile_image

    out = []
    for result in organic_results:
        link = result.get("link") or ""
        if "instagram.com" not in link.lower():
            continue
        username = _extract_username_from_url(link)
        if not username or username.lower() in seen_usernames:
            continue
        seen_usernames.add(username.lower())

        title = (result.get("title") or "").strip()
        snippet = (result.get("snippet") or "").strip()
        desc = (result.get("description") or "").strip()
        name = (
            title.replace(f"@{username}", "")
            .replace("(@" + username + ")", "")
            .replace("Instagram", "")
            .replace("•", "")
            .strip()
        )
        if not name or len(name) < 2:
            name = username

        combined = f"{title} {snippet} {desc}".strip()
        rate_range = _extract_rate_range(combined)
        normalized_url = f"https://www.instagram.com/{username}/"
        profile_pic_url = extract_profile_image({}, username, "_discover_influencers_serpapi")

        row = {
            "name": name,
            "username": username,
            "profile_link": normalized_url,
            "profile_url": normalized_url,
            "url": normalized_url,
            "original_url": link,
            "profile_pic_url": profile_pic_url,
            "profile_image": profile_pic_url,
            "image": profile_pic_url,
            "niche_hint": niche_hint,
            "location_hint": location_hint,
        }
        if rate_range:
            row["min_rate"] = rate_range.get("min_rate")
            row["max_rate"] = rate_range.get("max_rate")
            if rate_range.get("min_rate"):
                row["rate"] = rate_range.get("min_rate")
        out.append(row)
    return out


async def discover_influencers_from_prompt(parsed_query: Dict) -> List[Dict[str, str]]:
    """
    Discover Instagram influencers via structured SerpAPI query(ies).
    Fetches 10 pages (start=0, 10, 20, ... 90) in parallel, then merges and dedupes.
    """
    niche = parsed_query.get("niche") or "General"
    location = parsed_query.get("location") or "India"
    min_followers = parsed_query.get("min_followers")
    max_followers = parsed_query.get("max_followers")

    q = _build_discovery_query(niche, location, min_followers, max_followers)
    serp_location, gl = _serp_geo_for_location(location)

    # 10 batches: start=0, 10, 20, ... 90 – all requested in parallel
    num_batches = TARGET_DISCOVERY_PROFILES // SERP_PAGE_SIZE
    param_list = [
        {
            "api_key": SERP_API_KEY,
            "engine": "google",
            "q": q,
            "location": serp_location,
            "gl": gl,
            "hl": "en",
            "num": SERP_DISCOVERY_NUM,
            "filter": SERP_DISCOVERY_FILTER,
            "start": start,
        }
        for start in range(0, TARGET_DISCOVERY_PROFILES, SERP_PAGE_SIZE)
    ]

    logger.info(
        "Discovery query: %s | geo=%s gl=%s | %d SerpAPI pages in parallel (target=%d profiles)",
        q[:80], serp_location, gl, num_batches, TARGET_DISCOVERY_PROFILES,
    )

    loop = asyncio.get_event_loop()
    tasks = [
        loop.run_in_executor(None, lambda p=p: _run_serp_search(p))
        for p in param_list
    ]
    pages_organic: List[List[Dict]] = await asyncio.gather(*tasks)

    # Merge in page order and dedupe by username
    seen: set = set()
    discovered: List[Dict[str, str]] = []
    for organic_results in pages_organic:
        page = _organic_results_to_influencers(
            organic_results or [], seen, niche_hint=niche, location_hint=location
        )
        discovered.extend(page)

    logger.info("Discovery finished: %d profiles", len(discovered))
    return discovered


async def run_async_pipeline(
    user_query: str,
    influencers: Optional[List[Dict[str, str]]] = None,
    skip_analysis: bool = False
):
    """
    STRICT MODE: Only returns results that EXACTLY match prompt.
    NO relaxation, NO fallbacks. Better to return 0 results than wrong results.
    """
    log_section("ASYNC INSTAGRAM INFLUENCER SCRAPER - STRICT MODE")

    # Parse query
    parsed_query = parse_query_with_gemini(user_query)
    num_requested = parsed_query.get('num_results', 3)

    logger.info(f"STRICT MODE Query: {num_requested} {parsed_query['niche']} creators in {parsed_query['location']}")
    logger.info(f"⚠️  STRICT FILTERING: Will ONLY return exact matches, no relaxation")

    # Get influencers
    if influencers is not None:
        logger.info(f"Using {len(influencers)} pre-loaded influencers")
    else:
        # Discover profiles from web search
        influencers = await discover_influencers_from_prompt(parsed_query)
        if not influencers:
            logger.error("No influencers found matching query")
            return []

    # Flow: User Query → SerpAPI → BrightData → merge; Spreadd (authenticity) in parallel after merge
    start_time = time.time()

    scraper_a_results = await scraper_a_serpapi_only(influencers, parsed_query)
    if isinstance(scraper_a_results, Exception):
        logger.error(f"Scraper A error: {scraper_a_results}")
        scraper_a_results = []

    loop = asyncio.get_event_loop()
    scraper_b_results = []
    try:
        scraper_b_results = await loop.run_in_executor(None, scraper_b_brightdata, influencers, parsed_query)
    except Exception as e:
        logger.error(f"Scraper B error: {e}")
    if isinstance(scraper_b_results, Exception):
        scraper_b_results = []

    elapsed = time.time() - start_time
    logger.info(f"Scrapers completed in {elapsed:.1f}s: A={len(scraper_a_results)}, B={len(scraper_b_results)}")

    log_section("MERGING RESULTS")
    merged_results = merge_results(scraper_a_results, scraper_b_results, [])

    if len(merged_results) == 0:
        logger.warning("No results found after merging scrapers")
        return []

    logger.info(f"Merged {len(merged_results)} unique influencers")
    logger.info(f"Scrapers: A={len(scraper_a_results)}, B={len(scraper_b_results)}")
    logger.info("="*70)
    logger.info(f"Total results before sort: {len(merged_results)}")

    unique_results = remove_duplicates(merged_results)

    # Spreadd (authenticity score) in parallel – merge into results
    logger.info("Fetching authenticity scores (Spreadd) in parallel...")
    await run_spreadd_parallel(unique_results)
    logger.info("Authenticity scores ready")

    logger.info("Sort by relevance.")
    sorted_results = sort_results_by_relevance(unique_results, parsed_query)

    if len(sorted_results) == 0:
        logger.error("No results after sort.")
        return []

    if len(sorted_results) < num_requested:
        logger.warning(f"Found {len(sorted_results)} (requested: {num_requested})")
        final_results = sorted_results
    else:
        logger.info(f"Found {len(sorted_results)} (requested: {num_requested})")
        final_results = sorted_results[:num_requested]

    # ========================================================================
    # OPTIMIZED INDUSTRY STANDARDS: Discover peers EARLY, enrich in PARALLEL
    # ========================================================================
    industry_peers = []
    if final_results:
        try:
            from app.services.analysis.industry_standards import (
                ENABLE_INDUSTRY_STANDARDS,
                discover_industry_peers_early,
                apply_follower_constraint,
                rank_peers
            )
            
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
    if industry_peers:
        # Insert peers after anchor in final_results
        final_results_with_peers = [final_results[0]] + industry_peers + final_results[1:]
        logger.info(f"✅ Final results: 1 anchor + {len(industry_peers)} industry peers + {len(final_results)-1} other results")
    else:
        final_results_with_peers = final_results

    # Save results (use final_results_with_peers if we have peers)
    results_to_save = final_results_with_peers if industry_peers else final_results
    save_to_files(results_to_save)
    await send_to_endpoint(results_to_save)

    # Summary
    log_section("PIPELINE COMPLETE - STRICT MODE")
    results_to_return = final_results_with_peers if industry_peers else final_results
    logger.info(f"✅ Returned {len(results_to_return)} STRICT matches in {elapsed:.1f}s")
    logger.info(f"   All results EXACTLY match prompt criteria")
    if industry_peers:
        logger.info(f"   Includes {len(industry_peers)} industry peers (enriched in parallel)")
    logger.info(f"   {len(merged_results)} discovered → {len(unique_results)} unique → {len(sorted_results)} returned")

    if results_to_return:
        df = pd.DataFrame(results_to_return)
        display_cols = ['NAME', 'NICHE', 'Location', 'followers', 'engagement_rate', 'RATE']
        available_cols = [col for col in display_cols if col in df.columns]
        if available_cols:
            logger.info(f"\n📊 Results Summary:")
            logger.info(f"\n{df[available_cols].head(len(results_to_return)).to_string(index=False)}")

    return results_to_return

# ENTRY POINT

if __name__ == "__main__":
    print("\n" + "="*70)
    print("ASYNC INSTAGRAM INFLUENCER SCRAPER")
    print("Combines SerpAPI + Spreadd.io AND BrightData")
    print("="*70)

    print("\n💡 Examples:")
    print("   • 'top 10 fashion influencers in Mumbai'")
    print("   • 'find 5 food bloggers with over 100k followers'")
    print("   • 'get fitness influencers in Delhi'")

    while True:
        query = input("\n\nEnter query (or 'quit'): ").strip()

        if query.lower() in ['quit', 'exit', 'q']:
            print("\n👋 Goodbye!")
            break

        if not query:
            continue

        # Run async pipeline
        asyncio.run(run_async_pipeline(query))

        cont = input("\n\nRun another query? (y/n): ").strip().lower()
        if cont not in ['y', 'yes']:
            print("\n👋 Goodbye!")
            break