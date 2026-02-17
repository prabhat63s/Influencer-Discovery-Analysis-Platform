# Discovery Service
# =================
# Handles the discovery of influencers via web search (SerpAPI).
# Extracted from dynamic_search.py to centralize discovery logic.

from __future__ import annotations

import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Set

from app.config.settings import settings
from app.services.scrapers.serpapi_service import get_google_search, SERP_API_KEY
from app.services.core.search_filters import (
    extract_username_from_url as _extract_username_from_url,
    extract_rate_range as _extract_rate_range,
)
from app.utils.image_utils import extract_profile_image

logger = logging.getLogger(__name__)

# ========================================================================
# CONFIGURATION
# ========================================================================

# Results per request; filter=0 to avoid Google's "similar" collapsing.
# Target total profiles to discover (we paginate with start= to reach this).
TARGET_DISCOVERY_PROFILES = 1000
# Results per SerpAPI page (Google typically returns up to 10 per page).
SERP_PAGE_SIZE = 10
SERP_DISCOVERY_NUM = SERP_PAGE_SIZE
SERP_DISCOVERY_FILTER = "0"

# Location string (as used in UI/parser) -> (SerpAPI location, country code gl).
# CRITICAL: RESTRICTED TO INDIA ONLY per system requirements.
_LOCATION_TO_SERP = {
    "india": ("India", "in"),
    "mumbai": ("Mumbai, Maharashtra, India", "in"),
    "delhi": ("Delhi, India", "in"),
    "bangalore": ("Bangalore, Karnataka, India", "in"),
    "chennai": ("Chennai, Tamil Nadu, India", "in"),
    "hyderabad": ("Hyderabad, Telangana, India", "in"),
    "kolkata": ("Kolkata, West Bengal, India", "in"),
    "pune": ("Pune, Maharashtra, India", "in"),
    "ahmedabad": ("Ahmedabad, Gujarat, India", "in"),
    "jaipur": ("Jaipur, Rajasthan, India", "in"),
    "surat": ("Surat, Gujarat, India", "in"),
    "lucknow": ("Lucknow, Uttar Pradesh, India", "in"),
    "kanpur": ("Kanpur, Uttar Pradesh, India", "in"),
    "nagpur": ("Nagpur, Maharashtra, India", "in"),
    "indore": ("Indore, Madhya Pradesh, India", "in"),
    "thane": ("Thane, Maharashtra, India", "in"),
    "bhopal": ("Bhopal, Madhya Pradesh, India", "in"),
    "visakhapatnam": ("Visakhapatnam, Andhra Pradesh, India", "in"),
    "patna": ("Patna, Bihar, India", "in"),
    "vadodara": ("Vadodara, Gujarat, India", "in"),
    "ghaziabad": ("Ghaziabad, Uttar Pradesh, India", "in"),
    "ludhiana": ("Ludhiana, Punjab, India", "in"),
    "agra": ("Agra, Uttar Pradesh, India", "in"),
    "nashik": ("Nashik, Maharashtra, India", "in"),
    "faridabad": ("Faridabad, Haryana, India", "in"),
    "meerut": ("Meerut, Uttar Pradesh, India", "in"),
    "rajkot": ("Rajkot, Gujarat, India", "in"),
    "kalyan-dombivli": ("Kalyan-Dombivli, Maharashtra, India", "in"),
    "vasai-virar": ("Vasai-Virar, Maharashtra, India", "in"),
    "varanasi": ("Varanasi, Uttar Pradesh, India", "in"),
    "srinagar": ("Srinagar, Jammu and Kashmir, India", "in"),
    "aurangabad": ("Aurangabad, Maharashtra, India", "in"),
    "dhanbad": ("Dhanbad, Jharkhand, India", "in"),
    "amritsar": ("Amritsar, Punjab, India", "in"),
    "navi mumbai": ("Navi Mumbai, Maharashtra, India", "in"),
    "allahabad": ("Allahabad, Uttar Pradesh, India", "in"),
    "ranchi": ("Ranchi, Jharkhand, India", "in"),
    "howrah": ("Howrah, West Bengal, India", "in"),
    "coimbatore": ("Coimbatore, Tamil Nadu, India", "in"),
    "jabalpur": ("Jabalpur, Madhya Pradesh, India", "in"),
    "gwalior": ("Gwalior, Madhya Pradesh, India", "in"),
    "vijayawada": ("Vijayawada, Andhra Pradesh, India", "in"),
    "jodhpur": ("Jodhpur, Rajasthan, India", "in"),
    "madurai": ("Madurai, Tamil Nadu, India", "in"),
    "raipur": ("Raipur, Chhattisgarh, India", "in"),
    "kota": ("Kota, Rajasthan, India", "in"),
    "guwahati": ("Guwahati, Assam, India", "in"),
    "chandigarh": ("Chandigarh, India", "in"),
    "solapur": ("Solapur, Maharashtra, India", "in"),
    "hubli-dharwad": ("Hubli-Dharwad, Karnataka, India", "in"),
    "mysore": ("Mysore, Karnataka, India", "in"),
    "tiruchirappalli": ("Tiruchirappalli, Tamil Nadu, India", "in"),
    "bareilly": ("Bareilly, Uttar Pradesh, India", "in"),
    "aligarh": ("Aligarh, Uttar Pradesh, India", "in"),
    "tiruppur": ("Tiruppur, Tamil Nadu, India", "in"),
    "gurgaon": ("Gurgaon, Haryana, India", "in"),
    "moradabad": ("Moradabad, Uttar Pradesh, India", "in"),
    "jalandhar": ("Jalandhar, Punjab, India", "in"),
    "bhubaneswar": ("Bhubaneswar, Odisha, India", "in"),
    "salem": ("Salem, Tamil Nadu, India", "in"),
    "warangal": ("Warangal, Telangana, India", "in"),
    "mira-bhayandar": ("Mira-Bhayandar, Maharashtra, India", "in"),
    "jalgaon": ("Jalgaon, Maharashtra, India", "in"),
    "guntur": ("Guntur, Andhra Pradesh, India", "in"),
    "trivandrum": ("Thiruvananthapuram, Kerala, India", "in"),
    "bhiwandi": ("Bhiwandi, Maharashtra, India", "in"),
    "saharanpur": ("Saharanpur, Uttar Pradesh, India", "in"),
    "gorakhpur": ("Gorakhpur, Uttar Pradesh, India", "in"),
    "bikaner": ("Bikaner, Rajasthan, India", "in"),
    "amravati": ("Amravati, Maharashtra, India", "in"),
    "noida": ("Noida, Uttar Pradesh, India", "in"),
    "jamshedpur": ("Jamshedpur, Jharkhand, India", "in"),
    "bhilai": ("Bhilai, Chhattisgarh, India", "in"),
    "cuttack": ("Cuttack, Odisha, India", "in"),
    "firozabad": ("Firozabad, Uttar Pradesh, India", "in"),
    "kochi": ("Kochi, Kerala, India", "in"),
    "bhavnagar": ("Bhavnagar, Gujarat, India", "in"),
    "dehradun": ("Dehradun, Uttarakhand, India", "in"),
    "durgapur": ("Durgapur, West Bengal, India", "in"),
    "asansol": ("Asansol, West Bengal, India", "in"),
    "nanded": ("Nanded, Maharashtra, India", "in"),
    "kolhapur": ("Kolhapur, Maharashtra, India", "in"),
    "ajmer": ("Ajmer, Rajasthan, India", "in"),
    "gulbarga": ("Gulbarga, Karnataka, India", "in"),
    "jamnagar": ("Jamnagar, Gujarat, India", "in"),
    "ujjain": ("Ujjain, Madhya Pradesh, India", "in"),
    "loni": ("Loni, Uttar Pradesh, India", "in"),
    "siliguri": ("Siliguri, West Bengal, India", "in"),
    "jhansi": ("Jhansi, Uttar Pradesh, India", "in"),
    "ulhasnagar": ("Ulhasnagar, Maharashtra, India", "in"),
    "jammu": ("Jammu, Jammu and Kashmir, India", "in"),
    "sangli-miraj-kupwad": ("Sangli-Miraj & Kupwad, Maharashtra, India", "in"),
    "mangalore": ("Mangalore, Karnataka, India", "in"),
    "erode": ("Erode, Tamil Nadu, India", "in"),
    "belgaum": ("Belgaum, Karnataka, India", "in"),
    "ambattur": ("Ambattur, Tamil Nadu, India", "in"),
    "tirunelveli": ("Tirunelveli, Tamil Nadu, India", "in"),
    "malegaon": ("Malegaon, Maharashtra, India", "in"),
    "gaya": ("Gaya, Bihar, India", "in"),
    "jalna": ("Jalna, Maharashtra, India", "in"),
    "udaipur": ("Udaipur, Rajasthan, India", "in"),
    "maheshtala": ("Maheshtala, West Bengal, India", "in"),
    "davanagere": ("Davanagere, Karnataka, India", "in"),
    "kozhikode": ("Kozhikode, Kerala, India", "in"),
    "kurnool": ("Kurnool, Andhra Pradesh, India", "in"),
    "rajpur sonarpur": ("Rajpur Sonarpur, West Bengal, India", "in"),
    "rajahmundry": ("Rajahmundry, Andhra Pradesh, India", "in"),
    "bokaro": ("Bokaro, Jharkhand, India", "in"),
    "south dumdum": ("South Dumdum, West Bengal, India", "in"),
    "bellary": ("Bellary, Karnataka, India", "in"),
    "patiala": ("Patiala, Punjab, India", "in"),
    "gopalpur": ("Gopalpur, West Bengal, India", "in"),
    "agartala": ("Agartala, Tripura, India", "in"),
    "bhagalpur": ("Bhagalpur, Bihar, India", "in"),
    "muzaffarnagar": ("Muzaffarnagar, Uttar Pradesh, India", "in"),
    "bhatpara": ("Bhatpara, West Bengal, India", "in"),
    "panihati": ("Panihati, West Bengal, India", "in"),
    "latur": ("Latur, Maharashtra, India", "in"),
    "dhule": ("Dhule, Maharashtra, India", "in"),
    "tirupati": ("Tirupati, Andhra Pradesh, India", "in"),
    "rohtak": ("Rohtak, Haryana, India", "in"),
    "korba": ("Korba, Chhattisgarh, India", "in"),
    "bhilwara": ("Bhilwara, Rajasthan, India", "in"),
    "berhampur": ("Berhampur, Odisha, India", "in"),
    "muzaffarpur": ("Muzaffarpur, Bihar, India", "in"),
    "ahmednagar": ("Ahmednagar, Maharashtra, India", "in"),
    "mathura": ("Mathura, Uttar Pradesh, India", "in"),
    "kollam": ("Kollam, Kerala, India", "in"),
    "avadi": ("Avadi, Tamil Nadu, India", "in"),
    "kadapa": ("Kadapa, Andhra Pradesh, India", "in"),
    "kamarhati": ("Kamarhati, West Bengal, India", "in"),
    "sambalpur": ("Sambalpur, Odisha, India", "in"),
    "bilaspur": ("Bilaspur, Chhattisgarh, India", "in"),
    "shahjahanpur": ("Shahjahanpur, Uttar Pradesh, India", "in"),
    "satara": ("Satara, Maharashtra, India", "in"),
    "bijapur": ("Bijapur, Karnataka, India", "in"),
    "rampour": ("Rampur, Uttar Pradesh, India", "in"),
    "shimoga": ("Shimoga, Karnataka, India", "in"),
    "chandrapur": ("Chandrapur, Maharashtra, India", "in"),
    "junagadh": ("Junagadh, Gujarat, India", "in"),
    "thrissur": ("Thrissur, Kerala, India", "in"),
    "alwar": ("Alwar, Rajasthan, India", "in"),
    "bardhaman": ("Bardhaman, West Bengal, India", "in"),
    "kulti": ("Kulti, West Bengal, India", "in"),
    "kakinada": ("Kakinada, Andhra Pradesh, India", "in"),
    "nizamabad": ("Nizamabad, Telangana, India", "in"),
    "parbhani": ("Parbhani, Maharashtra, India", "in"),
    "tumkur": ("Tumkur, Karnataka, India", "in"),
    "khammam": ("Khammam, Telangana, India", "in"),
    "ozhukarai": ("Ozhukarai, Puducherry, India", "in"),
    "bihar sharif": ("Bihar Sharif, Bihar, India", "in"),
    "panipat": ("Panipat, Haryana, India", "in"),
    "darbhanga": ("Darbhanga, Bihar, India", "in"),
    "bally": ("Bally, West Bengal, India", "in"),
    "aizawl": ("Aizawl, Mizoram, India", "in"),
    "dewas": ("Dewas, Madhya Pradesh, India", "in"),
    "ichalkaranji": ("Ichalkaranji, Maharashtra, India", "in"),
    "karnal": ("Karnal, Haryana, India", "in"),
    "bathinda": ("Bathinda, Punjab, India", "in"),
    "jalna": ("Jalna, Maharashtra, India", "in"),
    "eluru": ("Eluru, Andhra Pradesh, India", "in"),
    "kirari sulemnagar": ("Kirari Suleman Nagar, Delhi, India", "in"),
    "barasat": ("Barasat, West Bengal, India", "in"),
    "purnia": ("Purnia, Bihar, India", "in"),
    "satna": ("Satna, Madhya Pradesh, India", "in"),
    "mau": ("Mau, Uttar Pradesh, India", "in"),
    "sonipat": ("Sonipat, Haryana, India", "in"),
    "farrukhabad": ("Farrukhabad, Uttar Pradesh, India", "in"),
    "sagar": ("Sagar, Madhya Pradesh, India", "in"),
    "rourkela": ("Rourkela, Odisha, India", "in"),
    "durg": ("Durg, Chhattisgarh, India", "in"),
    "imphal": ("Imphal, Manipur, India", "in"),
    "ratlam": ("Ratlam, Madhya Pradesh, India", "in"),
    "hapur": ("Hapur, Uttar Pradesh, India", "in"),
    "arrah": ("Arrah, Bihar, India", "in"),
    "karimnagar": ("Karimnagar, Telangana, India", "in"),
    "anantapur": ("Anantapur, Andhra Pradesh, India", "in"),
    "eta": ("Etawah, Uttar Pradesh, India", "in"),
    "ambernath": ("Ambernath, Maharashtra, India", "in"),
    "north dumdum": ("North Dumdum, West Bengal, India", "in"),
    "bharatpur": ("Bharatpur, Rajasthan, India", "in"),
    "begusarai": ("Begusarai, Bihar, India", "in"),
    "new delhi": ("New Delhi, Delhi, India", "in"),
    "gandhidham": ("Gandhidham, Gujarat, India", "in"),
    "baranagar": ("Baranagar, West Bengal, India", "in"),
    "tiruvottiyur": ("Tiruvottiyur, Tamil Nadu, India", "in"),
    "pondicherry": ("Puducherry, India", "in"),
    "katihar": ("Katihar, Bihar, India", "in"),
    "sikar": ("Sikar, Rajasthan, India", "in"),
    "thoubal": ("Thoubal, Manipur, India", "in"),
    "narara": ("Narara, Gujarat, India", "in"),
    "shillong": ("Shillong, Meghalaya, India", "in"),
    "rewex": ("Rewa, Madhya Pradesh, India", "in"),
    "shimla": ("Shimla, Himachal Pradesh, India", "in"),
    "gangtok": ("Gangtok, Sikkim, India", "in"),
    "haldwani": ("Haldwani, Uttarakhand, India", "in"),
    "itanagar": ("Itanagar, Arunachal Pradesh, India", "in"),
    "kohima": ("Kohima, Nagaland, India", "in"),
    "dimapur": ("Dimapur, Nagaland, India", "in"),
    "panaji": ("Panaji, Goa, India", "in"),
    "margao": ("Margao, Goa, India", "in"),
    "vasco da gama": ("Vasco da Gama, Goa, India", "in")
}



def _serp_geo_for_location(location: str) -> Tuple[str, str]:
    # Resolve (SerpAPI location string, gl) for a given location. Default: India.
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
    # Build a single SerpAPI query: site:instagram.com "niche" "location" "min..max followers".
    # Uses raw numbers for the range so Google can apply numeric filtering.
    niche = (niche or "influencer").strip() or "influencer"
    
    # CRITICAL: Default to India if no location specified
    location = (location or "India").strip() or "India"
    
    min_f = min_followers if min_followers is not None else 1000
    max_f = max_followers if max_followers is not None else 900000
    min_f = max(1, int(min_f))
    max_f = max(min_f, int(max_f))
    follower_part = f'"{min_f}..{max_f} followers"'
    return f'site:instagram.com "{niche}" "{location}" {follower_part}'


def _build_discovery_query_simple(niche: str, location: str) -> str:
    # Simpler query without numeric follower range (Google often returns no results for strict ranges).
    # Used as fallback when primary discovery returns too few profiles.
    niche = (niche or "influencer").strip() or "influencer"
    location = (location or "India").strip() or "India"
    return f'site:instagram.com "{niche}" "{location}" influencer'


from app.services.data.memory_cache import cache
import json

def _run_serp_search(params: Dict) -> List[Dict]:
    # Execute SerpAPI search (sync) via canonical serpapi_service; returns organic_results or [].
    # Create a stable cache key from query params
    # Sort keys to ensure deterministic string representation
    cache_key = f"serp_discovery:{json.dumps(params, sort_keys=True)}"
    
    # Check cache
    cached_data = cache.get(cache_key)
    if cached_data is not None:
        logger.info(f"⚡ Cache hit for discovery query: {params.get('q', '')[:30]}...")
        return cached_data

    try:
        data = get_google_search(params).get_dict()
    except Exception as e:
        logger.warning("SerpAPI request failed: %s", e)
        return []
        
    if data.get("error"):
        logger.warning("SerpAPI error: %s", data.get("error"))
        return []
        
    results = data.get("organic_results") or []
    
    # Cache successful results for 24 hours (86400 seconds)
    if results:
        cache.set(cache_key, results, ttl_seconds=86400)
        
    return results


def _organic_results_to_influencers(
    organic_results: List[Dict],
    seen_usernames: Set[str],
    niche_hint: str = "",
    location_hint: str = "",
) -> List[Dict]:
    # Parse SerpAPI organic results into influencer dicts; updates seen_usernames.
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

        # Validate via Pydantic model
        from app.models.schema import SearchResult
        
        try:
            profile = SearchResult(
                username=username,
                name=name,
                profile_link=normalized_url,
                profile_pic_url=profile_pic_url,
                original_url=link, # extra field, will be ignored by model but useful if we keep dict
                niche=niche_hint,
                location=location_hint,
                rate=rate_range.get("rate"),
                min_rate=rate_range.get("min_rate"),
                max_rate=rate_range.get("max_rate")
            )
            # Return as dict for now to maintain pipeline compatibility
            # In validation phase, we can switch to passing objects
            out.append(profile.model_dump(exclude_none=True))
        except Exception as e:
            logger.warning(f"Skipping invalid profile {username}: {e}")
            continue
            
    return out


async def discover_influencers_from_prompt(parsed_query: Dict) -> List[Dict[str, str]]:
    # Discover Instagram influencers via structured SerpAPI query(ies).
    # Fetches 10 pages (start=0, 10, 20, ... 90) in parallel, then merges and dedupes.
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
    seen: Set[str] = set()
    discovered: List[Dict[str, str]] = []
    for organic_results in pages_organic:
        page = _organic_results_to_influencers(
            organic_results or [], seen, niche_hint=niche, location_hint=location
        )
        discovered.extend(page)

    logger.info("Discovery finished: %d profiles", len(discovered))
    return discovered


def _generate_fallback_search_queries(parsed: Dict) -> List[str]:
    # Generate fallback search queries based on parsed parameters.
    # CRITICAL FIX: Now generates queries HEAVILY BIASED toward the HIGH END of follower range.
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
            # Format follower count for search queries
            if count >= 1000000:
                return f"{count / 1000000:.1f}M followers"
            elif count >= 1000:
                return f"{int(count / 1000)}k followers"
            return f"{count} followers"

        if min_followers and max_followers:
            range_size = max_followers - min_followers
            
            # Calculate HIGH percentiles (80th, 90th, 95th, 98th) - heavily favor upper end
            percentile_80 = min_followers + int(range_size * 0.80)  # For 400k-900k -> 800k
            percentile_90 = min_followers + int(range_size * 0.90)  # For 400k-900k -> 850k
            percentile_95 = min_followers + int(range_size * 0.95)  # For 400k-900k -> 875k
            percentile_98 = min_followers + int(range_size * 0.98)  # For 400k-900k -> 890k
            
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
