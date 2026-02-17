# Industry Standards Expansion Module
# 
# This module adds industry-standard influencers from the same profession
# when searching for a specific person. It finds 2-3 additional influencers
# with similar or more followers who share the exact same profession.
# 
# BACKGROUND PROCESSING:
# - Industry standards are processed asynchronously in the background
# - Results are stored separately with status (processing/completed)
# - Main search flow returns immediately without waiting
# - Analysis endpoint fetches industry standards when ready

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from typing import Dict, List, Optional

from app.config.settings import settings
from app.services.data import temp_store
from app.services.llm.openai_utils import get_openai_client, get_openai_model

logger = logging.getLogger(__name__)

# ========================================================================
# CACHING FOR INDUSTRY STANDARDS
# ========================================================================
_industry_standards_cache: Dict[str, Dict] = {}
CACHE_TTL_SECONDS = 24 * 60 * 60  # 24 hours


def clear_industry_cache_for_username(username: str) -> bool:
    # Clear cached industry standards for a specific username.
    # Should be called at the start of each new search to ensure fresh peer discovery.
    # 
    # Args:
    #     username: The Instagram username to clear cache for
    # 
    # Returns:
    #     True if cache was cleared, False if no cache existed
    if not username:
        return False
    
    cache_key = hashlib.md5(f"{username.lower().strip()}".encode()).hexdigest()
    if cache_key in _industry_standards_cache:
        del _industry_standards_cache[cache_key]
        logger.info(f"🗑️ Cleared industry standards cache for @{username}")
        return True
    return False


def clear_all_industry_cache() -> int:
    # Clear ALL cached industry standards.
    # Useful for forcing fresh peer discovery across all searches.
    # 
    # Returns:
    #     Number of cache entries cleared
    global _industry_standards_cache
    count = len(_industry_standards_cache)
    _industry_standards_cache = {}
    if count > 0:
        logger.info(f"🗑️ Cleared ALL industry standards cache ({count} entries)")
    return count


# ========================================================================
# SINGLE ENTRY POINT TRACKING (Prevent Duplicate Execution)
# ========================================================================
_active_industry_discoveries: Dict[str, asyncio.Task] = {}  # conversation_id -> task

# ========================================================================
# CACHING FOR PROFESSION PEERS (TOP SEARCHES)
# ========================================================================
# Stores status and results for "profession peers" comparison (top influencer searches)
# CRITICAL: Uses temp_store for file-based persistence (survives server restart)
_profession_peers_status: Dict[str, Dict] = {}  # In-memory cache (fast access)

def _store_profession_peers_status(conversation_id: str, status: str, results: Optional[List[Dict]] = None, error: Optional[str] = None) -> None:
    # Store status for profession peers background processing.
    # 
    # Uses BOTH in-memory (fast) and temp_store (persistent) storage.
    status_data = {
        "status": status,
        "results": results or [],
        "error": error,
        "updated_at": time.time()
    }
    
    # Store in memory for fast access
    _profession_peers_status[conversation_id] = status_data
    
    # CRITICAL: Also persist to temp_store for survival across server restarts
    try:
        session_data = temp_store.load_session(conversation_id) or {}
        session_data["profession_peers"] = status_data
        temp_store.persist_session(conversation_id, session_data)
        logger.debug(f"✅ Stored profession peers status: {conversation_id} -> {status}")
    except Exception as e:
        logger.warning(f"⚠️ Failed to persist profession peers status to temp_store: {e}")

def get_profession_peers_status(conversation_id: str) -> Dict:
    """Get profession peers processing status for frontend polling.
    
    Checks in-memory cache first, falls back to temp_store.
    """
    # Check in-memory cache first (fast)
    if conversation_id in _profession_peers_status:
        return _profession_peers_status[conversation_id]
    
    # Fallback to temp_store (persistent)
    try:
        session_data = temp_store.load_session(conversation_id)
        if session_data and "profession_peers" in session_data:
            profession_data = session_data["profession_peers"]
            # Cache in memory for future fast access
            _profession_peers_status[conversation_id] = profession_data
            return profession_data
    except Exception as e:
        logger.warning(f"⚠️ Failed to load profession peers status from temp_store: {e}")
    
    # Default: not started
    return {
        "status": "not_started",
        "results": [],
        "error": None
    }



# ========================================================================
# FEATURE FLAG
# ========================================================================

ENABLE_INDUSTRY_STANDARDS = True

# ========================================================================
# CONFIGURATION
# ========================================================================

GEMINI_API_KEY = settings.GEMINI_API_KEY
GEMINI_MODEL = settings.GEMINI_MODEL
OPENAI_API_KEY = settings.OPENAI_API_KEY
OPENAI_MODEL = settings.OPENAI_MODEL
SERP_API_KEY = settings.SERP_API_KEY

if not GEMINI_API_KEY:
    raise RuntimeError("Missing Gemini API key. Set GEMINI_API_KEY in .env")

if not OPENAI_API_KEY:
    raise RuntimeError("Missing OpenAI API key. Set OPENAI_API_KEY in .env")

_openai_client = None

# Import SerpAPI for web search
try:
    from app.services.scrapers.search_scrapers import GoogleSearch
except ImportError:
    try:
        from serpapi import GoogleSearch as _SerpApiGoogleSearch
        GoogleSearch = _SerpApiGoogleSearch
    except ImportError:
        GoogleSearch = None
        logger.warning("SerpAPI not available - peer discovery will use OpenAI names only")

from app.services.llm.gemini_utils import get_gemini_client
from app.services.core.search_filters import parse_followers_to_int, calculate_rate


def normalize_peer_urls_to_usernames(peer_urls: List[str], anchor_username: str) -> List[str]:
    """Extract and normalize usernames from URLs, excluding the anchor and duplicates."""
    usernames = set()
    anchor_clean = anchor_username.lower().strip()
    
    for url in peer_urls:
        if not url:
            continue
            
        # Extract username from URL or use as is if it looks like a username
        username = url
        if "instagram.com/" in url:
            try:
                username = url.split("instagram.com/")[1].split("/")[0].split("?")[0]
            except IndexError:
                continue
                
        username = username.strip().lower().lstrip("@")
        
        # Skip if empty, logic error, or is the anchor
        if not username or username == anchor_clean:
            continue
            
        usernames.add(username)
        
    return list(usernames)


# -----------------------------------------------------------------------------
# OpenAI: use canonical client/model from openai_utils (single source of truth).
# -----------------------------------------------------------------------------

async def _search_instagram_username_via_serpapi(peer_name: str) -> Optional[str]:
    """
    Search for Instagram username using SerpAPI.
    
    Args:
        peer_name: Name of the person (e.g., "MS Dhoni", "Virat Kohli")
    
    Returns:
        Instagram username if found, None otherwise
    """
    if not SERP_API_KEY or not GoogleSearch:
        logger.warning(f"SerpAPI not available, cannot search for Instagram username of {peer_name}")
        return None
    
    try:
        loop = asyncio.get_event_loop()
        
        # Search for peer's Instagram profile
        serp_params = {
            "api_key": SERP_API_KEY,
            "engine": "google",
            "q": f"{peer_name} instagram",
            "google_domain": "google.co.in",
            "gl": "in",
            "hl": "en",
            "num": 3,
        }
        
        serp_data = await loop.run_in_executor(
            None, lambda: GoogleSearch(serp_params).get_dict()
        )
        
        # Extract Instagram URL from search results
        if "error" not in serp_data:
            organic_results = serp_data.get("organic_results", [])
            for result in organic_results:
                link = result.get("link", "")
                if "instagram.com" in link.lower():
                    # Extract username from URL
                    from app.services.core.search_filters import extract_username_from_url as _extract_username_from_url
                    username = _extract_username_from_url(link)
                    if username:
                        logger.info(f"   ✅ Found Instagram username for '{peer_name}': @{username}")
                        return username
        
        logger.warning(f"   ⚠️ Could not find Instagram username for '{peer_name}' via SerpAPI")
        return None
        
    except Exception as e:
        logger.error(f"   ❌ SerpAPI search failed for '{peer_name}': {e}")
        return None


# ========================================================================
# OPENAI WEB SEARCH - PROFESSION & PEER DISCOVERY
# ========================================================================

async def discover_profession_and_peers_via_openai(anchor_url: str) -> Dict[str, any]:
    """
    Use OpenAI to discover profession and peer names, then use SerpAPI to find actual Instagram usernames.
    
    Args:
        anchor_url: Instagram profile URL or username (e.g., "https://instagram.com/virat.kohli" or "virat.kohli")
    
    Returns:
        {
            "profession": "Professional Cricketer",
            "peer_urls": [
                "https://www.instagram.com/mahi7781/",
                "https://www.instagram.com/rohitsharma45/"
            ]
        }
    """
    try:
        client = get_openai_client()
        model = get_openai_model()
        
        # Normalize input (handle both URL and username)
        if not anchor_url.startswith("http"):
            anchor_url = f"https://www.instagram.com/{anchor_url.lstrip('@')}/"
        
        prompt = f"""You are an expert at identifying account types and finding industry peers.

Given this Instagram profile: {anchor_url}

FIRST: Determine if this is a PERSONAL account or a BRAND/ORGANIZATION account.

PERSONAL ACCOUNT examples: Actors, Singers, Athletes, Fitness Coaches, YouTubers, Photographers
BRAND/ORGANIZATION ACCOUNT examples: News Media (Times Now, NDTV, BBC), Restaurants, Fashion Brands, Companies, Sports Teams

Your tasks:
1. Identify the account's PRIMARY category (be VERY SPECIFIC):
   - For PERSONAL accounts: "Professional Cricketer", "Bollywood Actor", "Singer", "Fashion Model", etc.
   - For NEWS MEDIA accounts: "News Media Organization", "News Channel", "News Publication"
   - For BRAND accounts: "Fashion Brand", "Food & Restaurant Brand", "Tech Company", etc.
   
2. Find EXACTLY 2 OTHER accounts of the EXACT SAME type/category

STRICT MATCHING RULES:
- The 2 peers MUST be IDENTICAL in type to the anchor:
  * If anchor is a "News Media Organization" → return other News Media Organizations ONLY (e.g., ANI, NDTV, Times Now, Republic TV)
  * If anchor is a "News Channel" → return other News Channels, NOT journalists or reporters
  * If anchor is a "Singer" → return other Singers, NOT actors who sometimes sing
  * If anchor is a "Professional Cricketer" → return other Professional Cricketers, NOT other sportspersons
  * If anchor is a "Bollywood Actor" → return other Bollywood Actors, NOT TV actors or models
  * If anchor is a "Fashion Brand" → return other Fashion Brands, NOT fashion influencers or models
  * If anchor is a "Food & Restaurant Brand" → return other Food/Restaurant Brands, NOT food bloggers
- NEVER mix personal accounts with brand accounts
- NEVER mix news media with journalists
- If the account has MULTIPLE categories, identify the PRIMARY one and find peers with that SAME primary category

OTHER REQUIREMENTS:
- Return the FULL NAMES of 2 different accounts (names like "NDTV", "Times Now", "MS Dhoni")
- The 2 must be DIFFERENT accounts - no aliases or sub-accounts of the same entity
- Prioritize the most popular/influential accounts in the same category (highest follower counts)
- Return EXACTLY 2 names, no more, no less

Respond in JSON format:
{{
    "profession": "News Media Organization",
    "peer_names": [
        "ANI",
        "Times Now"
    ]
}}"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert at identifying Instagram account types (personal vs brand/organization) and finding industry peers. CRITICAL RULES: (1) First determine if account is PERSONAL or BRAND/ORGANIZATION. (2) The 2 peers MUST be the EXACT SAME TYPE - never mix personal accounts with brands, never mix news media organizations with journalists, never mix fashion brands with fashion influencers. (3) For news/media pages, return other news/media organizations ONLY. Return valid JSON with profession and peer_names array."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=1000,
            response_format={"type": "json_object"}
        )
        
        data = json.loads(response.choices[0].message.content)
        profession = data.get("profession", "")
        peer_names = data.get("peer_names", [])
        
        # Log raw OpenAI response for debugging
        logger.info(f"🔍 OpenAI raw response - profession: '{profession}', peer_names: {peer_names}")
        
        if not profession or not peer_names or len(peer_names) < 2:
            logger.warning(f"⚠️ OpenAI returned incomplete data: profession={profession}, peer_names={peer_names}")
            return {"profession": "", "peer_urls": []}
        
        # Use SerpAPI to find actual Instagram usernames for each peer
        logger.info(f"🔍 Searching for Instagram usernames via SerpAPI for {len(peer_names)} peers...")
        peer_urls = []
        
        for peer_name in peer_names[:2]:  # Limit to 2 peers
            if not isinstance(peer_name, str) or not peer_name.strip():
                continue
                
            username = await _search_instagram_username_via_serpapi(peer_name.strip())
            if username:
                peer_url = f"https://www.instagram.com/{username}/"
                peer_urls.append(peer_url)
                logger.info(f"   ✅ Added peer URL: {peer_url}")
            else:
                logger.warning(f"   ⚠️ Could not find Instagram username for '{peer_name}', skipping")
        
        if profession and peer_urls:
            logger.info(f"✅ Discovered profession: {profession} with {len(peer_urls)} verified peer URLs")
            return {
                "profession": profession,
                "peer_urls": peer_urls
            }
        else:
            logger.warning(f"⚠️ Failed to find Instagram usernames for peers: profession={profession}, found_urls={len(peer_urls)}")
            return {"profession": "", "peer_urls": []}
            
    except Exception as e:
        logger.error(f"❌ Profession and peer discovery failed: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return {"profession": "", "peer_urls": []}


# ========================================================================
# PARALLEL SPREADD ENRICHMENT (LIGHTWEIGHT - NO SerpAPI)
# ========================================================================

async def _enrich_peers_parallel_spreadd_only(
    peer_influencers: List[Dict[str, str]], 
    conversation_id: Optional[str] = None
) -> List[Dict]:
    """
    OPTIMIZED: Enrich peers using ONLY Spreadd sequentially (no SerpAPI).
    This is faster and lighter for industry standards.
    
    CRITICAL: Persists peers incrementally to temp_store as they are enriched,
    updating status so frontend polling works reliably.
    
    Args:
        peer_influencers: List of peer influencer dicts to enrich
        conversation_id: Optional conversation ID for incremental persistence
    """
    if not peer_influencers:
        return []
    
    from app.services.scrapers.search_scrapers import AsyncSpreaddChecker
    from app.utils.image_utils import extract_profile_image
    from app.services.core.search_filters import parse_rate_to_int, calculate_rate
    
    checker = None
    try:
        checker = AsyncSpreaddChecker(headless=True)
        logger.info(f"✅ ChromeDriver initialized for parallel Spreadd enrichment")
    except Exception as e:
        logger.warning(f"⚠️ Could not initialize ChromeDriver: {e}")
        return []
    
    results = []
    
    try:
        # Run all Spreadd checks in parallel
        async def enrich_single_peer(inf: Dict[str, str]) -> Optional[Dict]:
            username = inf.get("username")
            if not username:
                return None
            
            try:
                spreadd_data = await checker.check_username(username)
                # Log what Spreadd actually returned
                if spreadd_data:
                    logger.info(f"   📊 Spreadd data for @{username}: followers={spreadd_data.get('followers', 'N/A')}, engagement={spreadd_data.get('engagement_rate', 'N/A')}, posts={spreadd_data.get('posts', 'N/A')}")
                else:
                    logger.warning(f"   ⚠️ Spreadd returned None for @{username}")
            except Exception as e:
                logger.warning(f"⚠️ Spreadd check failed for @{username}: {e}")
                spreadd_data = None
            
            if not spreadd_data:
                logger.warning(f"   ⚠️ No spreadd_data for @{username}, using defaults")
                spreadd_data = {
                    "username": username,
                    "followers": "0",
                    "posts": "0",
                    "engagement_rate": "0"
                }
            
            # Extract profile image
            profile_pic_url = extract_profile_image(spreadd_data, username, "industry_standards")
            
            # Calculate rate - handle N/A and empty values
            followers_str = str(spreadd_data.get("followers", "0") or "0")
            if followers_str.upper() in ("N/A", "NAN", "NULL", "NONE", ""):
                followers_str = "0"
                logger.warning(f"   ⚠️ @{username}: followers is N/A, using 0")
            primary_rate = parse_rate_to_int(calculate_rate(followers_str))
            rate_display = calculate_rate(followers_str)
            
            # Helper to convert N/A to 0 for numeric fields, but preserve valid formatted strings
            def safe_numeric_value(val, default="0"):
                if val is None:
                    return default
                val_str = str(val).strip()
                if not val_str or val_str.upper() in ("N/A", "NAN", "NULL", "NONE") or val_str == "-":
                    return "0"
                # Preserve valid formatted strings like "9.92M", "1.2K", "0.12%"
                return val_str
            
            # Prepare the result with proper value handling
            followers_val = safe_numeric_value(spreadd_data.get("followers"), "0")
            engagement_val = safe_numeric_value(spreadd_data.get("engagement_rate"), "0")
            
            # Log the final values being returned
            logger.info(f"   ✅ Final values for @{username}: followers={followers_val}, engagement={engagement_val}")
            
            result = {
                "NAME": inf.get("name", username),
                "Id": username,
                "PROFILE_LINK": inf.get("profile_link") or f"https://www.instagram.com/{username}/",
                "profile_pic_url": profile_pic_url,
                "profile_image": profile_pic_url,
                "image": profile_pic_url,
                "platform": "instagram",
                "followers": followers_val,
                "following": safe_numeric_value(spreadd_data.get("following"), "0"),
                "posts_count": safe_numeric_value(spreadd_data.get("posts"), "0"),
                "average_likes": safe_numeric_value(spreadd_data.get("avg_likes"), "0"),
                "average_comments": safe_numeric_value(spreadd_data.get("avg_comments"), "0"),
                "engagement_rate": engagement_val,
                "real_followers_percentage": safe_numeric_value(spreadd_data.get("real_followers_percentage"), "0"),
                "suspicious_followers_percentage": safe_numeric_value(spreadd_data.get("suspicious_followers_percentage"), "0"),
                "NICHE": inf.get("_industry_profession", ""),
                "Location": "Global",
                "RATE": rate_display,
                "rate": primary_rate,
                "source": "industry_standards_spreadd_only"
            }
            
            return result
        
        # CRITICAL FIX: Run Spreadd checks SEQUENTIALLY (not parallel)
        # Selenium/ChromeDriver cannot handle concurrent calls - causes connection pool errors
        logger.info(f"🔄 Running {len(peer_influencers)} Spreadd checks sequentially (Selenium limitation)...")
        
        for idx, inf in enumerate(peer_influencers, 1):
            try:
                result = await enrich_single_peer(inf)
                if result:
                    results.append(result)
                    # Log the actual values that were extracted
                    followers_val = result.get("followers", "N/A")
                    engagement_val = result.get("engagement_rate", "N/A")
                    logger.info(f"   [{idx}/{len(peer_influencers)}] ✅ Enriched @{inf.get('username', 'unknown')} - followers={followers_val}, engagement={engagement_val}")
                    
                    # CRITICAL: Persist incrementally as peers are enriched
                    if conversation_id:
                        try:
                            # Tag peer before persisting
                            result["industry_standard"] = True
                            
                            # Load existing results
                            from app.services.core import prompt_service
                            existing_results = prompt_service.load_dynamic_results(conversation_id) or []
                            
                            # Ensure anchor is marked
                            if existing_results and not any(r.get("industry_anchor") is True for r in existing_results):
                                existing_results[0]["industry_anchor"] = True
                            
                            # Merge new peer (avoid duplicates)
                            existing_ids = {r.get("id") or r.get("Id") for r in existing_results if r.get("id") or r.get("Id")}
                            peer_id = result.get("id") or result.get("Id")
                            if peer_id and peer_id not in existing_ids:
                                existing_results.append(result)
                                # Persist immediately
                                prompt_service.record_dynamic_results(conversation_id, existing_results)
                                prompt_service.persist_dynamic_results(conversation_id, existing_results)
                                
                                # CRITICAL: Update industry standards count incrementally so frontend polling detects new peers
                                try:
                                    # Count current peers (including the one just added)
                                    current_peer_count = len([r for r in existing_results if r.get("industry_standard") is True])
                                    peer_results = [r for r in existing_results if r.get("industry_standard") is True]
                                    # Update status with current peer count - keep status as "processing" until all peers are done
                                    _store_industry_standards_status(conversation_id, "processing", results=peer_results)
                                    # Also update comparison status to keep it in sync
                                    _store_industry_comparison_status(conversation_id, "processing", f"Enriched {current_peer_count} peer(s) so far...")
                                    logger.debug(f"   ✅ Persisted peer @{inf.get('username', 'unknown')} incrementally (count: {current_peer_count}, status: processing)")
                                except Exception as count_error:
                                    logger.warning(f"   ⚠️ Failed to update count incrementally: {count_error}")
                                    logger.debug(f"   ✅ Persisted peer @{inf.get('username', 'unknown')} incrementally")
                        except Exception as persist_error:
                            logger.warning(f"   ⚠️ Failed to persist peer incrementally: {persist_error}")
                            # Continue - will persist at end
            except Exception as e:
                logger.warning(f"   [{idx}/{len(peer_influencers)}] ⚠️ Enrichment failed: {e}")
                continue
        
        logger.info(f"✅ Sequential enrichment completed: {len(results)}/{len(peer_influencers)} successful")
        
    finally:
        if checker:
            try:
                checker.close()
            except:
                pass
    
    return results


def normalize_peer_urls_to_usernames(urls: List[str], anchor_username: str) -> List[str]:
    """
    Normalize peer Instagram URLs to usernames.
    Removes anchor username and duplicates.
    
    Args:
        urls: List of Instagram profile URLs
        anchor_username: Username of the anchor influencer (to exclude)
    
    Returns:
        List of unique usernames (without @ symbol)
    """
    usernames = []
    anchor_lower = anchor_username.lower().lstrip("@")
    
    logger.info(f"🔍 Normalizing {len(urls)} URLs to usernames (anchor: @{anchor_username})")
    
    for url in urls:
        if not url or not isinstance(url, str):
            logger.warning(f"   ⚠️ Skipping invalid URL: {url}")
            continue
            
        # Extract username from URL
        from app.services.core.search_filters import extract_username_from_url as _extract_username_from_url
        username = _extract_username_from_url(url)
        
        logger.info(f"   🔍 URL: {url} → Extracted username: {username}")
        
        if username and username.lower() != anchor_lower:
            usernames.append(username.lower())
            logger.info(f"   ✅ Added username: {username.lower()}")
        elif username:
            logger.info(f"   ⏭️ Skipped username (same as anchor): {username.lower()}")
        else:
            logger.warning(f"   ❌ Failed to extract username from URL: {url}")
    
    # Remove duplicates while preserving order
    seen = set()
    unique_usernames = []
    for username in usernames:
        if username not in seen:
            seen.add(username)
            unique_usernames.append(username)
    
    logger.info(f"✅ Normalized {len(urls)} URLs to {len(unique_usernames)} unique usernames (excluding anchor): {unique_usernames}")
    return unique_usernames


# ========================================================================
# IDENTITY RESOLUTION - SINGLE SOURCE OF TRUTH
# ========================================================================

async def resolve_influencer_identity_with_openai(
    profile_url: str,
    username: str,
    full_name: Optional[str] = None,
    biography: Optional[str] = None,
    external_url: Optional[str] = None
) -> Dict[str, any]:
    """
    SINGLE SOURCE OF TRUTH for influencer identity/profession.
    
    Uses OpenAI to identify the primary profession based on public profile data.
    This runs AFTER enrichment (SerpAPI + Spreadd) when data is stable.
    
    Rules:
    - Returns exactly ONE profession
    - Confidence >= 0.7 → use identified profession
    - Confidence < 0.7 → return "Digital Creator"
    - Never returns "General"
    
    Args:
        profile_url: Instagram profile URL
        username: Instagram username
        full_name: Full name from profile (optional)
        biography: Biography text (optional)
        external_url: External website URL (optional)
    
    Returns:
        {
            "profession": "Professional Cricketer",
            "confidence": 0.92,
            "reason": "Indian international cricketer with official sports affiliations",
            "source": "openai"
        }
        OR if confidence < 0.7:
        {
            "profession": "Digital Creator",
            "confidence": 0.65,
            "reason": "Low confidence in profession identification",
            "source": "openai_fallback"
        }
    """
    try:
        client = get_openai_client()
        model = get_openai_model()
        
        # Build context from available data
        context_parts = []
        if full_name:
            context_parts.append(f"Name: {full_name}")
        if username:
            context_parts.append(f"Username: @{username}")
        if profile_url:
            context_parts.append(f"Profile: {profile_url}")
        if biography and biography not in ("N/A", "nan", ""):
            context_parts.append(f"Bio: {biography}")
        if external_url and external_url not in ("N/A", "nan", ""):
            context_parts.append(f"Website: {external_url}")
        
        context = "\n".join(context_parts) if context_parts else f"Instagram profile: @{username}"
        
        prompt = f"""You are an expert at identifying public figures' primary professions.

Given this Instagram profile information:
{context}

Your task:
1. Identify the person's PRIMARY, globally recognized profession/role
2. Ignore brand deals, side businesses, or secondary activities
3. Focus on their main public identity (e.g., "Professional Cricketer", "Actor", "Fitness Coach", "Musician", "Fashion Designer")
4. Return exactly ONE profession

IMPORTANT RULES:
- Return a specific profession, not generic terms like "influencer" or "content creator"
- If the person is primarily known for a specific profession, use that
- If you cannot confidently identify a specific profession (confidence < 0.7), return "Digital Creator"
- Never return "General" or "Unknown"

Respond in JSON format:
{{
    "profession": "Professional Cricketer",
    "confidence": 0.92,
    "reason": "Indian international cricketer with official sports affiliations and cricket-focused content"
}}"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert at identifying public figures' primary professions. Always return valid JSON with profession, confidence, and reason."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.1,
            max_tokens=300,
            response_format={"type": "json_object"}
        )
        
        data = json.loads(response.choices[0].message.content)
        profession = data.get("profession", "").strip()
        confidence = float(data.get("confidence", 0))
        reason = data.get("reason", "")
        
        # Validate profession is not empty or "General"
        if not profession or profession.lower() == "general":
            profession = "Digital Creator"
            confidence = 0.0
            reason = "Invalid profession returned by OpenAI"
        
        # Apply confidence threshold
        if confidence < 0.7:
            profession = "Digital Creator"
            source = "openai_fallback"
            logger.debug(f"Identity resolution for @{username}: confidence {confidence} < 0.7, using 'Digital Creator'")
        else:
            source = "openai"
            logger.debug(f"Identity resolution for @{username}: {profession} (confidence: {confidence})")
        
        return {
            "profession": profession,
            "confidence": confidence,
            "reason": reason,
            "source": source
        }
        
    except Exception as e:
        logger.warning(f"Identity resolution failed for @{username}: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return {
            "profession": "Digital Creator",
            "confidence": 0.0,
            "reason": f"Identity resolution error: {str(e)}",
            "source": "error_fallback"
        }


# =============================================================================
# SYNC WRAPPER: Run identity resolution from sync or async callers (production)
# =============================================================================
# Callers (brightdata_scraper, pipeline_orchestrator_streaming) may be in a
# sync context or inside an already-running event loop. This helper runs
# resolve_influencer_identity_with_openai in a thread when loop is running,
# else asyncio.run(); returns identity dict or error_fallback on timeout/exception.
# =============================================================================

def run_identity_resolution_sync(
    profile_url: str,
    username: str,
    full_name: Optional[str] = None,
    biography: Optional[str] = None,
    external_url: Optional[str] = None,
    timeout_seconds: int = 10,
) -> Dict:
    """
    Run resolve_influencer_identity_with_openai from synchronous code.
    Safe when called from sync context or from code already inside an event loop.
    """
    import concurrent.futures

    def _run() -> Dict:
        return asyncio.run(
            resolve_influencer_identity_with_openai(
                profile_url=profile_url,
                username=username,
                full_name=full_name,
                biography=biography,
                external_url=external_url,
            )
        )

    try:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop is not None:
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                future = pool.submit(_run)
                return future.result(timeout=timeout_seconds)
        return _run()
    except Exception as e:
        logger.warning("Identity resolution failed for @%s: %s", username, e)
        return {
            "profession": "Digital Creator",
            "confidence": 0.0,
            "reason": str(e),
            "source": "error_fallback",
        }


# ========================================================================
# OLD FUNCTIONS REMOVED
# ========================================================================
# The following functions have been removed as they're no longer needed:
# - infer_profession_from_profile() - Replaced by OpenAI Web Search
# - strict_profession_match() - No longer needed, OpenAI ensures profession match
#
# The new workflow uses OpenAI Web Search as the authority for profession
# identification and peer discovery, eliminating the need for these functions.


# ========================================================================
# INDUSTRY STANDARD EXPANSION (CORE LOGIC)
# ========================================================================

def _is_specific_person_search(results: List[Dict], parsed_query: Dict) -> bool:
    """
    Check if this is a specific person search (single profile ONLY).
    Industry standards should ONLY run for single profile searches, NOT for top 3/5 searches.
    Top 3/5 searches should use internal comparison (comparing results against each other).
    
    Returns True ONLY if it's a single profile search (len(results) == 1).
    """
    if not results:
        return False
    
    # CRITICAL: Industry standards should ONLY run for single profile searches
    # Top 3/5 searches should NOT trigger industry standards - they use internal comparison
    if len(results) > 1:
        logger.debug(f"Industry standards skipped: {len(results)} results (not a single profile search)")
        return False
    
    # Only proceed if we have exactly 1 result (single profile search)
    
    # CRITICAL FIX: Check for DIRECT_PROFILE mode first (URL or username searches)
    search_mode = parsed_query.get("search_mode", "")
    if search_mode == "DIRECT_PROFILE":
        logger.debug("Industry standards enabled: DIRECT_PROFILE mode detected (single profile search)")
        return True
    
    # Also check if the result itself has an Instagram profile link (for direct profile searches)
    if len(results) == 1:
        result = results[0]
        profile_link = result.get("profile_link") or result.get("profile_url") or result.get("url", "")
        if profile_link and "instagram.com" in str(profile_link).lower():
            logger.debug("Industry standards enabled: Instagram profile link found in result")
            return True
    
    user_query = parsed_query.get("original_query", "")
    is_instagram_url = "instagram.com" in user_query.lower() if user_query else False
    
    # Short query without search terms likely means specific person
    is_specific_person = False
    if user_query:
        query_lower = user_query.lower()
        search_terms = ["top", "find", "search", "list", "get", "show", "best", "influencers", "creators"]
        has_search_terms = any(term in query_lower for term in search_terms)
        is_specific_person = len(user_query) < 50 and not has_search_terms and not is_instagram_url
    
    # Enable industry standards ONLY for: Instagram URLs OR single result with specific person query
    return is_instagram_url or is_specific_person


def _store_industry_standards_status(conversation_id: str, status: str, results: Optional[List[Dict]] = None, error: Optional[str] = None) -> None:
    """
    Store industry standards processing status and results.
    
    Args:
        conversation_id: The conversation/search ID
        status: "processing" or "completed" or "error"
        results: Industry standards results (only when status is "completed")
        error: Error message (only when status is "error")
    """
    try:
        # Load existing session data
        session_data = temp_store.load_session(conversation_id) or {}
        
        # Update industry standards data
        from datetime import datetime
        session_data["industry_standards"] = {
            "status": status,
            "updated_at": datetime.utcnow().isoformat(),
        }
        
        if results is not None:
            session_data["industry_standards"]["results"] = results
            session_data["industry_standards"]["count"] = len(results)
        
        if error:
            session_data["industry_standards"]["error"] = error
        
        # Persist back
        temp_store.persist_session(conversation_id, session_data)
        logger.debug(f"✅ Stored industry standards status: {conversation_id} -> {status}")
        
    except Exception as e:
        logger.error(f"❌ Failed to store industry standards status: {e}")


def _store_industry_comparison_status(conversation_id: str, status: str, reason: str) -> None:
    """
    Store industry comparison status signal for UI feedback.
    
    Args:
        conversation_id: The conversation/search ID
        status: "pending" | "completed" | "skipped" | "failed"
        reason: Human-readable reason for the status
    """
    try:
        session_data = temp_store.load_session(conversation_id) or {}
        
        if "industry_comparison" not in session_data:
            session_data["industry_comparison"] = {}
        
        session_data["industry_comparison"]["status"] = status
        session_data["industry_comparison"]["reason"] = reason
        session_data["industry_comparison"]["updated_at"] = time.time()
        
        temp_store.persist_session(conversation_id, session_data)
        logger.debug(f"✅ Stored industry comparison status: {conversation_id} -> {status}")
    except Exception as e:
        logger.error(f"❌ Failed to store industry comparison status: {e}")


def get_industry_standards_status(conversation_id: str) -> Dict[str, any]:
    """
    Get industry standards processing status and results.
    
    Returns:
        {
            "status": "processing" | "completed" | "error" | "not_found",
            "results": [...],  # Only when status is "completed"
            "count": int,      # Only when status is "completed"
            "error": str,      # Only when status is "error"
            "industry_comparison": {
                "status": "pending" | "completed" | "skipped" | "failed",
                "reason": "Human-readable reason"
            }
        }
    """
    try:
        session_data = temp_store.load_session(conversation_id)
        if not session_data:
            return {
                "status": "not_found",
                "industry_comparison": {
                    "status": "not_found",
                    "reason": "No industry standards processing found"
                }
            }
        
        industry_data = session_data.get("industry_standards")
        if not industry_data:
            return {
                "status": "not_found",
                "industry_comparison": {
                    "status": "not_found",
                    "reason": "No industry standards processing found"
                }
            }
        
        # Get industry comparison status
        comparison_data = session_data.get("industry_comparison", {})
        
        return {
            "status": industry_data.get("status", "not_found"),
            "results": industry_data.get("results", []),
            "count": industry_data.get("count", 0),
            "error": industry_data.get("error"),
            "industry_comparison": {
                "status": comparison_data.get("status", "pending"),
                "reason": comparison_data.get("reason", "Processing...")
            }
        }
    except Exception as e:
        logger.error(f"❌ Failed to get industry standards status: {e}")
        return {
            "status": "error",
            "error": str(e),
            "industry_comparison": {
                "status": "failed",
                "reason": str(e)
            }
        }


async def _process_industry_standards_background(
    results: List[Dict],
    parsed_query: Dict,
    conversation_id: str
) -> None:
    """
    Background task to process industry standards.
    This runs asynchronously and stores results separately.
    
    CRITICAL: This function persists peers incrementally as they are enriched,
    updating status from processing → completed so frontend polling works reliably.
    
    FAILURE HANDLING:
    - If OpenAI Web Search fails → returns empty list, status="completed" (not error)
    - If no peers found → returns empty list, status="completed"
    - If all peers fail follower constraint → returns empty list, status="completed"
    - Only actual exceptions → status="error"
    
    The anchor influencer is always available in main search results, so no peers
    is not considered a failure - it's a valid outcome.
    """
    try:
        logger.info(f"[INDUSTRY_SEARCH_STARTED] Starting industry standards background processing for {conversation_id}")
        
        # Mark as processing with status signal
        _store_industry_standards_status(conversation_id, "processing")
        _store_industry_comparison_status(conversation_id, "processing", "Processing industry standards...")
        
        # Use the existing expand_industry_standards logic with incremental persistence
        industry_results = await _expand_industry_standards_internal(
            results, 
            parsed_query, 
            conversation_id=conversation_id  # Pass conversation_id for incremental persistence
        )
        
        if industry_results:
            # Mark as completed with results
            _store_industry_standards_status(conversation_id, "completed", results=industry_results)
            _store_industry_comparison_status(conversation_id, "completed", f"Found {len(industry_results)} industry peers")
            logger.info(f"[INDUSTRY_SEARCH_COMPLETED] Industry standards processing completed: {conversation_id} -> {len(industry_results)} results")
            
            # NOTE: Peers are already persisted incrementally during enrichment
            # This final merge ensures all peers are in main results storage
            try:
                from app.services import prompt_service
                existing_results = prompt_service.load_dynamic_results(conversation_id) or []
                
                # Ensure anchor is marked
                if existing_results and not any(r.get("industry_anchor") is True for r in existing_results):
                    existing_results[0]["industry_anchor"] = True
                    prompt_service.record_dynamic_results(conversation_id, existing_results)
                    prompt_service.persist_dynamic_results(conversation_id, existing_results)
                
                logger.info(f"✅ Industry peers already persisted incrementally during enrichment")
            except Exception as merge_error:
                logger.warning(f"⚠️ Failed to verify peer persistence: {merge_error}")
        else:
            # No industry standards found - mark as skipped
            _store_industry_standards_status(conversation_id, "completed", results=[])
            _store_industry_comparison_status(conversation_id, "skipped", "No industry peers found")
            logger.info(f"[INDUSTRY_SEARCH_SKIPPED] Industry standards processing completed: {conversation_id} -> no peers found (anchor still available)")
            
    except Exception as e:
        logger.error(f"[INDUSTRY_SEARCH_FAILED] Industry standards background processing failed: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        _store_industry_standards_status(conversation_id, "error", error=str(e))
        _store_industry_comparison_status(conversation_id, "failed", str(e))
    finally:
        # Clean up task tracking
        if conversation_id in _active_industry_discoveries:
            del _active_industry_discoveries[conversation_id]


def apply_follower_constraint(enriched_peers: List[Dict], anchor_followers: int) -> List[Dict]:
    """
    Apply flexible follower constraint with 50% minimum threshold.
    
    CRITICAL FIX: Changed from 70% to 50% to prevent dropping valid peers.
    Industry "standards" are recognizable peers, not clones with identical follower counts.
    
    Strategy:
    - Minimum threshold: 50% of anchor followers
    - Always keep top 2 peers minimum if profession matches (even if below threshold)
    - This ensures we find peers even when anchor has high follower counts
    
    Args:
        enriched_peers: List of enriched peer profiles from Spreadd
        anchor_followers: Follower count of anchor influencer
    
    Returns:
        Filtered list of peers that meet follower requirement (minimum 2 if available)
    """
    if anchor_followers == 0:
        logger.warning("Anchor has 0 followers, skipping follower constraint")
        return enriched_peers
    
    # FIXED: Use 50% minimum threshold (was 70% - too aggressive)
    threshold_ratio = 0.50  # 50% - flexible enough to find recognizable peers
    threshold = int(anchor_followers * threshold_ratio)
    
    filtered = []
    below_threshold = []
    
    for peer in enriched_peers:
        peer_followers = parse_followers_to_int(peer.get("followers", "0"))
        peer_username = peer.get("Id") or peer.get("username", "unknown")
        
        if peer_followers >= threshold:
            filtered.append(peer)
            logger.debug(f"✅ Peer @{peer_username} passed follower constraint: {peer_followers:,} >= {threshold:,} (50% of anchor)")
        else:
            below_threshold.append((peer, peer_followers))
            logger.debug(f"⚠️ Peer @{peer_username} below threshold: {peer_followers:,} < {threshold:,} (50% of anchor)")
    
    logger.info(f"Follower constraint: {len(enriched_peers)} peers → {len(filtered)} passed (threshold: {threshold:,} = 50% of {anchor_followers:,})")
    
    # CRITICAL FIX: Always keep minimum 2 peers if available (even if below threshold)
    # Industry standards are recognizable peers, not clones
    if len(filtered) < 2 and below_threshold:
        # Sort by followers (descending) and take top peers to reach minimum 2
        below_threshold.sort(key=lambda x: x[1], reverse=True)
        needed = 2 - len(filtered)
        
        for peer, peer_followers in below_threshold[:needed]:
            filtered.append(peer)
            peer_username = peer.get("Id") or peer.get("username", "unknown")
            logger.info(f"✅ Keeping peer @{peer_username} below threshold to meet minimum 2 peers requirement: {peer_followers:,} < {threshold:,}")
        
        logger.info(f"✅ Follower constraint: Kept minimum 2 peers (total: {len(filtered)})")
    
    return filtered


def rank_peers(peers: List[Dict]) -> List[Dict]:
    """
    Rank peers by priority: followers > verified > engagement.
    
    Args:
        peers: List of peer profiles
    
    Returns:
        Ranked list (top 2-3)
    """
    def calculate_rank_score(peer: Dict) -> float:
        """Calculate ranking score for a peer."""
        followers = parse_followers_to_int(peer.get("followers", "0"))
        engagement_rate_str = str(peer.get("engagement_rate", "0")).replace("%", "").strip()
        # Handle dash and other invalid values
        if engagement_rate_str in ("N/A", "NAN", "NULL", "NONE", "-", ""):
            engagement_rate = 0.0
        else:
            try:
                engagement_rate = float(engagement_rate_str or 0)
            except (ValueError, TypeError):
                engagement_rate = 0.0
        
        # Base score: followers (normalized)
        score = followers / 100000
        
        # Bonus: verified accounts
        if peer.get("is_verified"):
            score += 50
        
        # Bonus: business/professional accounts
        if peer.get("is_business_account") or peer.get("is_professional_account"):
            score += 10
        
        # Secondary: engagement rate (smaller weight)
        score += engagement_rate / 10
        
        return score
    
    # Sort by score (descending)
    ranked = sorted(peers, key=calculate_rank_score, reverse=True)
    
    # Return all ranked peers (no limit) - let frontend decide how many to display
    # CRITICAL: Limit to 2 peers max (1 anchor + 2 peers = 3 total)
    max_peers = 2
    limited_ranked = ranked[:max_peers]
    logger.info(f"Ranked {len(peers)} peers → returning top {len(limited_ranked)} (limited to {max_peers} for 3 total with anchor)")
    
    return limited_ranked


async def discover_industry_peers_early(
    anchor: Dict,
    parsed_query: Dict
) -> List[Dict[str, str]]:
    """
    OPTIMIZED: Discover industry peer usernames EARLY (before enrichment).
    Returns list of peer influencer dicts ready for parallel enrichment.
    
    This runs FAST (OpenAI only, no scraping) and returns usernames only.
    Includes caching and abort conditions.
    """
    if not ENABLE_INDUSTRY_STANDARDS:
        return []
    
    # Check if this is a specific person search
    test_results = [anchor]
    if not _is_specific_person_search(test_results, parsed_query):
        logger.debug("Industry expansion skipped: not a specific person search")
        return []
    
    # Extract anchor username
    anchor_username = (
        anchor.get("Id") or 
        anchor.get("username") or 
        anchor.get("NAME", "") or
        anchor.get("name", "")
    )
    if not anchor_username:
        profile_url = anchor.get("profile_link") or anchor.get("profile_url") or anchor.get("url", "")
        if profile_url and "instagram.com" in str(profile_url):
            from app.services.core.search_filters import extract_username_from_url as _extract_username_from_url
            anchor_username = _extract_username_from_url(str(profile_url))
    
    if not anchor_username:
        logger.debug("Industry expansion skipped: missing anchor username")
        return []
    
    # ========================================================================
    # CLEAR CACHE - Always fetch fresh peers for new searches
    # ========================================================================
    # CRITICAL FIX: Clear any existing cache for this username BEFORE proceeding
    # This ensures each new search gets fresh peer comparison data
    cache_key = hashlib.md5(f"{anchor_username}".encode()).hexdigest()
    if cache_key in _industry_standards_cache:
        del _industry_standards_cache[cache_key]
        logger.info(f"🗑️ Cleared existing cache for @{anchor_username} - will fetch fresh peers")
    
    # Get anchor profile URL for OpenAI
    anchor_url = (
        anchor.get("profile_link") or 
        anchor.get("profile_url") or 
        anchor.get("url", "") or
        f"https://www.instagram.com/{anchor_username}/"
    )
    
    logger.info(f"[INDUSTRY_SEARCH_STARTED] Early industry peer discovery for @{anchor_username}")
    
    # ========================================================================
    # STEP 1: OpenAI Web Search - Discover Profession & Peer URLs (FAST)
    # ========================================================================
    try:
        discovery_result = await discover_profession_and_peers_via_openai(anchor_url)
        profession = discovery_result.get("profession", "")
        peer_urls = discovery_result.get("peer_urls", [])
        
        # ABORT CONDITION: Check if we have enough peers
        if not profession or len(peer_urls) < 2:
            logger.info(f"[INDUSTRY_SEARCH_SKIPPED] Not enough peers: profession={profession}, peer_urls={len(peer_urls)}")
            return []
        
        logger.info(f"✅ OpenAI discovered: profession='{profession}', {len(peer_urls)} peer URLs")
        
    except Exception as e:
        logger.error(f"[INDUSTRY_SEARCH_FAILED] OpenAI Web Search failed: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return []
    
    # ========================================================================
    # STEP 2: Normalize Peer URLs to Usernames
    # ========================================================================
    peer_usernames = normalize_peer_urls_to_usernames(peer_urls, anchor_username)
    
    if not peer_usernames or len(peer_usernames) < 2:
        logger.info(f"[INDUSTRY_SEARCH_SKIPPED] Not enough valid usernames after normalization: {len(peer_usernames)}")
        return []
    
    logger.info(f"✅ Normalized to {len(peer_usernames)} peer usernames")
    
    # ========================================================================
    # STEP 3: Convert to Scraper-Compatible Format (usernames only, no enrichment yet)
    # ========================================================================
    peer_influencers = []
    # CRITICAL: Limit to exactly 2 peers (1 anchor + 2 peers = 3 total)
    for username in peer_usernames[:2]:  # Limit to exactly 2 peers
        peer_influencers.append({
            "username": username,
            "profile_link": f"https://www.instagram.com/{username}/",
            "name": username,  # Will be updated by scraper
            "_industry_profession": profession,  # Store for later tagging
            "_industry_reference_for": anchor_username
        })
    
    # ========================================================================
    # CACHE RESULTS
    # ========================================================================
    _industry_standards_cache[cache_key] = {
        "peer_influencers": peer_influencers,
        "profession": profession,
        "cached_at": time.time()
    }
    
    return peer_influencers


async def _expand_industry_standards_internal(
    results: List[Dict],
    parsed_query: Dict,
    conversation_id: Optional[str] = None
) -> List[Dict]:
    """
    Adds 2–3 industry-standard influencers from SAME profession using OpenAI Web Search.
    
    NEW WORKFLOW:
    1. Use OpenAI Web Search to discover profession and peer Instagram URLs
    2. Normalize peer URLs to usernames
    3. Enrich peers via Spreadd (scraper_a_serpapi_spreadd)
    4. Apply flexible follower constraint (>= 90% of anchor)
    5. Rank peers (followers > verified > engagement)
    6. Tag successful peers with industry_standard flags
    7. Return peers only (not merged with anchor)
    """
    if not ENABLE_INDUSTRY_STANDARDS or not results:
        return []

    # Check if this is a specific person search
    if not _is_specific_person_search(results, parsed_query):
        logger.debug("Industry expansion skipped: not a specific person search")
        return []

    anchor = results[0]
    # Extract anchor username
    anchor_username = (
        anchor.get("Id") or 
        anchor.get("username") or 
        anchor.get("NAME", "") or
        anchor.get("name", "")
    )
    if not anchor_username:
        profile_url = anchor.get("profile_link") or anchor.get("profile_url") or anchor.get("url", "")
        if profile_url and "instagram.com" in str(profile_url):
            from app.services.core.search_filters import extract_username_from_url as _extract_username_from_url
            anchor_username = _extract_username_from_url(str(profile_url))
    
    anchor_followers = parse_followers_to_int(anchor.get("followers", "0"))

    if not anchor_username or anchor_followers == 0:
        logger.debug("Industry expansion skipped: missing anchor username or followers")
        return []

    # Get anchor profile URL for OpenAI
    anchor_url = (
        anchor.get("profile_link") or 
        anchor.get("profile_url") or 
        anchor.get("url", "") or
        f"https://www.instagram.com/{anchor_username}/"
    )

    logger.info(f"🔄 Industry expansion started for @{anchor_username}")

    # ========================================================================
    # STEP 1: OpenAI Web Search - Discover Profession & Peer URLs
    # ========================================================================
    try:
        discovery_result = await discover_profession_and_peers_via_openai(anchor_url)
        profession = discovery_result.get("profession", "")
        peer_urls = discovery_result.get("peer_urls", [])
        
        if not profession or not peer_urls:
            logger.warning(f"OpenAI Web Search returned incomplete data: profession={profession}, peer_urls={len(peer_urls)}")
            return []
        
        logger.info(f"✅ OpenAI discovered: profession='{profession}', {len(peer_urls)} peer URLs")
        
    except Exception as e:
        logger.error(f"❌ OpenAI Web Search failed: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return []

    # ========================================================================
    # STEP 2: Normalize Peer URLs to Usernames
    # ========================================================================
    peer_usernames = normalize_peer_urls_to_usernames(peer_urls, anchor_username)
    
    if not peer_usernames:
        logger.warning("No valid peer usernames after normalization")
        return []
    
    logger.info(f"✅ Normalized to {len(peer_usernames)} peer usernames")

    # ========================================================================
    # STEP 3: Convert to Scraper-Compatible Format
    # ========================================================================
    peer_influencers = []
    for username in peer_usernames:
        peer_influencers.append({
            "username": username,
            "profile_link": f"https://www.instagram.com/{username}/",
            "name": username  # Will be updated by scraper
        })
    
    # ========================================================================
    # STEP 4: Enrich Peers via Spreadd ONLY (LIGHTWEIGHT PARALLEL - NO SerpAPI)
    # ========================================================================
    try:
        logger.info(f"[INDUSTRY_SEARCH_STARTED] Enriching {len(peer_influencers)} peers in parallel (Spreadd only, no SerpAPI)")
        
        # OPTIMIZED: Sequential Spreadd enrichment only (no SerpAPI for industry standards)
        # Pass conversation_id for incremental persistence
        enriched_peers = await _enrich_peers_parallel_spreadd_only(peer_influencers, conversation_id=conversation_id)
        
        if not enriched_peers:
            logger.warning("Peer enrichment returned no results")
            return []
        
        logger.info(f"[INDUSTRY_SEARCH_COMPLETED] Enriched {len(enriched_peers)} peer profiles")
        
    except Exception as e:
        logger.error(f"[INDUSTRY_SEARCH_FAILED] Peer enrichment failed: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        return []

    # ========================================================================
    # STEP 5: Apply Follower Constraint (Flexible: >= 90% of anchor)
    # ========================================================================
    filtered_peers = apply_follower_constraint(enriched_peers, anchor_followers)
    
    if not filtered_peers:
        logger.info("No peers passed follower constraint")
        return []

    # ========================================================================
    # STEP 6: Rank Peers
    # ========================================================================
    ranked_peers = rank_peers(filtered_peers)

    # ========================================================================
    # STEP 7: Tag Peers AFTER All Checks
    # ========================================================================
    for peer in ranked_peers:
        peer["industry_standard"] = True
        peer["industry_profession"] = profession
        peer["industry_reference_for"] = anchor_username
        
        peer_username = peer.get("Id") or peer.get("username", "unknown")
        logger.info(f"✅ Industry standard tagged: @{peer_username} ({profession})")

    logger.info(f"✅ Industry expansion complete: {len(ranked_peers)} industry standards found")
    
    return ranked_peers


def start_industry_standards_discovery(
    results: List[Dict],
    parsed_query: Dict,
    conversation_id: str
) -> bool:
    """
    SINGLE AUTHORITATIVE ENTRY POINT for industry standards discovery.
    Ensures discovery is triggered exactly once per conversation.
    
    Returns:
        True if discovery was started (or already in progress), False if skipped
    """
    if not ENABLE_INDUSTRY_STANDARDS:
        return False
    
    # Check if this is a specific person search
    if not _is_specific_person_search(results, parsed_query):
        logger.debug(f"Industry standards discovery skipped: not a specific person search for {conversation_id}")
        return False
    
    # CRITICAL: Check if discovery has already started for this conversation
    if conversation_id in _active_industry_discoveries:
        existing_task = _active_industry_discoveries[conversation_id]
        if not existing_task.done():
            logger.info(f"✅ Industry standards discovery already in progress for {conversation_id}, skipping duplicate trigger")
            return True
        else:
            # Task completed, clean up
            del _active_industry_discoveries[conversation_id]
    
    # Check status in temp_store to avoid duplicate execution
    try:
        status_data = get_industry_standards_status(conversation_id)
        current_status = status_data.get("industry_comparison", {}).get("status", "")
        if current_status in ["processing", "pending"]:
            logger.info(f"✅ Industry standards discovery already marked as processing for {conversation_id}, skipping duplicate trigger")
            return True
        if current_status == "completed":
            logger.info(f"✅ Industry standards discovery already completed for {conversation_id}, skipping duplicate trigger")
            return True
    except Exception as e:
        logger.debug(f"Could not check status for {conversation_id}: {e}")
    
    # Start discovery task
    try:
        loop = asyncio.get_running_loop()
        task = loop.create_task(_process_industry_standards_background(results, parsed_query, conversation_id))
        _active_industry_discoveries[conversation_id] = task
        logger.info(f"🚀 Started industry standards discovery for {conversation_id} (single entry point)")
        return True
    except RuntimeError:
        # No event loop running, create a new one in a thread
        import threading
        def run_in_thread():
            new_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(new_loop)
            try:
                new_loop.run_until_complete(_process_industry_standards_background(results, parsed_query, conversation_id))
            finally:
                new_loop.close()
                # Clean up tracking
                if conversation_id in _active_industry_discoveries:
                    del _active_industry_discoveries[conversation_id]
        
        thread = threading.Thread(target=run_in_thread, daemon=True)
        thread.start()
        logger.info(f"🚀 Started industry standards discovery (thread) for {conversation_id} (single entry point)")
        return True
    except Exception as e:
        logger.error(f"❌ Failed to start industry standards discovery: {e}")
        return False


def trigger_industry_standards_background(
    results: List[Dict],
    parsed_query: Dict,
    conversation_id: str
) -> None:
    """
    DEPRECATED: Use start_industry_standards_discovery instead.
    Kept for backward compatibility but delegates to single entry point.
    """

    start_industry_standards_discovery(results, parsed_query, conversation_id)


# ========================================================================
# PROFESSION PEERS FOR TOP SEARCHES (Background Task)
# ========================================================================

async def discover_profession_peers_with_target(
    anchor_url: str,
    target_followers: int
) -> Dict[str, any]:
    """
    Discover profession peers with specific target follower count (OpenAI).
    Used for "Profession Peers" comparison in top influencer searches.
    
    Args:
        anchor_url: Instagram profile URL/username
        target_followers: Desired follower count (approximate)
    
    Returns:
        {"profession": "...", "peer_urls": [...]}
    """
    try:
        client = get_openai_client()
        model = get_openai_model()
        
        # Normalize input
        if not anchor_url.startswith("http"):
            anchor_url = f"https://www.instagram.com/{anchor_url.lstrip('@')}/"
            
        followers_fmt = f"{target_followers:,}"
        if target_followers >= 1_000_000:
            followers_fmt = f"{target_followers/1_000_000:.1f}M"
        elif target_followers >= 1_000:
            followers_fmt = f"{target_followers/1_000:.1f}K"
        
        prompt = f"""You are an expert at finding specific Instagram influencers.

Given this Instagram profile: {anchor_url}

Task: Find EXACTLY 2 other Instagram accounts that:
1. Are in the EXACT SAME profession/category (e.g., if anchor is a Fashion Blogger, find other Fashion Bloggers)
2. Have approximately {followers_fmt} followers (plus/minus 30%)
3. Are NOT the top industry mega-stars/celebrities (unless target is very high)

STRICT RULES:
- Must match profession EXACTLY (no "similar" fields)
- Must be close to {followers_fmt} followers
- Return FULL NAMES or USERNAMES
- Return EXACTLY 2 accounts

Respond in JSON:
{{
    "profession": "Specific Profession",
    "peer_names": ["Name1", "Name2"]
}}"""

        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": "You are an expert Instagram researcher. Find peers with specific follower counts valid JSON."},
                {"role": "user", "content": prompt}
            ],
            temperature=0.2,
            max_tokens=1000,
            response_format={"type": "json_object"}
        )
        
        data = json.loads(response.choices[0].message.content)
        profession = data.get("profession", "")
        peer_names = data.get("peer_names", [])
        
        logger.info(f"🔍 OpenAI target discovery ({followers_fmt}): profession='{profession}', peer_names={peer_names}")
        
        if not profession or len(peer_names) < 2:
            return {"profession": "", "peer_urls": []}
            
        # Use SerpAPI to find actual usernames
        peer_urls = []
        for name in peer_names[:2]:
            if isinstance(name, str) and name.strip():
                username = await _search_instagram_username_via_serpapi(name.strip())
                if username:
                    peer_urls.append(f"https://www.instagram.com/{username}/")
        
        return {
            "profession": profession,
            "peer_urls": peer_urls
        }

    except Exception as e:
        logger.error(f"❌ Target peer discovery failed: {e}")
        return {"profession": "", "peer_urls": []}


async def start_profession_peers_background(
    anchor: Dict,
    parsed_query: Dict,
    conversation_id: str,
    follower_multiplier: float = 5.0
) -> None:
    """
    Background task to discover profession peers for TOP SEARCHES.
    
    Workflow:
    1. Calculate target followers (approx 5x anchor)
    2. OpenAI: Discover profession + peer names
    3. SerpAPI: Get usernames
    4. Spreadd: Enrich profiles
    5. Cache results for polling
    """
    try:
        logger.info(f"🔄 Starting profession peers background task for {conversation_id}")
        _store_profession_peers_status(conversation_id, "processing")
        
        # Calculate target
        anchor_followers = parse_followers_to_int(anchor.get("followers", "0"))
        if anchor_followers == 0:
            # Fallback if anchor has no follower data
            anchor_followers = 50_000 
            
        target_followers = int(anchor_followers * follower_multiplier)
        # Cap limits (min 50k, max 50M)
        target_followers = max(50_000, min(50_000_000, target_followers))
        
        anchor_username = anchor.get("Id") or anchor.get("username", "")
        logger.info(f"🎯 Target: {target_followers:,} followers (5x of @{anchor_username}'s {anchor_followers:,})")
        
        # Step 1: Discover
        discovery_result = await discover_profession_peers_with_target(
            anchor_username, target_followers
        )
        profession = discovery_result.get("profession", "")
        peer_urls = discovery_result.get("peer_urls", [])
        
        if not peer_urls:
            logger.warning("⚠️ No profession peers found")
            _store_profession_peers_status(conversation_id, "completed", [])
            return

        # Step 2: Normalize
        peer_usernames = normalize_peer_urls_to_usernames(peer_urls, anchor_username)
        
        # Step 3: Prepare for enrichment
        peer_influencers = []
        for username in peer_usernames:
            peer_influencers.append({
                "username": username,
                "profile_link": f"https://www.instagram.com/{username}/",
                "_industry_profession": profession,
                "industry_standard": True  # Tag for frontend
            })
            
        # Step 4: Enrich using Spreadd ONLY (same as URL/Username peer comparison)
        # This is FASTER than scraper_a_serpapi_spreadd which uses SerpAPI + Spreadd
        # Using the same function as industry standards for consistency
        
        if peer_influencers:
            logger.info(f"🔄 Enriching {len(peer_influencers)} profession peers (Spreadd only)...")
            
            # Use the same Spreadd-only enrichment as URL/Username peer comparison
            # This is faster and more consistent
            enriched_peers = await _enrich_peers_parallel_spreadd_only(peer_influencers, conversation_id=conversation_id)
            
            # Sort by followers descending
            enriched_peers.sort(
                key=lambda x: parse_followers_to_int(x.get("followers", "0")), 
                reverse=True
            )
            
            # Limit to top 2
            final_peers = enriched_peers[:2]
            
            # Tag peers with industry_standard flag for frontend
            for peer in final_peers:
                peer["industry_standard"] = True
                peer["_industry_profession"] = profession
            
            logger.info(f"✅ Profession peers task completed: {len(final_peers)} peers found")
            _store_profession_peers_status(conversation_id, "completed", final_peers)

        else:
            _store_profession_peers_status(conversation_id, "completed", [])

    except Exception as e:
        logger.error(f"❌ Profession peers background task failed: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        _store_profession_peers_status(conversation_id, "error", error=str(e))


