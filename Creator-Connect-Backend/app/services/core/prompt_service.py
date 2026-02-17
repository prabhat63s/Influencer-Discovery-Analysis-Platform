from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import random
import re
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from dotenv import load_dotenv

from app.services.llm.agent_service import analyze_prompt
from app.services.core.slot_filler_service import InfluencerSlotFiller
from app.services.core.search_filters import parse_percentage
from app.utils.metric_constants import normalize_metric_value
from app.services.data import temp_store

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env")

logger = logging.getLogger(__name__)

_slot_filler_instances: Dict[str, InfluencerSlotFiller] = {}
_dynamic_search_results: Dict[str, List[Dict[str, Any]]] = {}



def get_slot_filler(conversation_id: str) -> InfluencerSlotFiller:
    # Return (and cache) a slot filler for the conversation.
    if conversation_id not in _slot_filler_instances:
        _slot_filler_instances[conversation_id] = InfluencerSlotFiller()
        logger.info("Created new slot filler for conversation %s", conversation_id)
    return _slot_filler_instances[conversation_id]


def get_dynamic_results_store() -> Dict[str, List[Dict[str, Any]]]:
    # Expose the in-memory dynamic search results store.
    return _dynamic_search_results


def load_dynamic_results(conversation_id: str) -> Optional[List[Dict[str, Any]]]:
    # Load dynamic results from storage (in-memory cache or temp_store).
    #
    # Args:
    #     conversation_id: Conversation/session ID
    #
    # Returns:
    #     List of results if found, None otherwise

    # Try in-memory cache first
    if conversation_id in _dynamic_search_results:
        logger.debug(f"✅ Loaded from in-memory cache: {conversation_id}")
        return _dynamic_search_results[conversation_id]

    # Fallback to temp_store
    session_data = temp_store.load_session(conversation_id)
    if session_data and "results" in session_data:
        results = session_data["results"]
        # Populate in-memory cache for future requests
        _dynamic_search_results[conversation_id] = results
        logger.debug(f"✅ Loaded from temp storage: {conversation_id}")
        return results

    logger.debug(f"❌ No results found for: {conversation_id}")
    return None


def record_dynamic_results(conversation_id: str, results: List[Dict[str, Any]]) -> None:
    # Record results in in-memory cache (for immediate access).
    # This is called BEFORE persist_dynamic_results.
    # Save the latest dynamic search results for quick access.
    # Uses both in-memory cache and persistent JSON storage.
    # 
    # CRITICAL FIX: Clears any existing cache/session data first to prevent stale peers.

    # CRITICAL: Clear any existing stale data for this conversation FIRST
    # This ensures we don't get stale peer comparison data from previous searches
    if conversation_id in _dynamic_search_results:
        old_count = len(_dynamic_search_results[conversation_id])
        del _dynamic_search_results[conversation_id]
        logger.debug(f"🗑️ Cleared existing in-memory cache for {conversation_id} ({old_count} old results)")
    
    # Also clear temp_store session to prevent stale disk data
    try:
        temp_store.delete_session(conversation_id, delete_reports=False)
        logger.debug(f"🗑️ Cleared existing temp_store session for {conversation_id}")
    except Exception as e:
        logger.debug(f"No temp_store session to clear for {conversation_id}: {e}")
    
    # Keep in-memory for quick access
    _dynamic_search_results[conversation_id] = results
    
    # Log what we're recording (for debugging)
    anchor_count = sum(1 for r in results if r.get("industry_anchor") is True)
    peer_count = sum(1 for r in results if r.get("industry_standard") is True)
    logger.info(f"💾 Recording {len(results)} results in cache: {anchor_count} anchor(s), {peer_count} peer(s)")

    # Persist to temp storage (24h lifecycle)
    temp_store.persist_session(conversation_id, {"results": results})




def _get_dynamic_results_dir() -> Path:
    storage_path = _PROJECT_ROOT / "storage"
    path = storage_path / "dynamic_results"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _atomic_write(path: Path, content: str) -> None:
    """Atomically write `content` to `path`."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", delete=False, dir=str(path.parent), encoding="utf-8") as tf:
        tf.write(content)
        tmpname = tf.name
    Path(tmpname).replace(path)


def _compute_influencer_id(record: Dict[str, Any]) -> Optional[str]:
    if not record:
        return None
    if record.get("id"):
        return record["id"]

    profile_link = record.get("profile_link") or record.get("PROFILE_LINK")
    name = record.get("name") or record.get("NAME", "Unknown")
    niche = record.get("niche") or record.get("NICHE", "Unknown")
    location = record.get("location") or record.get("Location", "Unknown")

    if profile_link:
        return hashlib.md5(str(profile_link).encode()).hexdigest()[:12]

    unique_string = f"{name}_{location}_{niche}"
    return hashlib.md5(unique_string.encode()).hexdigest()[:12]


def _extract_location_from_bio(bio: str) -> Optional[str]:
    """
    Extract a city/location hint from biography text.
    Uses pin markers and an expanded city/state list.
    """
    if not bio:
        return None

    # Pin emoji patterns
    pin_before = re.search(r"([A-Za-z\s]+)\s*📍", bio)
    if pin_before:
        loc = pin_before.group(1).strip()
        if loc:
            return loc
    pin_after = re.search(r"📍\s*([A-Za-z\s,]+)", bio)
    if pin_after:
        loc = pin_after.group(1).strip()
        if loc:
            return loc

    cities = [
        "Nagpur", "Delhi", "New Delhi", "Mumbai", "Bombay", "Bangalore", "Bengaluru",
        "Pune", "Hyderabad", "Chennai", "Kolkata", "Ahmedabad", "Jaipur", "Lucknow",
        "Chandigarh", "Gurgaon", "Noida", "Goa", "Kochi", "Indore", "Bhopal",
        "Surat", "Vadodara", "Rajkot", "Patna", "Kanpur", "Maharashtra",
        "Karnataka", "Tamil Nadu", "Kerala", "Gujarat", "Uttar Pradesh"
    ]
    for city in cities:
        if re.search(rf"\b{re.escape(city)}\b", bio, re.IGNORECASE):
            return city
    return None

def persist_dynamic_results(conversation_id: str, results: List[Dict[str, Any]]) -> None:
    """
    Persist dynamic search results using temp_store (24h lifecycle).
    Also maintains a lightweight JSON index for influencer lookups (no SQLite).
    """
    if not results:
        return

    # Use temp_store for JSON persistence (replaces old CSV approach)
    # Log what we're persisting (for debugging)
    anchor_count = sum(1 for r in results if r.get("industry_anchor") is True)
    peer_count = sum(1 for r in results if r.get("industry_standard") is True)
    logger.info(f"💾 Persisting {len(results)} results to temp storage: {anchor_count} anchor(s), {peer_count} peer(s)")
    
    payload = {
        "conversation_id": conversation_id,
        "saved_at": datetime.utcnow().isoformat(),
        "results": results,
    }

    success = temp_store.persist_session(conversation_id, payload)
    if success:
        logger.info(f"✅ Saved dynamic results to temp storage: {conversation_id} ({anchor_count} anchor, {peer_count} peers)")
    else:
        logger.warning("⚠️ Failed to save dynamic results for %s", conversation_id)

    # Maintain a JSON index for influencer lookups (fully file-based for easy deployment)
    try:
        dynamic_dir = _get_dynamic_results_dir()
        index_path = dynamic_dir / "dynamic_index.json"

        # Load existing index if present
        existing_index: Dict[str, Any] = {}
        if index_path.exists():
            try:
                with index_path.open("r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        existing_index = data
            except Exception as exc:
                logger.warning("⚠️ Failed to read existing dynamic_index.json: %s", exc)

        # Update index with current batch
        for record in results:
            influencer_id = _compute_influencer_id(record)
            if not influencer_id:
                continue
            existing_index[influencer_id] = {
                "conversation_id": conversation_id,
                "saved_at": payload["saved_at"],
            }

        # Atomically write updated index back to disk
        _atomic_write(index_path, json.dumps(existing_index, ensure_ascii=False, indent=2))
        logger.debug("✅ Updated JSON dynamic index at %s", index_path)
    except Exception as exc:
        logger.warning("⚠️ Failed to update JSON dynamic index: %s", exc)


def _parse_number_string(value: str) -> int:
    if not value or pd.isna(value):
        return 0

    value_str = (
        str(value)
        .upper()
        .replace("₹", "")
        .replace("RS", "")
        .replace(",", "")
        .replace("+", "")
        .strip()
    )

    try:
        if "M" in value_str:
            return int(float(value_str.replace("M", "")) * 1_000_000)
        if "K" in value_str:
            return int(float(value_str.replace("K", "")) * 1_000)
        return int(float(value_str))
    except (ValueError, AttributeError):
        return 0


# -----------------------------------------------------------------------------
# Metric parsing: use canonical parse_percentage from search_filters (handles
# N/A, nan, None; single source of truth for percentage coercion).
# -----------------------------------------------------------------------------

def calculate_influencer_metrics(result: Dict[str, Any]) -> Dict[str, float]:
    """Calculate influencer analytics metrics from provided formulas."""
    metrics: Dict[str, float] = {}

    def safe_float(key, default=0.0):
        val = result.get(key, default)
        if val is None or val == "N/A" or pd.isna(val):
            return default
        if isinstance(val, str):
            val = val.replace("%", "").replace(",", "").replace("₹", "").strip()
            try:
                return float(val)
            except Exception:
                return default
        return float(val)

    def safe_int(key, default=0):
        val = result.get(key, default)
        # Handle None, N/A, or NaN values
        if val is None or val == "N/A" or pd.isna(val):
            return default
        # Handle string values
        if isinstance(val, str):
            val = val.replace("%", "").replace(",", "").replace("₹", "").strip()
            if not val or val.upper() == "N/A":
                return default
            try:
                return int(float(val))
            except (ValueError, TypeError):
                return default
        # Handle numeric types (int, float)
        try:
            if isinstance(val, (int, float)):
                return int(val)
            # For any other type (list, dict, etc.), return default
            return default
        except (TypeError, ValueError):
            return default

    followers = safe_int("followers", 0)
    following = safe_int("following", 0)
    posts_count = safe_int("posts_count", 0)
    average_likes = safe_int("average_likes", 0)
    average_comments = safe_int("average_comments", 0)
    # Get scraped engagement_rate - if provided, we'll trust it
    scraped_engagement_rate = safe_float("engagement_rate", 0.0)

    real_followers_pct = parse_percentage(result.get("real_followers_percentage", "0%"))
    suspicious_followers_pct = parse_percentage(result.get("suspicious_followers_percentage", "0%"))

    is_verified = result.get("is_verified", False)
    is_business_account = result.get("is_business_account", False)
    is_professional_account = result.get("is_professional_account", False)
    highlights_count = safe_int("highlights_count", 0)
    has_bio = bool(result.get("biography") and result.get("biography") != "N/A")
    has_external_url = bool(result.get("external_url") and result.get("external_url") != "N/A")
    has_category = bool(result.get("category_name") and result.get("category_name") != "N/A")
    has_highlights = highlights_count > 0

    # Ensure all values are not None before arithmetic operations - CRITICAL FIX
    safe_followers_val = followers if followers is not None else 0
    safe_following_val = following if following is not None else 0
    safe_posts_count_val = posts_count if posts_count is not None else 0
    safe_average_likes = average_likes if average_likes is not None else 0
    safe_average_comments = average_comments if average_comments is not None else 0
    
    safe_followers = max(safe_followers_val, 1)
    safe_following = max(safe_following_val, 1)
    safe_posts = max(safe_posts_count_val, 1)
    safe_likes = max(safe_average_likes, 1)
    
    total_engagement = safe_average_likes + safe_average_comments

    # CRITICAL FIX: Use scraped engagement_rate if available and valid
    # Only calculate from averages if scraped value is missing or invalid
    if scraped_engagement_rate > 0:
        # Scraped engagement_rate is already provided - use as-is (no normalization)
        metrics["engagement_rate"] = scraped_engagement_rate
        
        # Cap engagement rate at 100% (can't exceed follower count)
        if metrics["engagement_rate"] > 100.0:
            logger.warning(
                f"Engagement rate capped from {metrics['engagement_rate']:.2f}% to 100% "
                f"(followers: {safe_followers_val}, likes: {safe_average_likes}, comments: {safe_average_comments})"
            )
            metrics["engagement_rate"] = 100.0
    else:
        # No scraped engagement_rate - calculate from averages (keep as percentage)
        calculated_rate = (total_engagement / safe_followers) if safe_followers_val > 0 else 0.0
        # Cap engagement rate at 100% (can't exceed follower count)
        if calculated_rate > 100.0:
            logger.warning(
                f"Engagement rate capped from {calculated_rate:.2f}% to 100% "
                f"(followers: {safe_followers_val}, total_engagement: {total_engagement})"
            )
            metrics["engagement_rate"] = 100.0
        else:
            metrics["engagement_rate"] = calculated_rate

    metrics["like_rate"] = (safe_average_likes / safe_followers) if safe_followers_val > 0 else 0.0
    metrics["comment_rate"] = (safe_average_comments / safe_followers) if safe_followers_val > 0 else 0.0
    metrics["comment_to_like_ratio"] = (safe_average_comments / safe_likes) if safe_average_likes > 0 else 0.0
    metrics["total_engagement_per_post"] = float(total_engagement)
    # Use safe_posts_count_val which is already validated
    safe_posts_count_for_ops = safe_posts_count_val
    metrics["total_engagement_volume"] = float(total_engagement * safe_posts_count_for_ops)
    metrics["engagement_per_follower"] = (total_engagement * safe_posts_count_for_ops) / safe_followers if safe_followers_val > 0 else 0.0

    safe_highlights_count_val = highlights_count if highlights_count is not None else 0
    metrics["posts_per_highlight_ratio"] = safe_posts_count_for_ops / max(safe_highlights_count_val, 1) if safe_highlights_count_val > 0 else 0.0
    metrics["content_saturation_index"] = (safe_posts_count_for_ops / safe_followers) if safe_followers_val > 0 else 0.0
    metrics["followers_per_post"] = safe_followers_val / safe_posts if safe_posts_count_for_ops > 0 else 0.0
    metrics["average_post_engagement"] = (total_engagement * safe_posts_count_for_ops) / safe_posts if safe_posts_count_for_ops > 0 else 0.0

    # Use the calculated engagement_rate from metrics (ensures we use the correct value)
    calculated_engagement_rate = metrics["engagement_rate"]

    metrics["authenticity_score"] = (real_followers_pct * calculated_engagement_rate) / 100.0
    metrics["real_engagement_volume"] = safe_average_likes * (real_followers_pct / 100.0)
    metrics["quality_follower_count"] = safe_followers_val * (real_followers_pct / 100.0)
    metrics["bot_risk_score"] = (suspicious_followers_pct * 100) / max(calculated_engagement_rate, 0.01) if calculated_engagement_rate > 0 else 0.0

    metrics["follower_to_following_ratio"] = safe_followers_val / safe_following if safe_following_val > 0 else 0.0
    metrics["following_percentage"] = (safe_following_val / safe_followers) * 100 if safe_followers_val > 0 else 0.0
    metrics["network_authority_score"] = (
        int(is_verified) + int(is_business_account) + int(is_professional_account)
    ) / 3.0
    metrics["account_type_score"] = float(int(is_business_account) + int(is_professional_account))

    metrics["engagement_efficiency_ratio"] = (
        calculated_engagement_rate / max(suspicious_followers_pct, 0.01) if suspicious_followers_pct > 0 else 0.0
    )
    metrics["audience_activation_rate"] = (
        ((total_engagement * safe_posts_count_for_ops) / (safe_followers * safe_posts))
        if safe_followers_val > 0 and safe_posts_count_for_ops > 0
        else 0.0
    )
    metrics["estimated_highlights_engagement"] = float(safe_highlights_count_val * total_engagement)
    metrics["follower_engagement_density"] = safe_followers_val / safe_posts if safe_posts_count_for_ops > 0 else 0.0

    metrics["content_portfolio_value"] = float(safe_posts_count_for_ops * total_engagement)
    metrics["engagement_sustainability"] = (real_followers_pct * calculated_engagement_rate) / 100.0

    metrics["weighted_engagement_quality"] = (
        ((safe_average_comments * 10) + safe_average_likes) / safe_followers
    ) if safe_followers_val > 0 else 0.0
    metrics["true_reach_estimate"] = safe_followers_val * (real_followers_pct / 100.0) * (calculated_engagement_rate / 100.0)
    metrics["virality_potential_index"] = (
        total_engagement / (safe_following * (calculated_engagement_rate / 100.0))
        if safe_following_val > 0 and calculated_engagement_rate > 0
        else 0.0
    )
    metrics["engagement_depth_score"] = (safe_average_comments / safe_likes) if safe_average_likes > 0 else 0.0

    # Get rate from result data (support both 'rate' and 'RATE' keys)
    rate = safe_float("rate", 0.0) or safe_float("RATE", 0.0)
    safe_total_engagement = max(total_engagement, 0.01)

    # Only calculate cost metrics if rate is available
    if rate > 0:
        metrics["cost_per_engagement"] = rate / safe_total_engagement if total_engagement > 0 else 0.0
        metrics["cost_per_like"] = rate / safe_likes if safe_average_likes > 0 else 0.0
        metrics["cost_per_comment"] = rate / max(safe_average_comments, 0.01) if safe_average_comments > 0 else 0.0
        metrics["cost_per_1000_followers"] = (rate / safe_followers) * 1000 if safe_followers_val > 0 else 0.0
        metrics["cost_per_quality_follower"] = (
            rate / max(metrics["quality_follower_count"], 0.01)
            if metrics["quality_follower_count"] > 0
            else 0.0
        )

    # Ensure posts_count and highlights_count are not None before addition
    safe_posts_count = posts_count if posts_count is not None else 0
    safe_highlights_count = highlights_count if highlights_count is not None else 0
    metrics["instagram_activity_score"] = (safe_posts_count_for_ops + safe_highlights_count_val + (int(is_business_account) * 10)) / 3.0

    industry_avg_engagement = 0.0
    industry_avg_real_followers = 0.0
    metrics["engagement_vs_industry_benchmark"] = calculated_engagement_rate - industry_avg_engagement
    metrics["authenticity_vs_industry_benchmark"] = real_followers_pct - industry_avg_real_followers

    account_age_days = 365
    metrics["posts_frequency"] = posts_count / max(account_age_days, 1) if account_age_days > 0 else 0.0
    metrics["engagement_growth_rate"] = 0.0
    metrics["follower_growth_rate"] = 0.0
    metrics["content_efficiency_score"] = (
        ((total_engagement * safe_posts_count_for_ops) / safe_posts / safe_followers) * 10000
        if safe_followers_val > 0 and safe_posts_count_for_ops > 0
        else 0.0
    )
    metrics["audience_quality_index"] = (real_followers_pct * calculated_engagement_rate * metrics["follower_to_following_ratio"]) / 1000.0
    metrics["collaboration_readiness_score"] = (
        (int(is_professional_account) * 3) + (int(is_business_account) * 2) + (int(highlights_count > 5) * 1)
    ) / 6.0
    metrics["engagement_consistency"] = 0.0
    metrics["profile_completeness_score"] = (
        (int(has_bio) + int(has_external_url) + int(has_category) + int(has_highlights)) / 4.0
    ) * 100.0

    filtered_metrics: Dict[str, float] = {}
    for key, value in metrics.items():
        if value is None:
            continue
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                continue
            if abs(value) < 0.0001:
                continue
        if isinstance(value, str):
            v_upper = value.upper().strip()
            if v_upper in ["N/A", "NA", "NONE", ""]:
                continue
            try:
                v_float = float(v_upper)
                if abs(v_float) < 0.0001:
                    continue
                filtered_metrics[key] = round(v_float, 2)
            except (ValueError, TypeError):
                continue
        else:
            filtered_metrics[key] = round(float(value), 2)

    return filtered_metrics


def convert_dynamic_search_to_standard_format(dynamic_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    logger.debug("Converting %s dynamic results to standard format", len(dynamic_results))
    standard_results: List[Dict[str, Any]] = []

    for result in dynamic_results:
        profile_link = result.get("PROFILE_LINK") or result.get("profile_link", "")
        name = result.get("NAME") or result.get("name", "Unknown")

        if profile_link:
            influencer_id = hashlib.md5(str(profile_link).encode()).hexdigest()[:12]
        else:
            niche = result.get("NICHE", "Unknown")
            location = result.get("Location", "Unknown")
            unique_string = f"{name}_{location}_{niche}"
            influencer_id = hashlib.md5(unique_string.encode()).hexdigest()[:12]

        # Extract rate (support both RATE and rate keys)
        rate_value = result.get("RATE") or result.get("rate") or result.get("min_rate", "N/A")

        # Location handling: prefer explicit location; if it's default/unknown, try extracting from bio
        raw_location = result.get("Location", result.get("location", "Unknown"))
        bio_location = None
        if str(raw_location).strip().lower() in {"unknown", "n/a", "india", ""}:
            bio_location = _extract_location_from_bio(result.get("biography", ""))
        if bio_location:
            raw_location = bio_location

        standard_result = {
            "id": influencer_id,
            "name": name,
            "niche": result.get("NICHE", result.get("niche", "Unknown")),
            "location": raw_location,
            "followers": _parse_number_string(result.get("followers", "0")),
            "following": _parse_number_string(result.get("following", "0")),
            "posts_count": _parse_number_string(result.get("posts_count", "0")),
            "average_likes": _parse_number_string(result.get("average_likes", "0")),
            "average_views": _parse_number_string(result.get("avg_views", result.get("average_views", "0"))),
            "average_comments": _parse_number_string(result.get("average_comments", "0")),
            "engagement_rate": parse_percentage(result.get("engagement_rate", "0")),
            "match_score": 100.0,
            "rate": rate_value,  # Add rate to standard result
            "RATE": rate_value,  # Also keep RATE key for backward compatibility
        }

        if profile_link:
            standard_result["profile_link"] = profile_link

        # CRITICAL FIX: Preserve ALL fields from dynamic results
        # The old approach with a hardcoded list was dropping BrightData fields like:
        # - posts (array of post data)
        # - post analysis metrics (top_hashtags, content_themes, etc.)
        # - niche_hint, location_hint
        # - And many others
        #
        # NEW APPROACH: Copy all fields from result, then override with standard_result fields
        # This ensures nothing is lost from BrightData enrichment
        for key, value in result.items():
            # Skip keys that are already set in standard_result with processed values
            if key not in standard_result:
                standard_result[key] = value

        # Now apply our processed/calculated values on top
        # (This ensures followers/engagement_rate use parsed values, not raw strings)
        standard_result.update({
            "id": influencer_id,
            "name": name,
            "niche": result.get("NICHE", result.get("niche", "Unknown")),
            "location": raw_location,
            "followers": _parse_number_string(result.get("followers", "0")),
            "following": _parse_number_string(result.get("following", "0")),
            "posts_count": _parse_number_string(result.get("posts_count", "0")),
            "average_likes": _parse_number_string(result.get("average_likes", "0")),
            "average_views": _parse_number_string(result.get("avg_views", result.get("average_views", "0"))),
            "average_comments": _parse_number_string(result.get("average_comments", "0")),
            "engagement_rate": parse_percentage(result.get("engagement_rate", "0")),
            "match_score": 100.0,
            "rate": rate_value,
            "RATE": rate_value,
        })

        if profile_link:
            standard_result["profile_link"] = profile_link

        try:
            calculated_metrics = calculate_influencer_metrics(result)
            standard_result["metrics"] = calculated_metrics
            logger.debug("Calculated %s metrics for %s", len(calculated_metrics), name)
        except Exception as exc:
            logger.warning("Error calculating metrics for %s: %s", name, exc)
            standard_result["metrics"] = {}

        standard_results.append(standard_result)

    logger.debug("Converted %s results", len(standard_results))
    return standard_results


def clean_search_results(search_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    cleaned_search_results = []
    if not search_results:
        return cleaned_search_results

    try:
        import pandas as pd  # noqa: F401
    except ImportError:
        pd = None

    for result in search_results:
        cleaned_result: Dict[str, Any] = {}
        for key, value in result.items():
            is_nan = False
            if value is not None:
                if isinstance(value, float) and math.isnan(value):
                    is_nan = True
                elif pd and hasattr(pd, "isna") and pd.isna(value):
                    is_nan = True

            if is_nan:
                if key in ["followers", "average_likes", "average_views", "average_comments"]:
                    cleaned_result[key] = 0
                elif key in ["rate", "match_score", "engagement_rate", "similarity_score"]:
                    cleaned_result[key] = 0.0
                else:
                    cleaned_result[key] = None
            elif pd and hasattr(pd, "Series") and isinstance(value, pd.Series):
                cleaned_result[key] = value.tolist() if len(value) > 0 else None
            elif pd and hasattr(pd, "Timestamp") and isinstance(value, pd.Timestamp):
                cleaned_result[key] = value.isoformat()
            elif value is None:
                cleaned_result[key] = None
            else:
                try:
                    if hasattr(value, "item"):
                        cleaned_result[key] = value.item()
                    else:
                        cleaned_result[key] = value
                except (ValueError, AttributeError):
                    cleaned_result[key] = str(value)
        cleaned_search_results.append(cleaned_result)

    return cleaned_search_results


def compute_and_persist_metrics(result: Dict[str, Any], conversation_id: str) -> None:
    """Compute metrics for a single result and persist them back into temp_store."""
    try:
        metrics = calculate_influencer_metrics(result)
        influencer_id = _compute_influencer_id(result) or result.get("id")

        # Persist metrics to a JSON index (no SQLite dependency)
        try:
            dynamic_dir = _get_dynamic_results_dir()
            metrics_index_path = dynamic_dir / "influencer_metrics.json"

            metrics_index: Dict[str, Any] = {}
            if metrics_index_path.exists():
                try:
                    with metrics_index_path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                        if isinstance(data, dict):
                            metrics_index = data
                except Exception as exc:
                    logger.warning("Failed to read existing influencer_metrics.json: %s", exc)

            metrics_index[influencer_id] = {
                "conversation_id": conversation_id,
                "metrics": metrics,
                "updated_at": datetime.utcnow().isoformat(),
            }

            _atomic_write(
                metrics_index_path,
                json.dumps(metrics_index, ensure_ascii=False, indent=2),
            )
        except Exception as exc:
            logger.warning("Failed to persist metrics to JSON for %s: %s", influencer_id, exc)

        # Load from temp_store
        session_data = temp_store.load_session(conversation_id)
        if not session_data or "results" not in session_data:
            logger.warning(f"No session data found for {conversation_id}")
            return

        # Update metrics in session data
        updated = False
        for item in session_data.get("results", []):
            item_id = item.get("id") or _compute_influencer_id(item)
            if (influencer_id and item_id == influencer_id) or (
                not influencer_id and item.get("profile_link") == result.get("profile_link")
            ):
                item.setdefault("metrics", {})
                item["metrics"].update(metrics)
                updated = True
                break

        if not updated:
            new_item = result.copy()
            new_item.setdefault("metrics", {})
            new_item["metrics"].update(metrics)
            if not new_item.get("id"):
                new_item["id"] = influencer_id or _compute_influencer_id(new_item)
            session_data.setdefault("results", []).append(new_item)

        # Save back to temp_store
        temp_store.persist_session(conversation_id, session_data)
        logger.debug("✅ Persisted metrics for influencer %s in conversation %s", influencer_id, conversation_id)

    except Exception as exc:
        logger.exception("Failed to compute/persist metrics for conversation=%s: %s", conversation_id, exc)


def check_prompt_requirements(prompt: str) -> Tuple[bool, List[str], Dict[str, Any]]:
    """Check if prompt has required fields: Category, Location, AND Followers range."""
    validation = analyze_prompt(prompt)

    def safe_str_convert(value):
        if value is None:
            return None
        if isinstance(value, float) and math.isnan(value):
            return None
        try:
            if hasattr(pd, "isna") and pd.isna(value):
                return None
        except ImportError:
            pass
        try:
            return str(value) if value else None
        except Exception:
            return None

    extracted = {
        "category": safe_str_convert(validation.get("extracted_category")),
        "location": safe_str_convert(validation.get("extracted_location")),
        "followers": safe_str_convert(validation.get("extracted_followers")),
        "fee": safe_str_convert(validation.get("extracted_fee")),
        "fee_range": safe_str_convert(validation.get("extracted_fee_range")),
    }

    missing_fields = []
    if not extracted["category"]:
        missing_fields.append("Category")
    if not extracted["location"]:
        missing_fields.append("Location")
    if not extracted["followers"]:
        missing_fields.append("Followers range")

    is_complete = len(missing_fields) == 0
    return is_complete, missing_fields, extracted


__all__ = [
    "get_slot_filler",
    "get_dynamic_results_store",
    "load_dynamic_results",
    "record_dynamic_results",
    "persist_dynamic_results",
    "convert_dynamic_search_to_standard_format",
    "clean_search_results",
    "compute_and_persist_metrics",
    "calculate_influencer_metrics",
    "check_prompt_requirements",
]

