"""
Ranking and search helpers.
- parse_followers_to_int, parse_rate_to_int
- sort_results_by_relevance (rank by niche, followers, quality)
- remove_duplicates, merge helpers
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from typing import Dict, List, Optional, Any
import re
from app.utils.parsing import parse_number, parse_percentage

logger = logging.getLogger(__name__)


# ============================================================================
# STRING EXTRACTION UTILITIES
# ============================================================================

def extract_username_from_url(url: str) -> Optional[str]:
    """
    Extract username from Instagram URL, filtering out posts/reels/stories.
    """
    if not url:
        return None

    # Parse URL
    url = str(url).strip().lower()

    # Filter out non-profile URLs (posts, reels, TV, stories, explore, etc.)
    invalid_patterns = ['/p/', '/reel/', '/tv/', '/stories/', '/explore/', '/accounts/', '/direct/']
    for pattern in invalid_patterns:
        if pattern in url:
            return None

    # Extract username from profile URL: instagram.com/username or instagram.com/username/
    match = re.search(r"instagram\.com/([a-zA-Z0-9._]+)/?(?:\?|$)", url)
    if match:
        username = match.group(1).strip().lstrip("@")
        if 1 <= len(username) <= 30 and re.match(r'^[a-zA-Z0-9._]+$', username):
            return username

    return None


def normalize_profile_url(u: Optional[str]) -> Optional[str]:
    """
    Normalize profile URL for consistent matching.
    Removes trailing slashes, normalizes www, handles http/https differences.
    """
    if not u:
        return None
    u = str(u).strip()
    # Remove query/fragment
    u = u.split('?')[0].split('#')[0].rstrip('/')
    # Add scheme if missing (safe normalization)
    if not (u.startswith('http://') or u.startswith('https://')):
        if u.startswith('www.'):
            u = 'https://' + u
        elif 'instagram.com' in u:
            u = 'https://' + u
        else:
            # If it's just a username, create full URL
            username = u.lstrip('@').strip()
            if username:
                u = f"https://www.instagram.com/{username}"
            else:
                return None
    # Remove 'www.' for consistent comparison
    u = u.replace('www.', '')
    return u.lower()


def normalize_instagram_url(url_or_username: str) -> Optional[str]:
    """
    Normalize URL to full Instagram URL format required by scrapers.
    Ensures https://www.instagram.com/... format.
    """
    normalized = normalize_profile_url(url_or_username)
    if normalized:
        # Ensure it has www. for external APIs that prefer it
        if 'instagram.com' in normalized and 'www.' not in normalized:
            return normalized.replace('https://instagram.com', 'https://www.instagram.com')
        return normalized
    return None


def extract_rate_range(text: str) -> Dict[str, Optional[int]]:
    """Extract rate/fee range (min-max) from text."""
    if not text:
        return {}
    
    # Normalize text
    text_clean = text
    text_lower = text.lower()
    
    min_rate = None
    max_rate = None
    
    # Pattern 1: Range format "₹X - ₹Y" with currency
    range_patterns = [
        r'₹\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*([km]?)\s*(?:-|to|–)\s*₹\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*([km]?)',
        r'(\d+(?:,\d+)*(?:\.\d+)?)\s*([km]?)\s*(?:-|to|–)\s*(\d+(?:,\d+)*(?:\.\d+)?)\s*([km]?)\s*(?:per|for|rate|fee)',
    ]
    
    for pattern in range_patterns:
        match = re.search(pattern, text_clean, re.IGNORECASE)
        if match:
            try:
                if len(match.groups()) >= 4:
                    num1 = float(match.group(1).replace(',', ''))
                    suffix1 = match.group(2).lower()
                    num2 = float(match.group(3).replace(',', ''))
                    suffix2 = match.group(4).lower()
                    
                    multiplier1 = 1000 if suffix1 == 'k' else (1000000 if suffix1 == 'm' else 1)
                    multiplier2 = 1000 if suffix2 == 'k' else (1000000 if suffix2 == 'm' else 1)
                    
                    min_rate = int(num1 * multiplier1)
                    max_rate = int(num2 * multiplier2)
                    
                    if min_rate and max_rate:
                        return {"min_rate": min(min_rate, max_rate), "max_rate": max(min_rate, max_rate)}
            except Exception:
                continue

    return {}


def extract_snippet_metrics(snippet: str) -> Dict[str, str]:
    """Extract metrics from SerpAPI snippet."""
    if not snippet:
        return {
            "followers_serp": "N/A",
            "following_serp": "N/A",
            "posts_serp": "N/A",
        }
    
    snippet_lower = snippet.lower().replace(",", "").replace("+", "")
    
    def find_metric(*patterns):
        for pattern in patterns:
            match = re.search(pattern, snippet_lower, re.IGNORECASE)
            if match:
                return match.group(1).upper().strip()
        return "N/A"
    
    followers = find_metric(r"([\d\.]+[km]?)\s*followers", r"followers[:\s]+([\d\.]+[km]?)")
    following = find_metric(r"([\d\.]+[km]?)\s*following", r"following[:\s]+([\d\.]+[km]?)")
    posts = find_metric(r"([\d\.]+[km]?)\s*posts", r"posts[:\s]+([\d\.]+[km]?)")
    
    return {
        "followers_serp": followers,
        "following_serp": following,
        "posts_serp": posts,
    }


# ============================================================================
# PARSING UTILITIES
# ============================================================================

def parse_followers_to_int(followers_str: str | int | float) -> int:
    """Legacy wrapper for centralized parse_number."""
    return parse_number(followers_str)


def parse_rate_to_int(rate_str: str) -> int:
    """Parse rate string to integer"""
    if not rate_str or rate_str in ("N/A", "null", "None", ""):
        return 0
    try:
        rate = str(rate_str).replace('₹', '').replace(',', '').replace('RS', '').replace('rs', '').strip()
        return int(float(rate))
    except (ValueError, AttributeError):
        return 0


def format_number(num: int) -> str:
    """Format number to K/M notation. Shared by calculate_avg_metric and scrapers."""
    if num >= 1_000_000:
        return f"{num / 1_000_000:.1f}M"
    if num >= 1_000:
        return f"{num / 1_000:.1f}K"
    return str(num)


def calculate_avg_metric(posts: list, metric: str) -> str:
    """Calculate average likes/comments from first 10 posts. Single implementation for all scrapers."""
    if posts is None or not posts:
        return "N/A"
    try:
        values = []
        for post in (posts[:10] if isinstance(posts, list) else []):
            if not post or not isinstance(post, dict):
                continue
            val = post.get(metric)
            if val is None:
                val = 0
            elif isinstance(val, (int, float)):
                val = float(val)
            elif isinstance(val, str):
                try:
                    s = val.replace(",", "").replace("+", "").strip()
                    val = float(s) if s and s.upper() not in ("N/A", "") else 0
                except (ValueError, TypeError):
                    val = 0
            else:
                val = 0
            values.append(val)
        if not values:
            return "N/A"
        return format_number(int(sum(values) / len(values)))
    except (TypeError, ValueError, ZeroDivisionError):
        return "N/A"


def calculate_rate(followers_str: str) -> str:
    """Estimate influencer rate from followers string. Single implementation for all scrapers."""
    try:
        followers = (followers_str or "").upper().replace(",", "").replace("+", "").strip()
        if not followers or followers == "N/A":
            return "N/A"
        if "K" in followers:
            followers_num = float(followers.replace("K", "")) * 1000
        elif "M" in followers:
            followers_num = float(followers.replace("M", "")) * 1_000_000
        else:
            followers_num = float(followers)
        if followers_num < 200_000:
            return "₹20,000"
        if followers_num < 500_000:
            return "₹25,000"
        if followers_num < 900_000:
            return "₹30,000"
        return "₹45,000"
    except Exception:
        return "N/A"


# -----------------------------------------------------------------------------
# Percentage parsing: single source for report/prompt metrics (N/A, nan-safe).
# -----------------------------------------------------------------------------

# Legacy alias for backward compatibility (parse_percentage is now imported)
_parse_percentage = parse_percentage


def _is_empty_value(val) -> bool:
    """Check if a value is empty, N/A, or zero - used for merge fallback logic."""
    if val is None:
        return True
    if isinstance(val, str):
        return val.strip() in ('', 'N/A', 'n/a', 'null', 'None', '0')
    if isinstance(val, (int, float)):
        return val == 0
    return False


# ============================================================================
# SORT BY RELEVANCE
# ============================================================================

def sort_results_by_relevance(
    results: List[Dict],
    parsed_query: Dict,
    metrics: Optional[Any] = None
) -> List[Dict]:
    """Accept all results, compute ranking scores, sort by relevance."""
    logger.info("\n" + "="*70)
    logger.info("Sort by relevance")
    logger.info("="*70)

    if metrics:
        sort_start = time.time()

    min_followers = parsed_query.get('min_followers')
    max_followers = parsed_query.get('max_followers')
    target_location = parsed_query.get('location', '').lower().strip()
    target_niche = parsed_query.get('niche', '').lower().strip()

    logger.info(f"Ranking: niche={target_niche or 'Any'}, location={target_location or 'Any'}")

    sorted_list = []
    for idx, result in enumerate(results, 1):
        name = result.get('NAME') or result.get('name') or result.get('username', f'Profile_{idx}')
        followers_int = parse_followers_to_int(result.get('followers', '0'))

        # Niche confidence (for ranking only)
        if target_niche and target_niche not in ['general', 'any', '']:
            result['_niche_confidence'] = _calculate_niche_confidence(result, target_niche)
        else:
            result['_niche_confidence'] = 0.5

        # Follower closeness (for ranking only)
        if followers_int > 0 and (min_followers or max_followers):
            if min_followers and max_followers and max_followers > min_followers:
                range_size = max_followers - min_followers
                position_in_range = (followers_int - min_followers) / range_size
                position_in_range = max(0.0, min(1.0, position_in_range))
                closeness_score = position_in_range ** 0.5
                if position_in_range >= 0.8:
                    closeness_score *= 1.2
                result['_follower_closeness'] = closeness_score
            elif max_followers and max_followers > 0:
                percentage_of_max = min(1.0, followers_int / max_followers)
                closeness_score = percentage_of_max ** 0.5
                if percentage_of_max >= 0.8:
                    closeness_score *= 1.2
                result['_follower_closeness'] = closeness_score
            else:
                result['_follower_closeness'] = 0.5
        else:
            result['_follower_closeness'] = 0.5

        result['_quality_score'] = _calculate_quality_score(result)

        # Location match (for ranking only)
        if target_location and target_location not in ['india', 'general', 'any', '']:
            result_location = str(result.get('Location', '')).lower().strip()
            location_hint = str(result.get('location_hint', '')).lower().strip()
            if location_hint == target_location or _location_match(target_location, result_location):
                result['_location_match'] = 1.0
            else:
                result['_location_match'] = 0.5
        else:
            result['_location_match'] = 0.5

        sorted_list.append(result)
        logger.debug(f"[{idx}] Include: {name} - {followers_int:,} followers")

    if metrics:
        if len(results) > 0:
            metrics.total_influencers_sorted = len(sorted_list)
            if hasattr(metrics, 'sort_time_seconds'):
                metrics.sort_time_seconds = time.time() - sort_start

    logger.info(f"Including all {len(sorted_list)} results")

    sorted_list.sort(key=lambda x: _calculate_relevance_score(x, parsed_query), reverse=True)

    logger.info(f"Sorted {len(sorted_list)} results by relevance")
    logger.info("="*70 + "\n")

    return sorted_list


def _calculate_niche_confidence(result: Dict, target_niche: str) -> float:
    """
    Calculate niche match confidence using multiple signals.
    Returns 0.0-1.0 confidence score.
    """
    target_niche = target_niche.lower().strip()
    confidence = 0.0
    signals = []

    result_niche = str(result.get('NICHE', '')).lower()
    result_bio = str(result.get('biography', '')).lower()
    result_category = str(result.get('category_name', '')).lower()
    result_business_category = str(result.get('business_category_name', '')).lower()
    niche_hint = str(result.get('niche_hint', '')).lower()
    result_name = str(result.get('NAME', '')).lower()

    if target_niche == result_niche:
        confidence += 0.5
        signals.append('exact_niche')
    elif target_niche in result_niche or result_niche in target_niche:
        confidence += 0.35
        signals.append('partial_niche')

    if niche_hint and (niche_hint == target_niche or target_niche in niche_hint):
        confidence += 0.35
        signals.append('hint_match')

    searchable_categories = f"{result_category} {result_business_category}"
    if target_niche in searchable_categories:
        confidence += 0.2
        signals.append('category_match')

    niche_keywords = _get_niche_keywords(target_niche)
    if any(kw in result_name for kw in niche_keywords[:5]):
        confidence += 0.15
        signals.append('name_match')

    searchable_text = f"{result_niche} {result_bio} {searchable_categories} {result_name}"
    keyword_matches = sum(1 for kw in niche_keywords if kw in searchable_text)
    if keyword_matches > 0:
        keyword_score = min(0.3, keyword_matches * 0.08)
        confidence += keyword_score
        signals.append(f'keywords({keyword_matches})')

    confidence = min(1.0, confidence)

    if confidence >= 0.3:
        logger.debug(f"   ✓ Niche confidence for '{result.get('NAME', 'Unknown')}': {confidence:.2f} ({', '.join(signals)})")

    return confidence


def _get_niche_keywords(niche: str) -> List[str]:
    """Get expanded keyword list for a niche - comprehensive coverage"""
    niche_keywords = {
        'finance': [
            'finance', 'financial', 'money', 'investment', 'investing',
            'trading', 'trader', 'budget', 'wealth', 'stock', 'stocks',
            'crypto', 'cryptocurrency', 'banking', 'bank', 'insurance',
            'tax', 'taxation', 'accounting', 'accountant', 'economy',
            'economic', 'fintech', 'personal finance', 'mutual fund',
            'investment advisor', 'financial advisor', 'portfolio',
            'saving', 'savings', 'loan', 'credit', 'equity', 'nifty',
            'sensex', 'sharemarket', 'share market', 'moneytips'
        ],
        'fitness': [
            'fitness', 'fit', 'gym', 'workout', 'health', 'healthy',
            'bodybuilding', 'bodybuilder', 'yoga', 'yogi', 'exercise',
            'training', 'trainer', 'athlete', 'athletic', 'nutrition',
            'nutritionist', 'wellness', 'sports', 'sport', 'crossfit',
            'weightlifting', 'cardio', 'marathon', 'running', 'cycling',
            'pilates', 'zumba', 'dance fitness', 'physical fitness',
            'muscle', 'strength', 'conditioning', 'hiit', 'calisthenics',
            'coach', 'instructor', 'fitnessmotivation', 'fitfam'
        ],
        'beauty': [
            'beauty', 'makeup', 'mua', 'skincare', 'skin care', 'cosmetic',
            'cosmetics', 'hair', 'hairstyle', 'salon', 'spa', 'grooming',
            'nails', 'manicure', 'pedicure', 'fragrance', 'perfume',
            'aesthetic', 'glam', 'glamour', 'beautician', 'dermatology',
            'facial', 'lipstick', 'foundation', 'eyeshadow', 'mascara',
            'beautyblogger', 'makeuptutorial', 'skincareroutine'
        ],
        'fashion': [
            'fashion', 'style', 'styling', 'stylist', 'outfit', 'clothing',
            'apparel', 'wardrobe', 'trend', 'trendy', 'designer',
            'boutique', 'accessories', 'accessory', 'model', 'modeling',
            'fashionista', 'ootd', 'streetwear', 'luxury fashion',
            'sustainable fashion', 'vintage', 'thrift', 'haute couture',
            'dress', 'jeans', 'shoes', 'bags', 'jewelry', 'fashionblogger'
        ],
        'food': [
            'food', 'foodie', 'recipe', 'recipes', 'cooking', 'cook',
            'chef', 'culinary', 'cuisine', 'restaurant', 'cafe',
            'baking', 'baker', 'pastry', 'meal', 'dining', 'gourmet',
            'street food', 'homemade', 'vegan', 'vegetarian', 'dessert',
            'sweets', 'breakfast', 'brunch', 'dinner', 'food blogger',
            'kitchen', 'cooking tips', 'meal prep', 'healthy eating',
            'foodporn', 'foodphotography', 'instafood', 'foodlover'
        ],
        'tech': [
            'tech', 'technology', 'gadget', 'gadgets', 'coding', 'code',
            'programming', 'programmer', 'software', 'developer',
            'app', 'application', 'digital', 'computer', 'ai',
            'artificial intelligence', 'ml', 'machine learning',
            'data science', 'cybersecurity', 'cloud', 'startup',
            'innovation', 'techie', 'geek', 'hardware', 'smartphone',
            'laptop', 'review', 'unboxing', 'tutorial', 'techtips'
        ],
        'travel': [
            'travel', 'traveler', 'traveller', 'trip', 'vacation',
            'tourism', 'tourist', 'wanderlust', 'explore', 'explorer',
            'adventure', 'adventurer', 'destination', 'backpack',
            'backpacker', 'nomad', 'journey', 'voyage', 'expedition',
            'trekking', 'hiking', 'globe', 'world traveler',
            'itinerary', 'hotel', 'flight', 'beach', 'mountain',
            'travelblogger', 'travelgram', 'instatravel', 'travelphotography'
        ],
        'gaming': [
            'gaming', 'gamer', 'game', 'games', 'esports', 'e-sports',
            'streamer', 'streaming', 'gameplay', 'console', 'pc gaming',
            'mobile gaming', 'playstation', 'xbox', 'nintendo',
            'twitch', 'youtube gaming', 'pro gamer', 'competitive gaming',
            'fps', 'moba', 'rpg', 'mmorpg', 'battle royale', 'bgmi', 'pubg'
        ],
        'lifestyle': [
            'lifestyle', 'life', 'daily', 'vlog', 'vlogger', 'blogger',
            'blog', 'routine', 'personal', 'day in life', 'wellness',
            'self care', 'productivity', 'minimalist', 'home decor',
            'organization', 'habits', 'morning routine', 'lifestyleblogger'
        ],
        'parenting': [
            'parenting', 'parent', 'parents', 'mom', 'mother', 'dad',
            'father', 'baby', 'babies', 'kids', 'children', 'family',
            'child', 'toddler', 'pregnancy', 'motherhood', 'fatherhood',
            'newborn', 'infant', 'childcare', 'momlife', 'dadlife'
        ],
        'education': [
            'education', 'learning', 'teaching', 'teacher', 'tutor',
            'course', 'courses', 'student', 'study', 'exam', 'school',
            'college', 'university', 'knowledge', 'skill', 'training',
            'edtech', 'online learning', 'tutorial', 'educate'
        ],
        'entertainment': [
            'entertainment', 'comedy', 'humor', 'funny', 'meme', 'memes',
            'viral', 'trending', 'content', 'creator', 'reels', 'shorts',
            'dance', 'dancing', 'performance', 'acting', 'actor', 'actress'
        ]
    }

    if niche in niche_keywords:
        return niche_keywords[niche]

    return [niche, f"{niche}er", f"{niche}ist", f"{niche}s", f"{niche} creator", f"{niche} blogger"]


def _calculate_quality_score(result: Dict) -> float:
    """
    Calculate overall quality score (0.0-1.0) based on:
    - Follower authenticity
    - Engagement rate
    - Account verification/professionalism
    - Profile completeness
    - Data availability
    """
    score = 0.0
    components = []

    real_pct = parse_percentage(result.get('real_followers_percentage', '0'))
    if real_pct > 0:
        score += (real_pct / 100) * 0.35
        components.append(f"auth:{real_pct:.0f}%")
    else:
        score += 0.15
        components.append("auth:default")

    engagement_str = str(result.get('engagement_rate', '0%')).replace('%', '').strip()
    try:
        engagement_rate = float(engagement_str) if engagement_str not in ('N/A', '', '0') else 0.0
        if engagement_rate > 0:
            normalized_engagement = min(1.0, engagement_rate / 10.0)
            score += normalized_engagement * 0.30
            components.append(f"eng:{engagement_rate:.1f}%")
        else:
            score += 0.10
            components.append("eng:default")
    except (ValueError, AttributeError):
        score += 0.10
        components.append("eng:default")

    verification_score = 0.0
    if result.get('is_verified'):
        verification_score += 0.5
        components.append("verified")
    if result.get('is_business_account') or result.get('is_professional_account'):
        verification_score += 0.5
        components.append("business")
    score += verification_score * 0.20

    completeness = 0.0
    if result.get('biography') and str(result.get('biography')) not in ('N/A', '', 'None'):
        completeness += 0.4
    if result.get('external_url') and str(result.get('external_url')) not in ('N/A', '', 'None'):
        completeness += 0.3
    if result.get('category_name') and str(result.get('category_name')) not in ('N/A', '', 'None'):
        completeness += 0.3
    score += completeness * 0.15

    final_score = min(1.0, score)

    if final_score >= 0.3:
        logger.debug(f"   Quality score: {final_score:.2f} ({', '.join(components)})")

    return final_score


def _location_match(target: str, result: str) -> bool:
    """Enhanced location matching - low level string op, fast enough without remote cache."""
    target = target.lower().strip()
    result = result.lower().strip()

    if target == result:
        return True

    if target in result or result in target:
        return True

    return False


def _calculate_relevance_score(result: Dict, parsed_query: Dict) -> float:
    """
    Calculate total relevance score for sorting.
    Higher score = better match = ranks higher
    """
    score = 0.0
    target_niche = parsed_query.get('niche', '').lower()
    min_followers = parsed_query.get('min_followers')
    max_followers = parsed_query.get('max_followers')

    niche_confidence = result.get('_niche_confidence', _calculate_niche_confidence(result, target_niche) if target_niche else 0.5)
    score += niche_confidence * 400

    quality_score = result.get('_quality_score', _calculate_quality_score(result))
    score += quality_score * 300

    followers_int = parse_followers_to_int(result.get('followers', '0'))

    # Use pre-calculated _follower_closeness score if available (from sort_results_by_relevance)
    # This score prioritizes influencers VERY CLOSE to max_followers using position_in_range^3
    follower_closeness = result.get('_follower_closeness')
    if follower_closeness is not None:
        # Use the pre-calculated closeness score (already optimized for max priority with exponential decay)
        # Multiply by very high weight to ensure it heavily influences ranking
        score += follower_closeness * 1500
    elif min_followers and max_followers and followers_int > 0:
        # Fallback: Calculate if not pre-calculated (shouldn't happen normally)
        range_size = max_followers - min_followers
        if range_size > 0:
            # Calculate position in range (0 = at min, 1 = at max)
            position_in_range = (followers_int - min_followers) / range_size
            position_in_range = max(0.0, min(1.0, position_in_range))
            # FIX: square-root bias, top 20% dominance
            closeness_score = position_in_range ** 0.5
            if position_in_range >= 0.8:
                closeness_score *= 1.2
            score += closeness_score * 1500
        else:
            # If min == max, only exact match gets score
            if followers_int == max_followers:
                score += 800
            else:
                score -= 500  # Heavy penalty for not matching exact count
    elif max_followers and followers_int > 0:
        # Only max specified - use percentage of max, square-root bias, top 20% dominance
        percentage_of_max = min(1.0, followers_int / max_followers)
        closeness_score = percentage_of_max ** 0.5
        if percentage_of_max >= 0.8:
            closeness_score *= 1.2
        score += closeness_score * 1500
    elif followers_int > 0:
        # No follower criteria but has followers - small bonus
        score += 150

    engagement_str = str(result.get('engagement_rate', '0%')).replace('%', '').strip()
    try:
        engagement_rate = float(engagement_str) if engagement_str not in ('N/A', '', '0') else 0.0
        score += min(100, engagement_rate * 15)
    except (ValueError, AttributeError):
        pass

    if result.get('is_verified'):
        score += 30
    if result.get('is_business_account') or result.get('is_professional_account'):
        score += 20

    real_pct = parse_percentage(result.get('real_followers_percentage', '0'))
    if real_pct > 0:
        score += real_pct

    location_match_score = result.get('_location_match', 0.5)
    score += location_match_score * 50

    return score


# ============================================================================
# ENHANCED DEDUPLICATION
# ============================================================================

def remove_duplicates(results: List[Dict]) -> List[Dict]:
    """Advanced duplicate removal with deterministic ordering"""
    logger.debug(f"Duplicate detection: {len(results)} results")

    seen_usernames = set()
    seen_profile_links = set()
    seen_normalized_names = set()
    unique_results = []

    def normalize_username(username: str) -> str:
        if not username:
            return ""
        return username.lower().strip().replace('@', '').replace('_', '').replace('.', '')

    def normalize_name(name: str) -> str:
        if not name:
            return ""
        normalized = name.lower().strip()
        normalized = normalized.replace('_', '').replace('.', '').replace('-', '')
        normalized = ''.join(normalized.split())
        return normalized

    def normalize_profile_link(link: str) -> str:
        # Use the centralized normalizer
        return normalize_profile_url(link) or link.lower().strip()

    # DETERMINISTIC SORTING: Prioritize better quality data
    # 1. Has location data (not N/A)
    # 2. Has engagement rate (not N/A)
    # 3. Higher follower count
    # 4. Username alphabetically (for consistency)
    def sort_key(r):
        has_location = 0 if r.get('Location') in [None, 'N/A', '', 'unknown'] else 1
        has_engagement = 0 if r.get('engagement_rate') in [None, 'N/A', '', '0%'] else 1
        has_real_followers = 0 if r.get('real_followers_percentage') in [None, 'N/A', ''] else 1
        followers_int = parse_followers_to_int(r.get('followers', '0'))
        username = (r.get('Id') or r.get('username', '')).lower()

        # Sort by: more complete data first, then higher followers, then alphabetically
        return (-has_location, -has_engagement, -has_real_followers, -followers_int, username)

    # Sort BEFORE deduplication so best version wins
    results_sorted = sorted(results, key=sort_key)
    logger.debug(f"Sorted {len(results_sorted)} results by data quality for deterministic deduplication")

    for result in results_sorted:
        username = result.get('Id') or result.get('username', '')
        name = result.get('NAME') or result.get('name', '')
        profile_link = result.get('PROFILE_LINK') or result.get('profile_link', '')

        norm_username = normalize_username(username)
        norm_name = normalize_name(name)
        norm_link = normalize_profile_link(profile_link)

        if not norm_username and not norm_name and not norm_link:
            continue

        is_duplicate = False

        if norm_username and norm_username in seen_usernames:
            is_duplicate = True
        if norm_link and norm_link in seen_profile_links:
            is_duplicate = True
        if norm_username and norm_name and norm_username == norm_name:
            if norm_username in seen_usernames or norm_name in seen_normalized_names:
                is_duplicate = True
        # Name already seen with similar follower count (within 10%) → likely same person
        if norm_name and norm_name in seen_normalized_names and not is_duplicate:
            current_followers = parse_followers_to_int(result.get("followers", "0"))
            for existing in unique_results:
                existing_name = normalize_name(existing.get("NAME") or existing.get("name", ""))
                if existing_name != norm_name:
                    continue
                existing_followers = parse_followers_to_int(existing.get("followers", "0"))
                if existing_followers > 0:
                    diff_pct = abs(existing_followers - current_followers) / existing_followers
                    if diff_pct < 0.1:
                        is_duplicate = True
                        break

        if is_duplicate:
            logger.debug(f"   ✗ DUPLICATE: {name or username}")
            continue

        if norm_username:
            seen_usernames.add(norm_username)
        if norm_name:
            seen_normalized_names.add(norm_name)
        if norm_link:
            seen_profile_links.add(norm_link)
        unique_results.append(result)

    duplicates_removed = len(results) - len(unique_results)
    if duplicates_removed > 0:
        logger.debug(f"Removed {duplicates_removed} duplicates")
    return unique_results


def location_match(location1: str, location2: str) -> bool:
    """Check if two locations match (case-insensitive, partial match)."""
    if not location1 or not location2:
        return False
    loc1 = str(location1).lower().strip()
    loc2 = str(location2).lower().strip()
    return loc1 in loc2 or loc2 in loc1 or loc1 == loc2

def extract_usernames_from_urls(url_list: List[str]) -> List[str]:
    """
    Extract Instagram usernames from a list of URLs.
    Handles various URL formats: full URLs, partial URLs, or just usernames.
    """
    import re
    usernames = []
    for url in url_list:
        if not url:
            continue
        
        url_str = str(url).strip().rstrip('/')
        
        # Extract username from Instagram URL
        match = re.search(r'instagram\.com/([^/?]+)', url_str, re.IGNORECASE)
        if match:
            username = match.group(1).lstrip('@').strip()
            if username:
                usernames.append(username)
        elif not url_str.startswith('http'):
            # If it's just a username (no URL), use it directly
            username = url_str.lstrip('@').strip()
            if username:
                usernames.append(username)
    
    return usernames


# ============================================================================
# DATA MERGER
# ============================================================================

def merge_results(scraper_a_results: List[Dict], scraper_b_results: List[Dict], scraper_c_results: List[Dict] = None) -> List[Dict]:
    merged = {}

    # Process Scraper B (BrightData has detailed profile data)
    for result in scraper_b_results:
        username = (result.get('Id') or result.get('NAME') or '').lower()
        if not username:
            continue

        if username not in merged:
            result_copy = result.copy()
            if 'niche_hint' not in result_copy:
                result_copy['niche_hint'] = result.get('NICHE', '')
            if 'location_hint' not in result_copy:
                result_copy['location_hint'] = result.get('Location', '')
            merged[username] = result_copy

            # DEBUG: Log what BrightData data we're storing
            logger.debug(f"   🔍 Stored BrightData for @{username}:")
            logger.debug(f"      → biography: {result_copy.get('biography', 'N/A')[:50]}...")
            logger.debug(f"      → posts: {len(result_copy.get('posts', []))} items")
            logger.debug(f"      → category_name: {result_copy.get('category_name', 'N/A')}")

    # Add unique results from Scraper A (Spreadd has engagement metrics)
    for result in scraper_a_results:
        username = (result.get('Id') or result.get('NAME') or '').lower()
        if not username:
            continue

        if username not in merged:
            result_copy = result.copy()
            if 'niche_hint' not in result_copy:
                result_copy['niche_hint'] = result.get('NICHE', '')
            if 'location_hint' not in result_copy:
                result_copy['location_hint'] = result.get('Location', '')
            merged[username] = result_copy
        else:
            existing = merged[username]
            if 'niche_hint' not in existing or not existing['niche_hint']:
                existing['niche_hint'] = result.get('niche_hint', result.get('NICHE', ''))
            if 'location_hint' not in existing or not existing['location_hint']:
                existing['location_hint'] = result.get('location_hint', result.get('Location', ''))
            
            # CRITICAL FIX: Merge Spreadd data intelligently - prefer Spreadd if BrightData is invalid/empty
            # Check followers - use Spreadd if BrightData is 0, "0", "N/A", or empty
            existing_followers = existing.get('followers', '0')
            spreadd_followers = result.get('followers', '0')
            if (existing_followers in ('0', 0, 'N/A', '', None) or 
                (isinstance(existing_followers, str) and existing_followers.strip() in ('0', 'N/A', ''))) and \
               spreadd_followers not in ('0', 0, 'N/A', '', None) and \
               (isinstance(spreadd_followers, str) and spreadd_followers.strip() not in ('0', 'N/A', '')):
                existing['followers'] = spreadd_followers
                logger.debug(f"   ✅ Merged Spreadd followers for @{username}: {spreadd_followers}")
            
            # Merge engagement_rate - ALWAYS prefer Spreadd (calculated with authenticity analysis)
            # BrightData's avg_engagement is often much lower than Spreadd's calculated rate
            spreadd_engagement = result.get('engagement_rate', 'N/A')
            # Use Spreadd's engagement rate if it's valid (non-empty, non-zero)
            if spreadd_engagement not in ('N/A', '0', 0, '0%', '0.00%', '', None) and \
               (isinstance(spreadd_engagement, str) and spreadd_engagement.strip() not in ('N/A', '0', '0%', '0.00%', '')):
                existing['engagement_rate'] = spreadd_engagement
                logger.debug(f"   ✅ Using Spreadd engagement_rate for @{username}: {spreadd_engagement}")
            
            # Merge authenticity metrics - prefer Spreadd if BrightData is missing
            if existing.get('suspicious_followers_percentage') in ('N/A', None, '') and \
               result.get('suspicious_followers_percentage') not in ('N/A', None, ''):
                existing['suspicious_followers_percentage'] = result['suspicious_followers_percentage']
                existing['real_followers_percentage'] = result.get('real_followers_percentage', 'N/A')
                logger.debug(f"   ✅ Merged Spreadd authenticity metrics for @{username}")
            
            # Merge other Spreadd metrics if BrightData is missing
            if existing.get('average_likes') in ('N/A', 0, None, '') and result.get('average_likes') not in ('N/A', 0, None, ''):
                existing['average_likes'] = result.get('average_likes')
            if existing.get('average_comments') in ('N/A', 0, None, '') and result.get('average_comments') not in ('N/A', 0, None, ''):
                existing['average_comments'] = result.get('average_comments')
            # Merge following - prefer valid data from either source
            existing_following = existing.get('following')
            spreadd_following = result.get('following')
            if _is_empty_value(existing_following) and not _is_empty_value(spreadd_following):
                existing['following'] = spreadd_following
            # Merge posts_count - prefer valid data from either source
            existing_posts = existing.get('posts_count')
            spreadd_posts = result.get('posts_count')
            if _is_empty_value(existing_posts) and not _is_empty_value(spreadd_posts):
                existing['posts_count'] = spreadd_posts

            # Merge profile imagery - prefer Spreadd/SerpAPI image if existing image is missing
            existing_pic = existing.get('profile_pic_url') or existing.get('image')
            spreadd_pic = result.get('profile_pic_url') or result.get('image')
            if not existing_pic and spreadd_pic and spreadd_pic not in ('N/A', '', None):
                existing['profile_pic_url'] = spreadd_pic
                existing['profile_image'] = spreadd_pic
                existing['image'] = spreadd_pic

            # Merge biography if BrightData didn't provide one
            existing_bio = existing.get('biography')
            spreadd_bio = result.get('biography')
            if (not existing_bio or existing_bio in ('N/A', '', None)) and spreadd_bio not in ('N/A', '', None):
                existing['biography'] = spreadd_bio

            # Merge external_url if missing
            existing_url = existing.get('external_url')
            spreadd_url = result.get('external_url')
            if (not existing_url or existing_url in ('N/A', '', None)) and spreadd_url not in ('N/A', '', None):
                existing['external_url'] = spreadd_url

    if scraper_c_results:
        for result in scraper_c_results:
            username = (result.get('Id') or result.get('NAME') or result.get('username') or '').lower().strip()
            if not username:
                continue
            if username not in merged:
                result_copy = result.copy()
                merged[username] = result_copy

    required_fields = [
        "NAME", "Id", "PROFILE_LINK", "followers", "following", "posts_count",
        "average_likes", "average_comments", "suspicious_followers_percentage",
        "real_followers_percentage", "NICHE", "is_business_account",
        "is_professional_account", "is_verified", "engagement_rate",
        "external_url", "biography", "business_category_name", "category_name",
        "highlights_count", "is_joined_recently", "Location", "RATE",
        "niche_hint", "location_hint"
    ]

    final_results = []
    for username, data in merged.items():
        for field in required_fields:
            if field not in data:
                if field in ["is_verified", "is_business_account", "is_professional_account", "is_joined_recently"]:
                    data[field] = False
                elif field in ["highlights_count"]:
                    data[field] = 0
                else:
                    data[field] = "N/A"

        data['Id'] = data.get('Id', data.get('NAME', username))
        data['checked_at'] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        # Ensure posts is always a list for display workflow (post images + per-post info)
        if not isinstance(data.get('posts'), list):
            data['posts'] = []

        final_results.append(data)

    logger.info(f"Merged {len(final_results)} unique influencers")
    logger.info(f"Scrapers: A={len(scraper_a_results)}, B={len(scraper_b_results)}")
    logger.info("="*70)

    return final_results
