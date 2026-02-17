from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from dotenv import load_dotenv
from fastapi import APIRouter, HTTPException, Query, Body

from app.services.data import temp_store
from app.services.core.prompt_service import load_dynamic_results
from app.utils.parsing import parse_number, parse_percentage
from app.utils.safe_response import client_safe_500_message

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")

# router = APIRouter(prefix=PREFIX_SEARCH, tags=["3. Analysis"])
logger = logging.getLogger(__name__)


def _get_dynamic_results_dir() -> Path:
    """DEPRECATED: Use temp_store instead. Kept for backwards compatibility."""
    storage_path = _PROJECT_ROOT / "storage"
    path = storage_path / "dynamic_results"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _load_dynamic_results_for_conversation(conversation_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Load dynamic results for a conversation using temp_store.
    Falls back to old storage/dynamic_results for backwards compatibility.
    """
    # Try new temp_store first
    results = load_dynamic_results(conversation_id)
    if results:
        logger.debug(f"✅ Loaded from temp_store: {conversation_id}")
        return results

    # Fallback to old location for backwards compatibility
    file_path = _get_dynamic_results_dir() / f"{conversation_id}.json"
    if not file_path.exists():
        logger.debug(f"❌ No results found: {conversation_id}")
        return None

    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
        logger.debug(f"✅ Loaded from legacy storage: {conversation_id}")
        return data.get("results", [])
    except Exception as e:
        logger.warning(f"Failed to read dynamic results for conversation {conversation_id}: {e}")
        return None


def _load_prompt_dynamic_results(conversation_id: str) -> Optional[List[Dict[str, Any]]]:
    """
    Load prompt-based dynamic search results by checking the shared in-memory store first,
    then falling back to persisted JSON files.
    """
    try:
        from app.services.core import prompt_service

        storage = prompt_service.get_dynamic_results_store()
        dynamic_results = storage.get(conversation_id)
        if dynamic_results:
            return dynamic_results
    except ImportError:
        pass

    return _load_dynamic_results_for_conversation(conversation_id)


def _get_latest_prompt_conversation_id() -> Optional[str]:
    """
    Return the most recent prompt_* conversation id using temp_store.
    Falls back to legacy storage for backwards compatibility.
    """
    # Try temp_store first (new approach)
    try:
        sessions = temp_store.list_sessions(include_expired=False)

        # Filter for prompt_* conversation IDs
        prompt_sessions = [
            s for s in sessions
            if s.get("conversation_id", "").startswith("prompt_")
        ]

        if prompt_sessions:
            # Sort by created_at timestamp (descending)
            prompt_sessions.sort(
                key=lambda s: s.get("created_at", 0),
                reverse=True
            )
            latest = prompt_sessions[0]["conversation_id"]
            logger.debug(f"✅ Found latest prompt session from temp_store: {latest}")
            return latest
    except Exception as e:
        logger.warning(f"Failed to get latest prompt from temp_store: {e}")

    # Fallback to legacy storage for backwards compatibility
    results_dir = _get_dynamic_results_dir()
    prompt_files = sorted(
        results_dir.glob("prompt_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for file_path in prompt_files:
        if file_path.is_file():
            logger.debug(f"✅ Found latest prompt session from legacy storage: {file_path.stem}")
            return file_path.stem

    return None


def _resolve_prompt_conversation_id(requested_conversation_id: Optional[str]) -> str:
    """
    Resolve the prompt conversation id.
    If user passes None or 'default', fall back to the latest prompt_* run.
    """
    if requested_conversation_id and requested_conversation_id != "default":
        return requested_conversation_id

    latest_prompt_id = _get_latest_prompt_conversation_id()
    if not latest_prompt_id:
        raise HTTPException(
            status_code=404,
            detail={
                "error": "No prompt-based dynamic searches found",
                "message": "Please run POST /api/dynamic-search/prompt first.",
            },
        )
    return latest_prompt_id


def _compute_dynamic_result_id(record: Dict[str, Any]) -> Optional[str]:
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


def _build_dynamic_dataframe(record: Dict[str, Any]) -> pd.DataFrame:
    """
    Build a DataFrame from dynamic search record that matches the structure expected by influencer_metrics.

    CRITICAL: This must match the REQUIRED_COLUMNS from influencer_metrics.py:
    - followers, following, posts, average_likes, average_comments
    - suspicious_fake_followers, real_followers, real_percentage
    - RATE, NICHE, Name, PROFILE LINK, CITY / STATE / BASE
    """

    # Helpers removed (parse_number, parse_percentage) - imported from utils.parsing

    # Get follower count for calculations (parse k/M notation)
    followers = parse_number(record.get("followers", 0))
    # real_followers_percentage is a percentage (e.g., 85.5 means 85.5%)
    # suspicious_followers_percentage is a percentage (e.g., 14.5 means 14.5%)
    real_followers_pct = parse_percentage(record.get("real_followers_percentage"))
    suspicious_followers_pct = parse_percentage(record.get("suspicious_followers_percentage"))
    
    # Fallback: If suspicious is missing but real exists, calculate it
    if suspicious_followers_pct <= 0 and real_followers_pct > 0:
        suspicious_followers_pct = 100.0 - real_followers_pct

    # Calculate actual counts from percentages
    real_followers = int(followers * (real_followers_pct / 100.0)) if followers > 0 else 0
    suspicious_fake_followers = int(followers * (suspicious_followers_pct / 100.0)) if followers > 0 else 0

    # Build row matching REQUIRED_COLUMNS from influencer_metrics.py
    row = {
        # Basic metrics (required) - use parse_number for all counts
        "followers": followers,
        "following": parse_number(record.get("following", 0)),
        "posts": parse_number(record.get("posts_count") or record.get("posts", 0)),
        "average_likes": parse_number(record.get("average_likes", 0)),
        "average_comments": parse_number(record.get("average_comments", 0)),

        # Authenticity metrics (required) - actual counts, not percentages
        "suspicious_fake_followers": suspicious_fake_followers,
        "real_followers": real_followers,
        "real_percentage": real_followers_pct,  # This is the percentage (0-100)

        # Pricing and categorization (required)
        "RATE": float(record.get("rate", 0)) if record.get("rate") else 0,
        "NICHE": record.get("niche") or record.get("NICHE", "Unknown"),
        "Name": record.get("name") or record.get("NAME") or "Unknown",
        "PROFILE LINK": record.get("profile_link") or record.get("PROFILE_LINK") or "",
        "CITY / STATE / BASE": record.get("location") or record.get("Location", "Unknown"),

        # Additional fields for CSV compatibility
        "engagement_rate": parse_percentage(record.get("engagement_rate")),
        "is_verified": record.get("is_verified", False),
        "is_business_account": record.get("is_business_account", False),
        "is_professional_account": record.get("is_professional_account", False),
        "platform": record.get("platform", "Instagram"),

        # Additional fields from scrapers - use parse_number for counts
        "average_views": parse_number(record.get("average_views", 0)),
        "biography": record.get("biography", ""),
        "external_url": record.get("external_url", ""),
        "business_category_name": record.get("business_category_name", ""),
        "category_name": record.get("category_name", ""),
        "highlights_count": parse_number(record.get("highlights_count", 0)),
        "is_joined_recently": record.get("is_joined_recently", False),
    }

    return pd.DataFrame([row])


def _persist_analysis_file_hash(conversation_id: str, influencer_id: str, file_hash: str, analysis_id: str) -> bool:
    """
    Persist the analysis file_hash back to the dynamic results storage using an atomic write.
    This ensures the JSON file won't be corrupted by concurrent writes.
    """
    try:
        # Try to load from temp_store first
        session_data = temp_store.load_session(conversation_id)

        if session_data and "results" in session_data:
            # Update in temp_store
            results_list = session_data["results"]

            updated = False
            for result in results_list:
                result_id = _compute_dynamic_result_id(result)
                if result_id == influencer_id:
                    result["analysis_file_hash"] = file_hash
                    result["analysis_id"] = analysis_id
                    updated = True
                    logger.debug(f"Persisted file_hash={file_hash} for influencer_id={influencer_id}")
                    break

            if updated:
                # Save back to temp_store
                temp_store.persist_session(conversation_id, session_data)
                logger.debug(f"✅ Updated temp_store: {conversation_id}")
                return True
            else:
                logger.warning(f"Could not find influencer {influencer_id} in temp_store")
                return False

        # Fallback to legacy storage
        dynamic_results_file = _get_dynamic_results_dir() / f"{conversation_id}.json"

        if not dynamic_results_file.exists():
            logger.warning(f"No data found in temp_store or legacy storage: {conversation_id}")
            return False

        # Load existing data from legacy storage
        data = json.loads(dynamic_results_file.read_text(encoding="utf-8"))
        results_list = data.get("results", [])

        # Find and update the influencer entry
        updated = False
        for result in results_list:
            result_id = _compute_dynamic_result_id(result)
            if result_id == influencer_id:
                result["analysis_file_hash"] = file_hash
                result["analysis_id"] = analysis_id
                updated = True
                logger.debug(f"Persisted file_hash={file_hash} for influencer_id={influencer_id}")
                break

        if not updated:
            logger.warning(f"Could not find influencer {influencer_id} in legacy results")
            return False

        # Atomic write to legacy storage
        temp_dir = dynamic_results_file.parent
        with tempfile.NamedTemporaryFile("w", delete=False, dir=str(temp_dir), encoding="utf-8") as tf:
            tf.write(json.dumps(data, indent=2, ensure_ascii=False))
            tmpname = tf.name

        Path(tmpname).replace(dynamic_results_file)

        logger.debug(f"✅ Updated legacy storage: {dynamic_results_file}")
        return True

    except Exception as e:
        logger.exception(f"Failed to persist analysis file_hash: {e}")
        return False


def _perform_virtual_analysis(influencer_id: str, conversation_id: str, record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform a 'virtual' analysis by calculating metrics from record data.
    This replaces the legacy run_analysis pipeline which is no longer available.
    """
    def parse_followers(value) -> int:
        if not value or str(value).upper() in {"N/A", "NA", "NONE", ""}:
            return 0
        if isinstance(value, (int, float)):
            return int(value)
        try:
            parsed = str(value).upper().replace(",", "").replace("+", "").strip()
            if not parsed or parsed in {"N/A", "NA", "NONE"}:
                return 0
            if "M" in parsed:
                return int(float(parsed.replace("M", "")) * 1_000_000)
            if "K" in parsed:
                return int(float(parsed.replace("K", "")) * 1_000)
            return int(float(parsed))
        except (ValueError, TypeError, AttributeError):
            return 0

    def parse_percentage(value) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        try:
            parsed = str(value).replace("%", "").strip()
            if not parsed or parsed.upper() in {"N/A", "NA", "NONE"} or parsed == "-":
                return 0.0
            return float(parsed)
        except (ValueError, TypeError, AttributeError):
            return 0.0

    def parse_rate(value) -> float:
        if not value or str(value).upper() in {"N/A", "NA", "NONE", ""}:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        try:
            cleaned = (
                str(value)
                .replace("₹", "")
                .replace(",", "")
                .replace("RS", "")
                .replace("rs", "")
                .strip()
            )
            if not cleaned or cleaned.upper() in {"N/A", "NA", "NONE"}:
                return 0.0
            return float(cleaned)
        except (ValueError, TypeError, AttributeError):
            return 0.0

    name = record.get("NAME") or record.get("name") or "Unknown"
    profile_link = record.get("PROFILE_LINK") or record.get("profile_link", "")

    followers_val = parse_followers(
        record.get("followers") or record.get("FOLLOWERS", 0)
    )
    following_val = parse_followers(
        record.get("following") or record.get("FOLLOWING", 0)
    )
    
    # BrightData posts: single source from app.services.legacy.brightdata
    from app.services.legacy.brightdata import get_posts_from_result, get_posts_count_from_result
    posts_list = get_posts_from_result(record)
    posts_val = get_posts_count_from_result(record)
    
    avg_likes_val = parse_followers(
        record.get("average_likes") or record.get("AVERAGE_LIKES", 0)
    )
    avg_comments_val = parse_followers(
        record.get("average_comments") or record.get("AVERAGE_COMMENTS", 0)
    )
    avg_views_val = parse_followers(
        record.get("average_views") or record.get("AVERAGE_VIEWS", 0)
    )
    engagement_rate_val = parse_percentage(record.get("engagement_rate", "0"))
    real_pct_val = parse_percentage(record.get("real_followers_percentage", "0"))
    suspicious_pct_val = parse_percentage(
        record.get("suspicious_followers_percentage", "0")
    )
    
    # Fallback: If suspicious is missing but real exists, calculate it
    if suspicious_pct_val <= 0 and real_pct_val > 0:
        suspicious_pct_val = 100.0 - real_pct_val
    
    rate_val = parse_rate(record.get("RATE", "N/A"))

    # Calculate derived values for metrics
    real_followers_count = (
        int(followers_val * (real_pct_val / 100.0))
        if followers_val > 0 and real_pct_val > 0
        else 0
    )
    suspicious_followers_count = (
        int(followers_val * (suspicious_pct_val / 100.0))
        if followers_val > 0 and suspicious_pct_val > 0
        else 0
    )

    try:
        from app.services.core.prompt_service import calculate_influencer_metrics

        # Use engagement_rate as-is (already in percentage format)
        temp_data = {
            "followers": followers_val,
            "following": following_val,
            "posts_count": posts_val,
            "posts": posts_val,  # count for metrics calc
            "average_likes": avg_likes_val,
            "avg_likes": avg_likes_val,
            "average_comments": avg_comments_val,
            "avg_comments": avg_comments_val,
            "average_views": avg_views_val,
            "avg_views": avg_views_val,
            "engagement_rate": engagement_rate_val,  # Use as-is, no normalization
            "real_followers_percentage": real_pct_val,
            "real_percentage": real_pct_val,
            "real_followers": real_followers_count,
            "suspicious_followers_percentage": suspicious_pct_val,
            "suspicious_fake_followers": suspicious_followers_count,
            "RATE": rate_val,
            "rate": rate_val,
            "is_verified": record.get("is_verified", False),
            "is_business_account": record.get("is_business_account", False),
            "is_professional_account": record.get("is_professional_account", False),
            "highlights_count": record.get("highlights_count", 0),
            "biography": record.get("biography", ""),
            "external_url": record.get("external_url", ""),
            "category_name": record.get("category_name", ""),
            "business_category_name": record.get("business_category_name", ""),
        }

        # Calculate comprehensive metrics
        calculated_metrics = calculate_influencer_metrics(temp_data)

        # Add chart-specific metric mappings for frontend compatibility
        calculated_metrics = _map_dynamic_metrics_for_charts(
            calculated_metrics,
            temp_data,
            record
        )
    except Exception as calc_exc:
        logger.warning("Failed to calculate fallback metrics: %s", calc_exc)
        calculated_metrics = {}

    # Extract profile picture URL using centralized utility
    from app.utils.image_utils import extract_profile_image
    username = record.get("Id") or record.get("username")
    profile_pic_url = extract_profile_image(record, username, "results_router")

    influencer_data = {
        "id": influencer_id,
        "name": name,
        "niche": record.get("NICHE", "Unknown"),
        "location": record.get("Location", "Unknown"),
        "profile_link": profile_link if profile_link else None,
        "profile_pic_url": profile_pic_url,  # Primary field
        "profile_picture_url": profile_pic_url,  # Alias
        "profile_image": profile_pic_url,  # Alias
        "image": profile_pic_url,  # Alias
        "followers": followers_val,
        "following": following_val,
        "posts_count": posts_val,
        "posts": posts_list,  # full list of post details from BrightData
        "average_likes": avg_likes_val,
        "avg_likes": avg_likes_val,
        "average_comments": avg_comments_val,
        "avg_comments": avg_comments_val,
        "average_views": avg_views_val,
        "avg_views": avg_views_val,
        "engagement_rate": engagement_rate_val,
        "real_followers_percentage": real_pct_val,
        "real_percentage": real_pct_val,
        "real_followers": real_followers_count,
        "suspicious_followers_percentage": suspicious_pct_val,
        "suspicious_fake_followers": suspicious_followers_count,
        "is_verified": record.get("is_verified", False),
        "is_business_account": record.get("is_business_account", False),
        "is_professional_account": record.get("is_professional_account", False),
        "is_joined_recently": record.get("is_joined_recently", False),
        "biography": record.get("biography", "N/A"),
        "external_url": record.get("external_url", "N/A"),
        "business_category_name": record.get("business_category_name", "N/A"),
        "category_name": record.get("category_name", "N/A"),
        "highlights_count": record.get("highlights_count", 0),
        "rate": rate_val,
        "RATE": rate_val,
        "source": record.get("source", "prompt_dynamic"),
        "checked_at": record.get("checked_at", None),
        "username": username,
        "id_name": username,
        "metrics": calculated_metrics,
        "raw_data": calculated_metrics,
        "post_analysis": record.get("post_analysis", {}),
        "hashtag_analysis": record.get("hashtag_analysis", {}),
        "top_hashtags": record.get("top_hashtags", []),
    }

    return {
        "influencer_id": influencer_id,
        "influencer": influencer_data,
        "status": "analyzed",
        "analysis_done": True,
        "aggregates": {},  # Populated in main entry points if needed
        "metadata": {},
    }


def _analyze_dynamic_influencer(influencer_id: str, conversation_id: str, record: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    logger.debug(
        "Performing virtual dynamic analysis for influencer_id=%s (conversation %s)",
        influencer_id,
        conversation_id,
    )
    try:
        # Perform retrieval of data and calculation of metrics
        analysis_result = _perform_virtual_analysis(influencer_id, conversation_id, record)
        
        if not analysis_result or not analysis_result.get("influencer"):
            return None

        # Calculate file_hash consistent with how report_controller expects it
        file_hash = hashlib.md5(f"dynamic_{conversation_id}_{influencer_id}".encode()).hexdigest()[:12]
        
        # Prepare the full results object to match the storage/results/*.json schema
        full_results = {
            "influencers": [analysis_result["influencer"]],
            "aggregates": analysis_result.get("aggregates", {}),
            "metadata": {
                **analysis_result.get("metadata", {}),
                "file_hash": file_hash,
                "conversation_id": conversation_id,
                "influencer_id": influencer_id,
                "source": "virtual_analysis"
            },
            "details": {
                analysis_result["influencer"].get("id"): analysis_result["influencer"]
            }
        }

        # Save to disk so other controllers can find it
        results_path = _PROJECT_ROOT / "storage" / "results"
        results_path.mkdir(parents=True, exist_ok=True)
        file_path = results_path / f"{file_hash}.json"
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(full_results, f, indent=2, ensure_ascii=False)
            
        logger.debug(f"✓ Persisted virtual analysis to disk: {file_path}")

        # Map back to the expected return format for this function
        analysis_id = analysis_result["influencer"].get("id")
        
        # Persist file_hash back to dynamic results storage for lookup
        _persist_analysis_file_hash(conversation_id, influencer_id, file_hash, analysis_id)

        analysis_result["file_hash"] = file_hash
        analysis_result["analysis_id"] = analysis_id
        
        return analysis_result
        
    except Exception as e:
        logger.exception(f"Failed to analyze dynamic influencer {influencer_id}: {e}")
        return None


def _find_influencer_in_dataset(influencer_id: str) -> Optional[Dict[str, Any]]:
    """
    Search for an influencer in the dataset CSV files by matching the ID generation logic.
    This is used when the influencer hasn't been analyzed yet but exists in the dataset.
    Uses the same column standardization as the search engine.
    
    Uses dynamic dataset (INFLUENCER_DATA_PATH) - from uploads
    """
    try:
        from app.services.data.influencer_dataset import get_dataset, load_dataset_from_path
        import pandas as pd
        import hashlib
        
        df = None
        
        # Try dynamic dataset first (if configured)
        try:
            df = get_dataset(copy=False)
            if df.empty:
                df = None
        except (ValueError, FileNotFoundError) as e:
            logger.debug("Dynamic dataset not available: %s", e)
            df = None
        
        # If dynamic dataset not available, skip
        if df is None or df.empty:
            df = None
        
        if df is None or df.empty:
            logger.debug("No dataset available")
            return None
        
        # Helper function to get value from row with multiple column name variations
        def get_value(row, standard_name, variations):
            """Get value from row trying standard name first, then variations."""
            # Try standard name first
            if standard_name in df.columns:
                value = row.get(standard_name)
                if pd.notna(value) and value != "":
                    return value
            
            # Try variations
            for col in df.columns:
                col_str = str(col).strip()
                if col_str in variations or col_str.lower() in [v.lower() for v in variations]:
                    value = row.get(col)
                    if pd.notna(value) and value != "":
                        return value
            
            # Try case-insensitive match
            standard_lower = standard_name.lower()
            for col in df.columns:
                if str(col).strip().lower() == standard_lower:
                    value = row.get(col)
                    if pd.notna(value) and value != "":
                        return value
            
            return None
        
        # Try to find influencer by matching ID generation logic
        for idx, row in df.iterrows():
            # Get profile_link - try multiple column name variations
            profile_link = None
            profile_variations = ["profile_link", "profile link", "profile", "url", "profile_url", "handle link", "PROFILE_LINK", "Profile Link"]
            for col in df.columns:
                col_lower = str(col).lower().strip()
                if any(variation.lower() in col_lower for variation in ["profile", "link", "url"]):
                    profile_link = row.get(col, None)
                    if pd.notna(profile_link) and profile_link and str(profile_link).strip():
                        break
            
            # Generate ID the same way as search does
            generated_id = None
            if profile_link and pd.notna(profile_link) and str(profile_link).strip():
                generated_id = hashlib.md5(str(profile_link).encode()).hexdigest()[:12]
            else:
                # Get name - try multiple variations
                name = get_value(row, "Name", ["name", "NAME", "influencer_name", "Name"])
                if not name or pd.isna(name):
                    name = "Unknown"
                else:
                    name = str(name).strip()
                
                # Get location - try multiple variations including "CITY / STATE / BASE"
                location = get_value(row, "location", ["location", "LOCATION", "city", "CITY", "state", "STATE", "base", "BASE"])
                if not location or pd.isna(location):
                    # Try "CITY / STATE / BASE" column
                    location = get_value(row, "CITY / STATE / BASE", ["CITY / STATE / BASE", "city / state / base", "City / State / Base"])
                if not location or pd.isna(location):
                    location = "Unknown"
                else:
                    location = str(location).strip()
                
                # Get niche
                niche = get_value(row, "NICHE", ["niche", "NICHE", "type", "TYPE", "category", "CATEGORY"])
                if not niche or pd.isna(niche):
                    niche = "Unknown"
                else:
                    niche = str(niche).strip()
                
                unique_string = f"{name}_{location}_{niche}_{idx}"
                generated_id = hashlib.md5(unique_string.encode()).hexdigest()[:12]
            
            if generated_id == influencer_id:
                # Found the influencer in dataset
                # Get all values using the same logic
                name = get_value(row, "Name", ["name", "NAME", "influencer_name", "Name"])
                if not name or pd.isna(name):
                    name = "Unknown"
                else:
                    name = str(name).strip()
                
                location = get_value(row, "location", ["location", "LOCATION", "city", "CITY", "state", "STATE", "base", "BASE"])
                if not location or pd.isna(location):
                    location = get_value(row, "CITY / STATE / BASE", ["CITY / STATE / BASE", "city / state / base", "City / State / Base"])
                if not location or pd.isna(location):
                    location = "Unknown"
                else:
                    location = str(location).strip()
                
                niche = get_value(row, "NICHE", ["niche", "NICHE", "type", "TYPE", "category", "CATEGORY"])
                if not niche or pd.isna(niche):
                    niche = "Unknown"
                else:
                    niche = str(niche).strip()
                
                # Get followers - try multiple variations
                followers = get_value(row, "followers", ["followers", "Followers", "FOLLOWERS", "follower_count", "FOLLOWER_COUNT"])
                followers_int = 0
                if followers and pd.notna(followers):
                    try:
                        followers_int = int(float(str(followers)))
                    except (ValueError, TypeError):
                        followers_int = 0
                
                # Return basic info (since it hasn't been analyzed)
                return {
                    "file_hash": None,
                    "influencer": {
                        "id": influencer_id,
                        "name": name,
                        "niche": niche,
                        "location": location,
                        "followers": followers_int,
                        "profile_link": str(profile_link).strip() if profile_link and pd.notna(profile_link) else None,
                    },
                    "results_data": None,
                    "from_dataset": True
                }
    except Exception as e:
        logger.error("Failed to search dataset for influencer %s: %s", influencer_id, e)
        logger.exception("Full traceback:")
    
    return None


def _find_influencer_by_id(influencer_id: str, profile_link: Optional[str] = None, name: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Search for an influencer by ID, profile_link, or name across all result files.
    
    Args:
        influencer_id: Influencer ID (from search results - MD5 hash)
        profile_link: Optional profile link to match
        name: Optional name to match
    
    Returns:
        Dictionary with 'file_hash', 'influencer', and 'results_data' if found, None otherwise
    """
    # Search through all result JSON files
    results_path_dir = _PROJECT_ROOT / "storage" / "results"
    for results_path in results_path_dir.glob("*.json"):
        try:
            results_data = json.loads(results_path.read_text(encoding="utf-8"))
            influencers = results_data.get("influencers", [])
            details = results_data.get("details", {})
            
            # First try: Search by exact ID match
            influencer = next((inf for inf in influencers if inf.get("id") == influencer_id), None)
            
            # Second try: If not found and profile_link provided, search by profile_link
            if not influencer and profile_link:
                # Normalize profile_link for comparison (remove query params, trailing slashes)
                def normalize_url(url: str) -> str:
                    if not url:
                        return ""
                    url = url.strip().lower()
                    # Remove query parameters
                    if "?" in url:
                        url = url.split("?")[0]
                    # Remove trailing slash
                    url = url.rstrip("/")
                    return url
                
                normalized_search_link = normalize_url(profile_link)
                
                for inf in influencers:
                    inf_profile_link = normalize_url(inf.get("profile_link", ""))
                    if inf_profile_link and normalized_search_link == inf_profile_link:
                        influencer = inf
                        break
                    # Also check in details
                    inf_id = inf.get("id")
                    if inf_id and inf_id in details:
                        detail_profile_link = normalize_url(details[inf_id].get("profile_link", ""))
                        if detail_profile_link and normalized_search_link == detail_profile_link:
                            influencer = inf
                            break
            
            # Third try: If not found and name provided, search by name (fuzzy match)
            if not influencer and name:
                name_lower = name.strip().lower()
                for inf in influencers:
                    inf_name = inf.get("name", "").strip().lower()
                    if inf_name and inf_name == name_lower:
                        influencer = inf
                        break
                    # Also check in details
                    inf_id = inf.get("id")
                    if inf_id and inf_id in details:
                        detail_name = details[inf_id].get("name", "").strip().lower()
                        if detail_name and detail_name == name_lower:
                            influencer = inf
                            break
            
            if influencer:
                file_hash = results_path.stem  # filename without .json extension
                return {
                    "file_hash": file_hash,
                    "influencer": influencer,
                    "results_data": results_data
                }
        except Exception as e:
            logger.debug("Failed to read results file %s: %s", results_path, e)
            continue

    # Checked all files, not found
    return None


def _analyze_single_influencer(influencer_id: str, dataset_info: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Automatically analyze a single influencer from the dataset.
    Uses virtual analysis to calculate metrics from available record data.
    """
    logger.debug("Performing virtual single-influencer analysis for %s", influencer_id)
    try:
        # Extract record from dataset_info if wrapped, otherwise use as-is
        record = dataset_info.get("influencer", dataset_info)
        analysis_result = _perform_virtual_analysis(influencer_id, "single", record)
        
        if not analysis_result or not analysis_result.get("influencer"):
            return None

        # Calculate file_hash consistent with how it's used elsewhere for single influencers
        file_hash = hashlib.md5(f"single_{influencer_id}".encode()).hexdigest()[:12]
        
        # Prepare the full results object
        full_results = {
            "influencers": [analysis_result["influencer"]],
            "aggregates": {},
            "metadata": {
                "file_hash": file_hash,
                "influencer_id": influencer_id,
                "source": "virtual_single_analysis"
            },
            "details": {
                analysis_result["influencer"].get("id"): analysis_result["influencer"]
            }
        }

        # Save to disk
        results_path = _PROJECT_ROOT / "storage" / "results"
        results_path.mkdir(parents=True, exist_ok=True)
        file_path = results_path / f"{file_hash}.json"
        
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(full_results, f, indent=2, ensure_ascii=False)
            
        logger.debug(f"✓ Persisted virtual single analysis to disk: {file_path}")

        analysis_result["file_hash"] = file_hash
        return analysis_result

    except Exception as e:
        logger.exception(f"Failed to analyze single influencer {influencer_id}: {e}")
        return None

    logger.debug("🔍 _analyze_single_influencer called for influencer_id=%s", influencer_id)
    try:
        from app.services.data.influencer_dataset import get_dataset, load_dataset_from_path
        import pandas as pd
        
        logger.debug("→ Getting dataset...")
        # Try to get dataset from dynamic source
        df_original = None
        
        # Try dynamic dataset first (if configured)
        try:
            df_original = get_dataset(copy=False)
            if df_original.empty:
                df_original = None
        except (ValueError, FileNotFoundError) as e:
            logger.debug("Dynamic dataset not available: %s", e)
            df_original = None
        
        # If dynamic dataset not available, skip
        if df_original is None or df_original.empty:
            df_original = None
        
        if df_original is None or df_original.empty:
            logger.error("✗ No dataset available!")
            return None
        
        logger.debug("✓ Dataset loaded with %d rows and %d columns", len(df_original), len(df_original.columns))
        
        # Make a copy for manipulation
        df = df_original.copy(deep=True)
        
        # Clean up problematic columns before saving to CSV
        # Handle 'posts' column if it contains JSON arrays
        # The JSON array only contains a SAMPLE of posts, not all posts
        # Use posts_count instead for the actual total count
        if 'posts' in df.columns:
            for idx, val in df['posts'].items():
                if pd.notna(val) and isinstance(val, str) and (val.startswith('[') or val.startswith('{')):
                    # It's a JSON string with post samples - use posts_count instead
                    if 'posts_count' in df.columns:
                        posts_count_val = df.at[idx, 'posts_count']
                        if pd.notna(posts_count_val):
                            df.at[idx, 'posts'] = posts_count_val
                        else:
                            df.at[idx, 'posts'] = 0
                    else:
                        # No posts_count available, try to count JSON array as fallback
                        try:
                            import json
                            posts_data = json.loads(val)
                            if isinstance(posts_data, list):
                                df.at[idx, 'posts'] = len(posts_data)
                            else:
                                df.at[idx, 'posts'] = 0
                        except:
                            df.at[idx, 'posts'] = 0
        
        # Find the influencer row in the dataset
        influencer_data = dataset_info["influencer"]
        profile_link = influencer_data.get("profile_link")
        name = influencer_data.get("name")
        
        logger.debug("→ Searching for influencer: name=%s, profile_link=%s", name, profile_link)
        
        # Find the row matching this influencer
        matching_row = None
        matching_idx = None
        
        # Normalize URL helper function
        def normalize_url(url: str) -> str:
            """Normalize URL for comparison."""
            if not url:
                return ""
            url = str(url).strip().lower()
            if "?" in url:
                url = url.split("?")[0]
            if "#" in url:
                url = url.split("#")[0]
            url = url.rstrip("/")
            url = url.replace("https://", "").replace("http://", "")
            url = url.replace("www.", "")
            if "/" in url:
                parts = url.split("/", 1)
                if len(parts) == 2:
                    domain, path = parts
                    path = path.rstrip("/")
                    return f"{domain}/{path}"
            return url
        
        # Normalize the search profile_link
        normalized_search_link = normalize_url(profile_link) if profile_link else ""
        logger.debug("  Normalized search profile_link: %s", normalized_search_link)
        
        for idx, row in df.iterrows():
            # Match by profile_link first (most reliable)
            if profile_link and normalized_search_link:
                for col in df.columns:
                    col_lower = str(col).lower().strip()
                    if "profile" in col_lower or "link" in col_lower or "url" in col_lower:
                        row_profile = row.get(col)
                        if pd.notna(row_profile) and str(row_profile).strip():
                            normalized_row_link = normalize_url(str(row_profile))
                            if normalized_row_link and normalized_row_link == normalized_search_link:
                                matching_row = row
                                matching_idx = idx
                                logger.debug("  ✓ Matched by profile_link at index %s", idx)
                                break
                if matching_row is not None:
                    break
            
            # Match by name if profile_link didn't match
            if matching_row is None and name and name != "Unknown":
                for col in df.columns:
                    if "name" in str(col).lower():
                        row_name = str(row.get(col, "")).strip()
                        if row_name and row_name.lower() == name.lower():
                            matching_row = row
                            matching_idx = idx
                            logger.debug("  ✓ Matched by name at index %s", idx)
                            break
                if matching_row is not None:
                    break
        
        if matching_row is None:
            logger.error("✗ Could not find matching row in dataset for influencer %s", influencer_id)
            return None
        
        logger.info("✓ Found matching row at index %s", matching_idx)
        logger.info("  Original dataset has %d columns: %s", len(df.columns), list(df.columns)[:10])
        
        # Log some key values from the matched row to verify data
        logger.debug("  Sample values from matched row:")
        sample_cols = ['NAME', 'Name', 'PROFILE LINK', 'followers', 'NICHE', 'Location', 'RATE']
        for col in sample_cols:
            if col in df.columns:
                val = matching_row.get(col)
                logger.debug("    %s = %s", col, val)
        
        # Create a DataFrame with just this influencer - preserve ALL columns from original dataset
        # Use iloc to get the exact row by index to preserve all data types and values
        # This ensures we get the exact row from the original CSV with all its values
        single_influencer_df = df.iloc[[matching_idx]].copy()  # Use cleaned df, not df_original
        
        # Ensure we have all columns from the original dataset
        if len(single_influencer_df.columns) != len(df.columns):
            logger.error("Column count mismatch! Original: %d, Single: %d", len(df.columns), len(single_influencer_df.columns))
            raise ValueError("Column count mismatch when creating single influencer DataFrame")
        
        # Additional cleanup for JSON columns in the single row
        for col in single_influencer_df.columns:
            val = single_influencer_df[col].iloc[0] if len(single_influencer_df) > 0 else None
            if pd.notna(val) and isinstance(val, str):
                # Check if it's a JSON string (starts with [ or {)
                if (val.startswith('[') or val.startswith('{')) and len(val) > 100:
                    # For large JSON strings (like post_hashtags), truncate or simplify
                    if col in ['post_hashtags', 'posts']:
                        try:
                            import json
                            json_data = json.loads(val)
                            if isinstance(json_data, list):
                                # For posts, store count; for hashtags, store first few
                                if col == 'posts':
                                    single_influencer_df.at[single_influencer_df.index[0], col] = len(json_data)
                                elif col == 'post_hashtags':
                                    # Keep it as JSON or simplify
                                    single_influencer_df.at[single_influencer_df.index[0], col] = str(json_data[:3]) if len(json_data) > 3 else val
                        except:
                            pass  # Keep original value if JSON parsing fails
        
        logger.debug("✓ Extracted row using iloc - preserving all %d columns", len(single_influencer_df.columns))
        
        # Log actual data in the DataFrame before saving
        logger.debug("✓ Created DataFrame with %d row(s) and %d columns", len(single_influencer_df), len(single_influencer_df.columns))
        logger.debug("  DataFrame columns: %s", list(single_influencer_df.columns)[:15])
        
        # Verify key values are present
        for col in ['NAME', 'Name', 'PROFILE LINK', 'followers']:
            if col in single_influencer_df.columns:
                val = single_influencer_df[col].iloc[0]
                logger.debug("  Verified %s = %s (type: %s)", col, val, type(val).__name__)
        
        # Add platform column if missing (required by CSV parser)
        # Infer platform from profile_link
        if "platform" not in single_influencer_df.columns or single_influencer_df["platform"].isna().all():
            profile_link = profile_link or ""
            profile_link_lower = str(profile_link).lower()
            if "instagram.com" in profile_link_lower or "instagr.am" in profile_link_lower:
                platform_value = "Instagram"
            elif "youtube.com" in profile_link_lower or "youtu.be" in profile_link_lower:
                platform_value = "YouTube"
            elif "tiktok.com" in profile_link_lower:
                platform_value = "TikTok"
            elif "twitter.com" in profile_link_lower or "x.com" in profile_link_lower:
                platform_value = "Twitter"
            elif "facebook.com" in profile_link_lower:
                platform_value = "Facebook"
            else:
                # Default to Instagram if we can't determine
                platform_value = "Instagram"
            
            single_influencer_df["platform"] = platform_value
            logger.debug("✓ Added platform column: %s (inferred from profile_link)", platform_value)
        
        # Generate a file_hash for this single influencer analysis
        file_hash = hashlib.md5(f"single_{influencer_id}".encode()).hexdigest()[:12]
        logger.debug("→ Generated file_hash: %s", file_hash)
        
        # Create temporary CSV file
        temp_dir = _PROJECT_ROOT / "storage" / "uploads"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_file = temp_dir / f"{file_hash}_temp.csv"
        
        # Save the single influencer to CSV - preserve all columns and values
        # Use to_csv with proper parameters to ensure all data is written
        # Don't use float_format to avoid converting integers to floats
        single_influencer_df.to_csv(
            temp_file, 
            index=False, 
            encoding='utf-8',
            # Don't convert NaN to empty string - let pandas handle it naturally
        )
        file_size = temp_file.stat().st_size if temp_file.exists() else 0
        logger.info("✓ Created temporary file: %s (size: %d bytes)", temp_file, file_size)
        
        # Verify the saved CSV has all columns and data
        try:
            verify_df = pd.read_csv(temp_file, nrows=1, dtype=str, keep_default_na=False)
            logger.info("✓ Verified CSV has %d columns: %s", len(verify_df.columns), list(verify_df.columns)[:10])
            
            # Check if key columns have values
            for col in ['NAME', 'Name', 'PROFILE LINK', 'followers']:
                if col in verify_df.columns:
                    val = verify_df[col].iloc[0] if len(verify_df) > 0 else None
                    logger.info("  CSV value for %s = %s", col, val)
                    if not val or val == '' or pd.isna(val):
                        logger.warning("  ⚠️ WARNING: %s is empty in saved CSV!", col)
        except Exception as e:
            logger.error("Could not verify CSV columns: %s", e)
            logger.exception("Full traceback:")
        
        # Run analysis on this single influencer
        logger.info("→ Starting run_analysis for file_hash=%s, raw_path=%s", file_hash, temp_file)
        try:
            results = run_analysis(
                file_hash=file_hash,
                raw_path=str(temp_file),
                top_n=1  # Only one influencer
            )
            logger.info("✓ run_analysis completed. Results keys: %s", list(results.keys()) if results else "None")
            
            # Find the influencer in results (it will have ID like {file_hash}-r0)
            if results and results.get("influencers"):
                analysis_influencer = results["influencers"][0]
                analysis_influencer_id = analysis_influencer.get("id")
                
                # Get full detail
                details = results.get("details", {})
                influencer_detail = details.get(analysis_influencer_id, {}) if analysis_influencer_id else {}
                
                # Combine data
                full_influencer_data = {
                    **analysis_influencer,
                    **influencer_detail
                }
                
                # Preserve the original influencer_id from search
                full_influencer_data["id"] = influencer_id
                
                # Return the same format as the main endpoint
                return {
                    "influencer_id": influencer_id,
                    "influencer": full_influencer_data,
                    "status": "analyzed",
                    "analysis_done": True,
                    "aggregates": results.get("aggregates", {}),
                    "metadata": results.get("metadata", {}),
                }
            else:
                logger.warning("Analysis completed but no influencers found in results for %s", influencer_id)
                return None
                
        except Exception as e:
            logger.error("Error running analysis for influencer %s: %s", influencer_id, e)
            return None
        finally:
            # Clean up temporary file
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception:
                pass
                
    except Exception as e:
        logger.exception("Failed to analyze single influencer %s: %s", influencer_id, e)
        return None


def _extract_parsing_metadata(metadata: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Extract parsing metadata from sanitized file."""
    sanitized_path = metadata.get("sanitized_path")
    if not sanitized_path:
        return None
    
    sanitized_file = Path(sanitized_path)
    if not sanitized_file.exists():
        return None
    
    try:
        import pandas as pd
        df = pd.read_csv(sanitized_file)
        rows_cleaned = len(df)
        
        upload_path = metadata.get("upload_path")
        rows_original = None
        if upload_path:
            raw_file = Path(upload_path)
            if raw_file.exists():
                try:
                    with open(raw_file, 'r', encoding='utf-8', errors='ignore') as f:
                        raw_lines = sum(1 for line in f if line.strip())
                    rows_original = max(0, raw_lines - 1)
                except Exception:
                    pass
        
        meta = {
            "rows_cleaned": rows_cleaned,
            "sanitized_path": str(sanitized_path),
        }
        
        if rows_original is not None:
            meta["rows_original"] = rows_original
            meta["invalid_count"] = max(0, rows_original - rows_cleaned)
        
        return meta
    except Exception as e:
        logger.debug("Could not extract metadata from sanitized file: %s", e)
        return {"sanitized_path": str(sanitized_path)}


def _find_existing_analysis_by_profile_link(
    profile_link: str,
    name: str,
    influencer_id: str
) -> Optional[Dict[str, Any]]:
    """
    Search for existing analysis results by profile_link or name.
    This is used for dynamic influencers to check if they've already been analyzed.

    Returns the same format as get_results() for consistency.
    """
    logger.info(f"🔍 Searching for existing analysis: profile_link={profile_link}, name={name}")

    # Normalize URL helper
    def normalize_url(url: str) -> str:
        if not url:
            return ""
        url = str(url).strip().lower()
        if "?" in url:
            url = url.split("?")[0]
        if "#" in url:
            url = url.split("#")[0]
        url = url.rstrip("/")
        url = url.replace("https://", "").replace("http://", "")
        url = url.replace("www.", "")
        if "/" in url:
            parts = url.split("/", 1)
            if len(parts) == 2:
                domain, path = parts
                path = path.rstrip("/")
                return f"{domain}/{path}"
        return url

    # Search through all result JSON files
    results_path_dir = _PROJECT_ROOT / "storage" / "results"
    results_files = list(results_path_dir.glob("*.json"))
    logger.info(f"  Searching {len(results_files)} results files...")

    for results_path in results_files:
        try:
            results_data = json.loads(results_path.read_text(encoding="utf-8"))
            influencers = results_data.get("influencers", [])
            details = results_data.get("details", {})

            for inf in influencers:
                inf_id = inf.get("id")
                inf_profile_link = inf.get("profile_link", "")
                inf_name = inf.get("name", "").strip().lower()

                # Match 1: Exact ID match
                if inf_id == influencer_id:
                    logger.debug(f"  ✓ Found by exact ID match: {inf_id}")
                    # Get full details
                    influencer_detail = details.get(inf_id, {})
                    full_influencer_data = {**inf, **influencer_detail}
                    full_influencer_data["id"] = influencer_id  # Preserve search ID

                    return {
                        "influencer_id": influencer_id,
                        "influencer": full_influencer_data,
                        "status": "analyzed",
                        "analysis_done": True,
                        "aggregates": results_data.get("aggregates", {}),
                        "metadata": results_data.get("metadata", {}),
                    }

                # Match 2: Profile link match (normalized)
                if profile_link and inf_profile_link:
                    normalized_search = normalize_url(profile_link)
                    normalized_inf = normalize_url(inf_profile_link)
                    if normalized_search and normalized_inf and normalized_search == normalized_inf:
                        logger.debug(f"  ✓ Found by profile_link match: {normalized_search}")
                        # Get full details
                        influencer_detail = details.get(inf_id, {})
                        full_influencer_data = {**inf, **influencer_detail}
                        full_influencer_data["id"] = influencer_id  # Preserve search ID

                        return {
                            "influencer_id": influencer_id,
                            "influencer": full_influencer_data,
                            "status": "analyzed",
                            "analysis_done": True,
                            "aggregates": results_data.get("aggregates", {}),
                            "metadata": results_data.get("metadata", {}),
                        }

                # Match 3: Check in details by profile_link
                if inf_id and inf_id in details:
                    detail = details[inf_id]
                    detail_profile_link = detail.get("profile_link", "")

                    if profile_link and detail_profile_link:
                        normalized_search = normalize_url(profile_link)
                        normalized_detail = normalize_url(detail_profile_link)
                        if normalized_search and normalized_detail and normalized_search == normalized_detail:
                            logger.debug(f"  ✓ Found by detail profile_link match: {normalized_search}")
                            full_influencer_data = {**inf, **detail}
                            full_influencer_data["id"] = influencer_id  # Preserve search ID

                            return {
                                "influencer_id": influencer_id,
                                "influencer": full_influencer_data,
                                "status": "analyzed",
                                "analysis_done": True,
                                "aggregates": results_data.get("aggregates", {}),
                                "metadata": results_data.get("metadata", {}),
                            }

                # Match 4: Name match (as fallback)
                if name and inf_name and name != "Unknown":
                    name_normalized = name.strip().lower()
                    if name_normalized and name_normalized == inf_name:
                        logger.debug(f"  ✓ Found by name match: {name_normalized}")
                        influencer_detail = details.get(inf_id, {})
                        full_influencer_data = {**inf, **influencer_detail}
                        full_influencer_data["id"] = influencer_id  # Preserve search ID

                        return {
                            "influencer_id": influencer_id,
                            "influencer": full_influencer_data,
                            "status": "analyzed",
                            "analysis_done": True,
                            "aggregates": results_data.get("aggregates", {}),
                            "metadata": results_data.get("metadata", {}),
                        }

        except Exception as e:
            logger.debug(f"Failed to read results file {results_path}: {e}")
            continue

    logger.info("  ✗ No existing analysis found")
    return None


def _map_dynamic_metrics_for_charts(
    calculated_metrics: Dict[str, float],
    influencer_data: Dict[str, Any],
    raw_data: Dict[str, Any]
) -> Dict[str, float]:
    """
    Map calculated metrics to chart-compatible format.
    Ensures all metrics expected by frontend charts are present with correct names.
    """
    mapped = calculated_metrics.copy()

    def safe_get(key: str, default: float = 0.0) -> float:
        """Safely get numeric value from influencer data or calculated metrics."""
        val = influencer_data.get(key, calculated_metrics.get(key, default))
        if val is None or val == "N/A":
            return default
        try:
            return float(val)
        except (ValueError, TypeError):
            return default

    # Basic values
    followers = safe_get("followers", 0.0)
    following = safe_get("following", 0.0)
    avg_likes = safe_get("average_likes", 0.0) or safe_get("avg_likes", 0.0)
    avg_comments = safe_get("average_comments", 0.0) or safe_get("avg_comments", 0.0)
    posts_count = safe_get("posts_count", 0.0) or safe_get("posts", 0.0)
    engagement_rate = safe_get("engagement_rate", 0.0)
    rate = safe_get("rate", 0.0) or safe_get("RATE", 0.0)
    real_pct = safe_get("real_followers_percentage", 0.0) or safe_get("real_percentage", 0.0)
    suspicious_pct = safe_get("suspicious_followers_percentage", 0.0)

    # Chart-required metrics - calculate if not present
    if "like_to_follower_ratio" not in mapped and followers > 0:
        mapped["like_to_follower_ratio"] = (avg_likes / followers) * 100  # As percentage

    if "comment_to_follower_ratio" not in mapped and followers > 0:
        mapped["comment_to_follower_ratio"] = (avg_comments / followers) * 100  # As percentage

    # Engagement velocity (same as engagement rate for charts)
    if "engagement_velocity" not in mapped:
        mapped["engagement_velocity"] = engagement_rate

    # Real/fake follower ratios (as percentages 0-100)
    if "real_follower_ratio" not in mapped:
        mapped["real_follower_ratio"] = real_pct

    if "fake_follower_ratio" not in mapped:
        mapped["fake_follower_ratio"] = suspicious_pct if suspicious_pct > 0 else max(0.0, 100.0 - real_pct)

    # Cost metrics (if rate is available)
    if rate > 0:
        if "cost_per_follower" not in mapped and followers > 0:
            mapped["cost_per_follower"] = rate / followers

        total_engagement = avg_likes + avg_comments
        if "cost_per_engagement" not in mapped and total_engagement > 0:
            mapped["cost_per_engagement"] = rate / total_engagement

        if "cost_per_real_follower" not in mapped and followers > 0 and real_pct > 0:
            real_followers = followers * (real_pct / 100.0)
            if real_followers > 0:
                mapped["cost_per_real_follower"] = rate / real_followers

    # Follower to following ratio
    if "follower_to_following_ratio" not in mapped and following > 0:
        mapped["follower_to_following_ratio"] = followers / following

    # Growth and saturation indices
    if "growth_saturation_index" not in mapped and posts_count > 0 and followers > 0:
        mapped["growth_saturation_index"] = (posts_count / followers) * 100

    if "activity_saturation_index" not in mapped and posts_count > 0:
        # Normalize to 0-100 scale
        mapped["activity_saturation_index"] = min((posts_count / 1000.0) * 100, 100.0)

    # Content performance metrics
    if "audience_interaction_score" not in mapped:
        mapped["audience_interaction_score"] = engagement_rate  # Already in percentage

    total_engagement = avg_likes + avg_comments
    if "post_efficiency_score" not in mapped and total_engagement > 0:
        # Normalize to 0-100 scale
        mapped["post_efficiency_score"] = min((total_engagement / 100.0), 100.0)

    if "comment_depth_ratio" not in mapped and avg_likes > 0:
        mapped["comment_depth_ratio"] = avg_comments / avg_likes

    # Health and quality scores (composite metrics)
    if "health_score" not in mapped:
        # Simple health score: combination of engagement and authenticity
        mapped["health_score"] = (engagement_rate * 0.5) + (real_pct * 0.5)

    if "influencer_quality_score" not in mapped:
        # Quality score: weighted combination of multiple factors
        engagement_score = engagement_rate  # Already in percentage
        authenticity_score = real_pct
        follower_score = min((followers / 10000.0), 100.0)  # Normalize followers
        mapped["influencer_quality_score"] = (
            (engagement_score * 0.4) + (authenticity_score * 0.4) + (follower_score * 0.2)
        )

    if "authenticity_score" not in mapped:
        # Authenticity: combination of real followers % and engagement
        mapped["authenticity_score"] = (real_pct * engagement_rate) / 100.0

    # Remove any None, NaN, or invalid values
    cleaned_metrics = {}
    for key, value in mapped.items():
        if value is None:
            continue
        try:
            float_val = float(value)
            if not (math.isnan(float_val) or math.isinf(float_val)):
                cleaned_metrics[key] = round(float_val, 2)
        except (ValueError, TypeError):
            continue

    return cleaned_metrics


async def get_prompt_dynamic_results(
    influencer_id: str = Query(..., description="Influencer ID from prompt-only dynamic results"),
    conversation_id: Optional[str] = Query(
        None,
        description="Prompt conversation ID (omit to use the latest prompt_* run)",
    ),
):
    """
    **Step 4: Get detailed analysis for an influencer from DYNAMIC web search**

    After searching with `/api/dynamic-search/prompt` or `/api/dynamic-search/prompt-stream`,
    use this endpoint to get full analysis for a specific discovered influencer.

    **Use this for:** Dynamic search results only

    **Parameters:**
    - **influencer_id**: The ID from your dynamic search results
    - **conversation_id**: (Optional) Specific search session ID. If omitted, uses most recent search.

    **What you get:**
    - Scraped social media metrics
    - Engagement rate analysis
    - Follower demographics
    - Content performance data
    - Authenticity scoring
    - Platform-specific insights

    **Example:**
    ```
    GET /api/results/dynamic/prompt?influencer_id=abc123
    GET /api/results/dynamic/prompt?influencer_id=abc123&conversation_id=prompt_b749dce7
    ```

    **Auto-resolves:** If conversation_id is omitted, automatically uses your most recent dynamic search.
    """
    resolved_conversation_id = _resolve_prompt_conversation_id(conversation_id)
    logger.debug("=" * 60)
    logger.debug("GET /api/results/dynamic/prompt called")
    logger.debug(f"   influencer_id: {influencer_id}")
    logger.debug(f"   requested conversation_id: {conversation_id}")
    logger.debug(f"   resolved conversation_id: {resolved_conversation_id}")
    logger.debug("=" * 60)

    dynamic_results = _load_prompt_dynamic_results(resolved_conversation_id)
    if not dynamic_results:
        logger.warning("No prompt dynamic results found for conversation %s", resolved_conversation_id)
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"No prompt dynamic search results found for conversation '{resolved_conversation_id}'",
                "message": "Run POST /api/dynamic-search/prompt (or prompt CSV upload) before requesting results.",
                "conversation_id": resolved_conversation_id,
            },
        )

    logger.debug("Found %d prompt dynamic results for conversation %s", len(dynamic_results), resolved_conversation_id)

    found_influencer: Optional[Dict[str, Any]] = None
    sample_ids: List[Dict[str, str]] = []

    for result in dynamic_results:
        generated_id = _compute_dynamic_result_id(result)
        if generated_id and len(sample_ids) < 5:
            display_name = str(
                result.get("NAME")
                or result.get("name")
                or result.get("PROFILE_NAME")
                or "Unknown"
            )
            sample_ids.append({"id": generated_id, "name": display_name})

        if generated_id == influencer_id:
            found_influencer = result
            logger.debug("Matched prompt dynamic influencer %s", influencer_id)
            break

    if not found_influencer:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Influencer with ID {influencer_id} not found in prompt dynamic search results",
                "message": "Ensure you are using the ID returned by the latest prompt search.",
                "conversation_id": resolved_conversation_id,
                "sample_valid_ids": sample_ids,
                "total_influencers": len(dynamic_results),
            },
        )

    profile_link = found_influencer.get("PROFILE_LINK") or found_influencer.get("profile_link", "")
    name = found_influencer.get("NAME") or found_influencer.get("name", "Unknown")

    existing_analysis = _find_existing_analysis_by_profile_link(profile_link, name, influencer_id)
    if existing_analysis:
        logger.debug("Returning cached analysis for %s", influencer_id)
        # Also cache this in session storage for faster future lookups
        try:
            session_data = temp_store.load_session(resolved_conversation_id)
            if session_data:
                if "computed_analyses" not in session_data:
                    session_data["computed_analyses"] = {}
                session_data["computed_analyses"][influencer_id] = existing_analysis
                temp_store.persist_session(resolved_conversation_id, session_data)
        except Exception as e:
            logger.debug("Failed to cache existing analysis in session: %s", e)
        return existing_analysis

    analysis_result = _analyze_dynamic_influencer(influencer_id, resolved_conversation_id, found_influencer)
    if analysis_result:
        logger.debug("On-demand analysis complete for %s", influencer_id)
        # Cache the analysis result in session storage
        try:
            session_data = temp_store.load_session(resolved_conversation_id)
            if session_data:
                if "computed_analyses" not in session_data:
                    session_data["computed_analyses"] = {}
                session_data["computed_analyses"][influencer_id] = analysis_result
                temp_store.persist_session(resolved_conversation_id, session_data)
                logger.debug("✅ Cached analysis result for %s in session", influencer_id)
        except Exception as e:
            logger.warning("Failed to cache analysis result in session: %s", e)
        return analysis_result

    # For dynamic prompt flows, skipping legacy analysis is expected (not an error)
    logger.debug("Skipping legacy dynamic analysis for influencer_id=%s (conversation %s)", influencer_id, resolved_conversation_id)

    # Check if we have cached computed data in session for this influencer
    session_data = temp_store.load_session(resolved_conversation_id)
    if session_data and "computed_analyses" in session_data:
        cached_analysis = session_data["computed_analyses"].get(influencer_id)
        if cached_analysis:
            logger.debug("Returning cached computed analysis for %s from session", influencer_id)
            return cached_analysis

    def parse_followers(value) -> int:
        if not value or str(value).upper() in {"N/A", "NA", "NONE", ""}:
            return 0
        if isinstance(value, (int, float)):
            return int(value)
        try:
            parsed = str(value).upper().replace(",", "").replace("+", "").strip()
            if not parsed or parsed in {"N/A", "NA", "NONE"}:
                return 0
            if "M" in parsed:
                return int(float(parsed.replace("M", "")) * 1_000_000)
            if "K" in parsed:
                return int(float(parsed.replace("K", "")) * 1_000)
            return int(float(parsed))
        except (ValueError, TypeError, AttributeError):
            return 0

    def parse_percentage(value) -> float:
        if value is None:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        try:
            parsed = str(value).replace("%", "").strip()
            if not parsed or parsed.upper() in {"N/A", "NA", "NONE"} or parsed == "-":
                return 0.0
            return float(parsed)
        except (ValueError, TypeError, AttributeError):
            return 0.0

    def parse_rate(value) -> float:
        if not value or str(value).upper() in {"N/A", "NA", "NONE", ""}:
            return 0.0
        if isinstance(value, (int, float)):
            return float(value)
        try:
            cleaned = (
                str(value)
                .replace("₹", "")
                .replace(",", "")
                .replace("RS", "")
                .replace("rs", "")
                .strip()
            )
            if not cleaned or cleaned.upper() in {"N/A", "NA", "NONE"}:
                return 0.0
            return float(cleaned)
        except (ValueError, TypeError, AttributeError):
            return 0.0

    followers_val = parse_followers(
        found_influencer.get("followers") or found_influencer.get("FOLLOWERS", 0)
    )
    following_val = parse_followers(
        found_influencer.get("following") or found_influencer.get("FOLLOWING", 0)
    )
    # BrightData posts: single source from app.services.legacy.brightdata
    from app.services.legacy.brightdata import get_posts_from_result, get_posts_count_from_result
    posts_list = get_posts_from_result(found_influencer)
    posts_val = get_posts_count_from_result(found_influencer)
    avg_likes_val = parse_followers(
        found_influencer.get("average_likes") or found_influencer.get("AVERAGE_LIKES", 0)
    )
    avg_comments_val = parse_followers(
        found_influencer.get("average_comments") or found_influencer.get("AVERAGE_COMMENTS", 0)
    )
    avg_views_val = parse_followers(
        found_influencer.get("average_views") or found_influencer.get("AVERAGE_VIEWS", 0)
    )
    engagement_rate_val = parse_percentage(found_influencer.get("engagement_rate", "0"))
    real_pct_val = parse_percentage(found_influencer.get("real_followers_percentage", "0"))
    suspicious_pct_val = parse_percentage(
        found_influencer.get("suspicious_followers_percentage", "0")
    )
    
    # Fallback: If suspicious is missing but real exists, calculate it
    if suspicious_pct_val <= 0 and real_pct_val > 0:
        suspicious_pct_val = 100.0 - real_pct_val
    
    rate_val = parse_rate(found_influencer.get("RATE", "N/A"))

    # Calculate derived values for metrics
    real_followers_count = (
        int(followers_val * (real_pct_val / 100.0))
        if followers_val > 0 and real_pct_val > 0
        else 0
    )
    suspicious_followers_count = (
        int(followers_val * (suspicious_pct_val / 100.0))
        if followers_val > 0 and suspicious_pct_val > 0
        else 0
    )

    try:
        from app.services.core.prompt_service import calculate_influencer_metrics

        # Use engagement_rate as-is (already in percentage format)
        temp_data = {
            "followers": followers_val,
            "following": following_val,
            "posts_count": posts_val,
            "posts": posts_val,  # count for metrics calc
            "average_likes": avg_likes_val,
            "avg_likes": avg_likes_val,
            "average_comments": avg_comments_val,
            "avg_comments": avg_comments_val,
            "average_views": avg_views_val,
            "avg_views": avg_views_val,
            "engagement_rate": engagement_rate_val,  # Use as-is, no normalization
            "real_followers_percentage": real_pct_val,
            "real_percentage": real_pct_val,
            "real_followers": real_followers_count,
            "suspicious_followers_percentage": suspicious_pct_val,
            "suspicious_fake_followers": suspicious_followers_count,
            "RATE": rate_val,
            "rate": rate_val,
            "is_verified": found_influencer.get("is_verified", False),
            "is_business_account": found_influencer.get("is_business_account", False),
            "is_professional_account": found_influencer.get("is_professional_account", False),
            "highlights_count": found_influencer.get("highlights_count", 0),
            "biography": found_influencer.get("biography", ""),
            "external_url": found_influencer.get("external_url", ""),
            "category_name": found_influencer.get("category_name", ""),
            "business_category_name": found_influencer.get("business_category_name", ""),
        }

        # Calculate comprehensive metrics
        calculated_metrics = calculate_influencer_metrics(temp_data)

        # Add chart-specific metric mappings for frontend compatibility
        calculated_metrics = _map_dynamic_metrics_for_charts(
            calculated_metrics,
            temp_data,
            found_influencer
        )
    except Exception as calc_exc:
        logger.warning("Failed to calculate fallback metrics: %s", calc_exc)
        calculated_metrics = {}

    # Extract profile picture URL using centralized utility
    from app.utils.image_utils import extract_profile_image
    username = found_influencer.get("Id") or found_influencer.get("username")
    profile_pic_url = extract_profile_image(found_influencer, username, "results_router")

    influencer_data = {
        "id": influencer_id,
        "name": name,
        "niche": found_influencer.get("NICHE", "Unknown"),
        "location": found_influencer.get("Location", "Unknown"),
        "profile_link": profile_link if profile_link else None,
        "profile_pic_url": profile_pic_url,  # Primary field
        "profile_picture_url": profile_pic_url,  # Alias
        "profile_image": profile_pic_url,  # Alias
        "image": profile_pic_url,  # Alias
        "followers": followers_val,
        "following": following_val,
        "posts_count": posts_val,
        "posts": posts_list,  # full list of post details from BrightData (id, caption, likes, comments, image_url, etc.)
        "average_likes": avg_likes_val,
        "avg_likes": avg_likes_val,
        "average_comments": avg_comments_val,
        "avg_comments": avg_comments_val,
        "average_views": avg_views_val,
        "avg_views": avg_views_val,
        "engagement_rate": engagement_rate_val,
        "real_followers_percentage": real_pct_val,
        "real_percentage": real_pct_val,
        "real_followers": real_followers_count,
        "suspicious_followers_percentage": suspicious_pct_val,
        "suspicious_fake_followers": suspicious_followers_count,
        "is_verified": found_influencer.get("is_verified", False),
        "is_business_account": found_influencer.get("is_business_account", False),
        "is_professional_account": found_influencer.get("is_professional_account", False),
        "is_joined_recently": found_influencer.get("is_joined_recently", False),
        "biography": found_influencer.get("biography", "N/A"),
        "external_url": found_influencer.get("external_url", "N/A"),
        "business_category_name": found_influencer.get("business_category_name", "N/A"),
        "category_name": found_influencer.get("category_name", "N/A"),
        "highlights_count": found_influencer.get("highlights_count", 0),
        "rate": rate_val,
        "RATE": rate_val,
        "source": found_influencer.get("source", "prompt_dynamic"),
        "checked_at": found_influencer.get("checked_at", None),
        "username": found_influencer.get("Id") or found_influencer.get("username"),
        "id_name": found_influencer.get("Id") or found_influencer.get("username"),
        "metrics": calculated_metrics,
        "raw_data": calculated_metrics,
        "post_analysis": found_influencer.get("post_analysis", {}),  # Include post analysis for AI insights
        "hashtag_analysis": found_influencer.get("hashtag_analysis", {}),  # Include hashtag analysis
        "top_hashtags": found_influencer.get("top_hashtags", []),  # Include top hashtags
    }

    response_data = {
        "influencer_id": influencer_id,
        "conversation_id": resolved_conversation_id,
        "influencer": influencer_data,
        "status": "prompt_dynamic_search",
        "data_source": "Prompt-based dynamic search (Spreadd + BrightData)",
        "message": "Prompt dynamic search results with fresh metrics",
    }

    # Cache the computed analysis in session storage for persistence across page refreshes
    try:
        session_data = temp_store.load_session(resolved_conversation_id)
        if session_data:
            # Initialize computed_analyses dict if not exists
            if "computed_analyses" not in session_data:
                session_data["computed_analyses"] = {}

            # Store this influencer's computed analysis
            session_data["computed_analyses"][influencer_id] = response_data

            # Persist back to storage
            temp_store.persist_session(resolved_conversation_id, session_data)
            logger.debug("✅ Cached computed analysis for %s in session", influencer_id)
    except Exception as e:
        logger.warning("Failed to cache computed analysis in session: %s", e)

    return response_data


async def get_all_prompt_results(
    conversation_id: str = Query(..., description="Conversation ID to fetch all results from"),
) -> Dict[str, Any]:
    """
    Get all results from a conversation including anchor and industry peers.
    This is used by the frontend to display the comparison header.
    
    Merges main results with industry standards results (from background task).
    """
    try:
        logger.debug(f"📥 Fetching all results for conversation: {conversation_id}")
        dynamic_results = _load_prompt_dynamic_results(conversation_id)
        
        # Also check for industry standards results (from background task)
        try:
            from app.services.analysis.industry_standards import get_industry_standards_status
            industry_status = get_industry_standards_status(conversation_id)
            
            if industry_status.get("status") == "completed" and industry_status.get("results"):
                industry_peers = industry_status.get("results", [])
                logger.debug(f"📦 Found {len(industry_peers)} industry peers from background task")
                
                # CRITICAL FIX: Get IDs of final filtered industry peers
                final_industry_peer_ids = {peer.get("id") or peer.get("Id") for peer in industry_peers if peer.get("id") or peer.get("Id")}
                
                # Merge industry peers with main results
                if dynamic_results:
                    # Tag the first result as anchor if not already tagged
                    if not any(r.get("industry_anchor") is True for r in dynamic_results):
                        dynamic_results[0]["industry_anchor"] = True
                    
                    # CRITICAL FIX: Remove industry_standard tag from peers that didn't pass final filtering
                    for result in dynamic_results:
                        result_id = result.get("id") or result.get("Id")
                        if result.get("industry_standard") is True and result_id not in final_industry_peer_ids:
                            # This peer was filtered out - remove the tag
                            result["industry_standard"] = False
                            logger.debug(f"   🗑️ Removed industry_standard tag from filtered peer: {result.get('NAME') or result.get('name')}")
                    
                    # Add final industry peers (avoid duplicates by ID)
                    existing_ids = {r.get("id") or r.get("Id") for r in dynamic_results if r.get("id") or r.get("Id")}
                    for peer in industry_peers:
                        peer_id = peer.get("id") or peer.get("Id")
                        if peer_id and peer_id not in existing_ids:
                            dynamic_results.append(peer)
                            existing_ids.add(peer_id)
                            logger.debug(f"✅ Added industry peer: {peer.get('NAME') or peer.get('name')}")
                else:
                    # No main results, but we have peers - use peers as results
                    dynamic_results = industry_peers
                    logger.debug("⚠️ No main results, using industry peers only")
        except Exception as e:
            logger.warning(f"⚠️ Failed to load industry standards: {e}")
            # Continue with main results only
        
        if not dynamic_results:
            logger.warning(f"⚠️ No results found for conversation: {conversation_id}")
            return {"results": []}
        
        # CRITICAL FIX: Filter out peers with 0 followers or invalid data
        # Only return peers that are actually industry standards with valid data
        filtered_results = []
        for result in dynamic_results:
            # Always include anchors
            if result.get("industry_anchor") is True:
                filtered_results.append(result)
            # Only include industry peers with valid follower data
            elif result.get("industry_standard") is True:
                followers = result.get("followers", "0")
                # Check if followers is a valid number (not 0, not "0", not "N/A")
                followers_str = str(followers).strip().upper()
                if followers_str not in ("0", "N/A", "NAN", "NULL", "NONE", "") and followers_str != "0":
                    # Parse to check if it's actually a valid number
                    try:
                        # Remove K/M suffixes for validation
                        clean_followers = followers_str.replace("K", "").replace("M", "").replace(",", "")
                        if float(clean_followers) > 0:
                            filtered_results.append(result)
                        else:
                            logger.debug(f"   🗑️ Filtered out peer with 0 followers: {result.get('NAME') or result.get('name')}")
                    except (ValueError, TypeError):
                        # If it's a formatted string like "45.62M", it's valid
                        if any(suffix in followers_str for suffix in ["K", "M", "B"]):
                            filtered_results.append(result)
                        else:
                            logger.debug(f"   🗑️ Filtered out peer with invalid followers: {result.get('NAME') or result.get('name')}")
                else:
                    logger.debug(f"   🗑️ Filtered out peer with 0/N/A followers: {result.get('NAME') or result.get('name')}")
            else:
                # Include non-industry results (if any)
                filtered_results.append(result)
        
        # Log what we're returning
        anchor_count = sum(1 for r in filtered_results if r.get("industry_anchor") is True)
        peer_count = sum(1 for r in filtered_results if r.get("industry_standard") is True)
        logger.debug(f"✅ Returning {len(filtered_results)} results: {anchor_count} anchor(s), {peer_count} peer(s) (filtered from {len(dynamic_results)} total)")
        
        return {"results": filtered_results}
    except Exception as e:
        logger.error(f"❌ Error fetching all results for conversation {conversation_id}: {e}")
        import traceback
        logger.debug(traceback.format_exc())
        raise HTTPException(status_code=500, detail=client_safe_500_message(e))


async def get_industry_standards_analysis(conversation_id: str) -> Dict[str, Any]:
    """
    Get industry standards processing status and results for a search.
    
    This endpoint returns the status of background industry standards processing.
    Industry standards are only generated for specific person searches (e.g., Instagram URLs).
    
    **Response Status:**
    - `"processing"`: Industry standards are being discovered and enriched
    - `"completed"`: Industry standards are ready (results may be empty if no peers found)
    - `"error"`: Processing failed (error message included)
    - `"not_found"`: No industry standards processing was triggered for this search
    
    **Response Format:**
    ```json
    {
        "conversation_id": "prompt_123",
        "status": "completed",
        "count": 2,
        "results": [
            {
                "Id": "msdhoni",
                "NAME": "MS Dhoni",
                "industry_standard": true,
                "industry_profession": "Professional Cricketer",
                "industry_reference_for": "virat.kohli",
                "followers": "50M",
                ...
            }
        ],
        "error": null
    }
    ```
    
    **Usage:**
    - Call this endpoint after a search completes
    - Poll until status is "completed" or "error"
    - When status is "completed":
      - If `count > 0`: Display industry standards alongside anchor
      - If `count == 0`: Show anchor only (no peers found that meet criteria)
    - Industry standards are stored separately from main search results
    - Frontend should merge: [anchor] + [industry_standards] for display
    
    **Note:** The anchor influencer is always in the main search results.
    This endpoint only returns the industry standard peers.
    """
    try:
        from app.services.analysis.industry_standards import get_industry_standards_status
        
        status_data = get_industry_standards_status(conversation_id)
        
        return {
            "conversation_id": conversation_id,
            "status": status_data.get("status", "not_found"),
            "count": status_data.get("count", 0),
            "results": status_data.get("results", []),
            "error": status_data.get("error"),
            "industry_comparison": status_data.get("industry_comparison", {
                "status": "not_found",
                "reason": "No industry standards processing found"
            })
        }
    except Exception as e:
        logger.error(f"Failed to get industry standards analysis: {e}")
        raise HTTPException(
            status_code=500,
            detail=client_safe_500_message(e)
        )


async def get_profession_peers_status_endpoint(conversation_id: str = Query(...)) -> Dict[str, Any]:
    """
    Get profession peers discovery status (for frontend polling).
    Used for TOP INFLUENCER searches where profession peers are discovered in background.
    
    Returns: {"status": "processing"|"completed", "results": [...]}
    """
    try:
        from app.services.analysis.industry_standards import get_profession_peers_status
        return get_profession_peers_status(conversation_id)
    except Exception as e:
        logger.error(f"Failed to get profession peers status: {e}")
        raise HTTPException(status_code=500, detail=client_safe_500_message(e))



async def generate_industry_comparison_insights(
    request: Dict[str, Any] = Body(...)
) -> Dict[str, Any]:
    """
    Generate professional AI insights for industry standard comparison using Gemini.
    
    Request body:
        {
            "anchor": {...},  # The main influencer being compared (industry_anchor = true)
            "peers": [...]    # List of industry standard peers (industry_standard = true)
        }
    
    Returns:
        {
            "insights": ["insight1", "insight2", ...],
            "summary": "Overall comparison summary"
        }
    """
    try:
        from app.services.llm.agent_service import call_openai_api
        import json
        
        if not isinstance(request, dict):
            raise HTTPException(status_code=400, detail="Request body must be a JSON object")
        
        anchor = request.get("anchor", {})
        peers = request.get("peers", [])
        
        if not anchor:
            raise HTTPException(status_code=400, detail="Missing 'anchor' in request body")
        if not isinstance(peers, list):
            raise HTTPException(status_code=400, detail="'peers' must be a list")
        
        # Prepare comparison data
        anchor_name = anchor.get("NAME") or anchor.get("name") or anchor.get("Id") or "Unknown"
        anchor_followers = anchor.get("followers", 0)
        anchor_engagement = anchor.get("engagement_rate", 0)
        anchor_authenticity = anchor.get("real_percentage") or anchor.get("real_followers_percentage", 0)
        
        peers_data = []
        for peer in peers[:3]:  # Max 3 peers
            peer_name = peer.get("NAME") or peer.get("name") or peer.get("Id") or "Unknown"
            peers_data.append({
                "name": peer_name,
                "followers": peer.get("followers", 0),
                "engagement_rate": peer.get("engagement_rate", 0),
                "authenticity": peer.get("real_percentage") or peer.get("real_followers_percentage", 0)
            })
        
        # Create comprehensive prompt for Gemini focused on COMPARISON RESULTS
        prompt = f"""You are an expert influencer marketing analyst. Analyze the following industry standard comparison and generate professional, COMPARISON-FOCUSED insights that directly compare the anchor influencer against industry peers.

ANCHOR INFLUENCER (Main Subject):
- Name: {anchor_name}
- Followers: {anchor_followers}
- Engagement Rate: {anchor_engagement}%
- Authenticity: {anchor_authenticity}%

INDUSTRY PEERS (Benchmarks):
{chr(10).join([f"- {p['name']}: {p['followers']} followers, {p['engagement_rate']}% engagement, {p['authenticity']}% authenticity" for p in peers_data])}

CRITICAL: Generate 4-6 professional, COMPARISON-FOCUSED insights that:
1. DIRECTLY COMPARE the anchor's metrics against each peer (e.g., "The anchor ranks X in followers compared to peers, indicating...")
2. HIGHLIGHT SPECIFIC COMPETITIVE POSITIONING (e.g., "While Peer A leads in followers, the anchor outperforms in engagement rate by...")
3. IDENTIFY RELATIVE STRENGTHS AND WEAKNESSES compared to benchmarks (e.g., "The anchor's authenticity score is higher/lower than industry average, suggesting...")
4. PROVIDE COMPARATIVE ANALYSIS (e.g., "Compared to the top peer, the anchor shows...")
5. FOCUS ON RANKING AND POSITIONING within the group (e.g., "Among the three influencers, the anchor positions as...")

Format as a JSON object with:
{{
  "insights": ["comparison insight1", "comparison insight2", "comparison insight3", "comparison insight4", "comparison insight5", "comparison insight6"],
  "summary": "One comprehensive paragraph summarizing the DIRECT COMPARISON results and competitive positioning relative to industry peers"
}}

Each insight MUST:
- Start with a direct comparison statement (e.g., "Compared to...", "Relative to peers...", "Among the group...")
- Reference specific peers or rankings when relevant
- Highlight where the anchor stands in relation to benchmarks
- Be professional and business-focused
- Be actionable for brand partnership decisions
- Be qualitative (describe comparisons, not repeat exact numbers)
- Be 1-2 sentences maximum
- Focus on COMPARATIVE positioning and strategic value

The summary should emphasize the COMPARATIVE ANALYSIS and how the anchor positions relative to industry standards.

Return ONLY valid JSON, no additional text."""
        
        logger.info(f"🤖 Generating OpenAI insights for industry comparison: {anchor_name} vs {len(peers_data)} peers")
        
        try:
            messages = [{"role": "user", "content": prompt}]
            response = call_openai_api(
                messages=messages,
                model=None,
                temperature=0.3,
                max_tokens=2000,
                response_format={"type": "json_object"}
            )
            
            if "choices" in response and len(response["choices"]) > 0:
                response_text = response["choices"][0]["message"]["content"]
            else:
                raise ValueError("Empty response from OpenAI")
        except Exception as openai_error:
            logger.error(f"OpenAI API call failed: {openai_error}")
            logger.warning("Using fallback insights due to OpenAI API failure")
            return {
                "insights": [
                    f"{anchor_name} demonstrates competitive positioning within the industry benchmark group.",
                    "Comparative analysis reveals strategic opportunities for brand partnership alignment.",
                    "Industry standard metrics indicate strong potential for targeted marketing campaigns.",
                    "Performance metrics suggest alignment with industry best practices for influencer partnerships.",
                    "Competitive positioning indicates readiness for strategic brand collaborations."
                ],
                "summary": f"{anchor_name} shows competitive positioning within the industry benchmark group, with metrics indicating strong potential for strategic brand partnerships and campaign alignment."
            }
        
        # Parse response
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError as json_error:
            logger.error(f"Failed to parse OpenAI JSON response: {json_error}")
            logger.error(f"Response text (first 500 chars): {response_text[:500] if response_text else 'N/A'}")
            # Try to extract JSON from response if it's wrapped in markdown
            import re
            json_match = re.search(r'\{[^{}]*"insights"[^{}]*\}', response_text, re.DOTALL)
            if json_match:
                try:
                    result = json.loads(json_match.group())
                except:
                    raise json_error
            else:
                raise json_error
        
        raw_insights = result.get("insights", [])
        raw_summary = result.get("summary", "")
        
        # Normalize insights to ensure they're always strings
        insights = []
        for item in raw_insights:
            if isinstance(item, str):
                insights.append(item)
            elif isinstance(item, dict):
                # Handle object format like {"insight": "text"} or {"text": "..."}
                if "insight" in item:
                    insights.append(str(item["insight"]))
                elif "text" in item:
                    insights.append(str(item["text"]))
                else:
                    # Try to get first string value
                    for key, value in item.items():
                        if isinstance(value, str):
                            insights.append(value)
                            break
            else:
                insights.append(str(item))
        
        # Normalize summary to string
        summary = str(raw_summary) if raw_summary else ""
        
        if not insights or len(insights) < 3:
            logger.warning("OpenAI returned insufficient insights, using fallback")
            insights = [
                f"{anchor_name} demonstrates competitive positioning within the industry benchmark group.",
                "Comparative analysis reveals strategic opportunities for brand partnership alignment.",
                "Industry standard metrics indicate strong potential for targeted marketing campaigns.",
                "Performance metrics suggest alignment with industry best practices for influencer partnerships.",
                "Competitive positioning indicates readiness for strategic brand collaborations."
            ]
            if not summary:
                summary = f"{anchor_name} shows competitive positioning within the industry benchmark group, with metrics indicating strong potential for strategic brand partnerships."
        
        logger.debug(f"✅ Generated {len(insights)} OpenAI insights for industry comparison")
        
        return {
            "insights": insights[:6],  # Max 6 insights
            "summary": summary
        }
        
    except HTTPException:
        raise
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse response as JSON: {e}")
        raise HTTPException(
            status_code=500,
            detail=client_safe_500_message(e)
        )
    except Exception as e:
        logger.exception(f"Failed to generate industry comparison insights: {e}")
        raise HTTPException(
            status_code=500,
            detail=client_safe_500_message(e)
        )


async def test_ai_insight():
    """
    **Step 5: Test your OpenAI AI configuration**

    Use this endpoint to verify your AI insight feature is properly configured.

    **What it checks:**
        - OPENAI_API_KEY is set in .env
        - OPENAI_MODEL is configured
    - API connectivity works

    **Returns:**
    - Success: Configuration is valid and API is accessible
    - Error: Details about what needs to be fixed

    **Optional:** Only needed if you want to use AI-generated insights.
    """
    try:
        from app.config.settings import settings
        import httpx

        # Check if API key is set
        if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "your_openai_api_key":
            return {
                "success": False,
                "error": "OPENAI_API_KEY not configured",
                "help": "Please set OPENAI_API_KEY in your .env file. Get a key from https://platform.openai.com/api-keys"
            }

        if not settings.OPENAI_MODEL or settings.OPENAI_MODEL == "gpt-model":
            return {
                "success": False,
                "error": "OPENAI_MODEL not configured",
                "help": "Please set OPENAI_MODEL in your .env file (e.g., 'gpt-4o-mini')"
            }

        # Test API connection with a simple request
        from openai import OpenAI
        try:
            client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[{"role": "user", "content": "Say hello"}],
                max_tokens=10,
            )
            return {
                "success": True,
                "message": "OpenAI API is configured correctly",
                "model": settings.OPENAI_MODEL
            }
        except Exception as e:
            return {
                "success": False,
                "error": f"OpenAI API test failed: {str(e)}",
                "help": "Check your OPENAI_API_KEY and OPENAI_MODEL configuration"
            }

    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "help": "Check your .env file and ensure OPENAI_API_KEY and OPENAI_MODEL are set correctly"
        }


async def generate_ai_insight(
    influencer_data: Dict[str, Any]
):
    """
    **Step 6: Generate AI-powered professional insights for an influencer**

    Uses OpenRouter LLM to generate comprehensive, human-readable analysis of an influencer's performance.

    **What it analyzes:**
    - Follower count and growth potential
    - Engagement rate effectiveness
    - Audience authenticity (real vs fake followers)
    - Content performance metrics
    - Niche relevance and positioning
    - Recommendations for brand partnerships

    **Request Body:**
    ```json
    {
      "name": "Influencer Name",
      "followers": 100000,
      "engagement_rate": 4.5,
      "real_followers_percentage": 85,
      "avg_likes": 5000,
      "avg_comments": 200,
      "niche": "Fashion",
      ...
    }
    ```

    **Returns:**
    - Professional AI-generated analysis
    - Partnership recommendations
    - Performance insights
    - Risk assessment

    **Requires:** OPENAI_API_KEY and OPENAI_MODEL in .env
    """
    try:
        from app.config.settings import settings
        import httpx

        # Validate configuration
        if not settings.OPENAI_API_KEY or settings.OPENAI_API_KEY == "your_openai_api_key":
            raise HTTPException(
                status_code=500,
                detail="OpenAI API key not configured. Please check your .env file."
            )

        if not settings.OPENAI_MODEL or settings.OPENAI_MODEL == "gpt-model":
            raise HTTPException(
                status_code=500,
                detail="OpenAI model not configured. Please check your .env file."
            )
        
        # Extract key metrics
        name = influencer_data.get("name", "Unknown")
        followers = influencer_data.get("followers", 0)
        engagement_rate = influencer_data.get("engagement_rate", 0)
        real_percentage = influencer_data.get("real_percentage", influencer_data.get("real_followers_percentage", 0))
        avg_likes = influencer_data.get("avg_likes", influencer_data.get("average_likes", 0))
        avg_comments = influencer_data.get("avg_comments", influencer_data.get("average_comments", 0))
        niche = influencer_data.get("niche", "Unknown")
        location = influencer_data.get("location", "Unknown")

        # Get metrics if available
        metrics = influencer_data.get("metrics", {})
        quality_score = metrics.get("influencer_quality_score", "N/A")
        health_score = metrics.get("health_score", "N/A")

        # Get post analysis if available
        post_analysis = influencer_data.get("post_analysis", {})
        has_post_analysis = post_analysis.get("post_analysis_available", False)
        content_strategy = post_analysis.get("content_strategy_summary", "") if has_post_analysis else ""
        posting_patterns = post_analysis.get("posting_patterns_summary", "") if has_post_analysis else ""

        # Get hashtag analysis if available
        hashtag_analysis = influencer_data.get("hashtag_analysis", {})
        top_hashtags = influencer_data.get("top_hashtags", [])
        has_hashtags = len(top_hashtags) > 0
        
        # Construct prompt for LLM - Concise bullet points format
        post_data_section = ""
        if has_post_analysis:
            post_data_section = f"""
Content Strategy: {content_strategy}
Posting Patterns: {posting_patterns}"""

        hashtag_section = ""
        if has_hashtags:
            hashtag_list = ", ".join(top_hashtags[:5])
            hashtag_section = f"\nTop Hashtags: {hashtag_list}"

        prompt = f"""Analyze this influencer and provide CONCISE bullet-point insights in 4 sections. Keep each section to 2-3 SHORT points maximum.

DATA:
Name: {name}
Followers: {followers:,}
Engagement: {engagement_rate}%
Authentic: {real_percentage}%
Avg Likes: {avg_likes:,}
Avg Comments: {avg_comments:,}
Quality: {quality_score}
Health: {health_score}{post_data_section}{hashtag_section}

OUTPUT FORMAT (SHORT bullet points only):

📊 Performance Highlights:
• {engagement_rate}% engagement with {followers:,} followers
• {real_percentage}% authentic audience
• [One more key insight]

✅ Key Strengths:
• {avg_likes:,} avg likes, {avg_comments:,} avg comments
• [One strength]
• [One strength]

⚠️ Considerations:
• [Main concern OR "Strong overall metrics"]
• [Secondary point if relevant]

🎯 Recommendation:
• [Highly Recommended/Recommended/Consider Carefully] based on [key metric]
• [One supporting reason]"""

        # Call OpenAI API
        from openai import OpenAI
        try:
            openai_client = OpenAI(api_key=settings.OPENAI_API_KEY)
            response = openai_client.chat.completions.create(
                model=settings.OPENAI_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": prompt
                    }
                ],
                temperature=0.7,
                max_tokens=500,
            )

            logger.info(f"OpenAI API response received")

            # Get insight from response
            insight = response.choices[0].message.content.strip()

            if not insight:
                logger.error(f"Empty content in response")
                raise HTTPException(
                    status_code=500,
                    detail="AI model returned empty response"
                )

            return {
                "success": True,
                "insight": insight,
                "influencer_name": name
            }

        except Exception as e:
            logger.error(f"OpenAI API request error: {e}")
            raise HTTPException(
                status_code=503,
                detail=client_safe_500_message(e)
            )
    
    except ImportError as e:
        logger.error(f"Missing dependency: {e}")
        raise HTTPException(
            status_code=500,
            detail="Server configuration error"
        )
    except Exception as e:
        logger.error(f"AI insight generation failed: {e}")
        raise HTTPException(
            status_code=500,
            detail=client_safe_500_message(e)
        )
