"""
BrightData – single source for all BrightData-related data and helpers.

Import this module wherever you need:
- BrightData post field names (BRIGHTDATA_POST_FIELDS)
- Normalized posts from raw BrightData response (normalize_posts_for_display)
- Posts list or count from any result dict that may contain BrightData payload
  (get_posts_from_result, get_posts_count_from_result)
- Extracting posts + count from raw BrightData profile dict (extract_posts_and_count)

Usage:
  from app.services.legacy.brightdata import (
      BRIGHTDATA_POST_FIELDS,
      normalize_posts_for_display,
      get_posts_from_result,
      get_posts_count_from_result,
      extract_posts_and_count,
  )
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Tuple

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# BrightData schema (matches BrightData API / sd_ml93ir7ph1j7ag6fy.json)
# ---------------------------------------------------------------------------

BRIGHTDATA_POST_FIELDS = (
    "id",
    "caption",
    "comments",
    "datetime",
    "image_url",
    "likes",
    "content_type",
    "url",
    "video_url",
    "is_pinned",
    "post_hashtags",
)

def _parse_posts_count(value: Any) -> int:
    """Parse posts_count from BrightData (int, float, or string like '1.2K', '10M', 'N/A')."""
    if value is None or value == "" or str(value).upper() in ("N/A", "NA", "NONE"):
        return 0
    if isinstance(value, (int, float)):
        return int(value)
    try:
        s = str(value).strip().upper().replace(",", "").replace("+", "")
        if not s or s in ("N/A", "NA", "NONE"):
            return 0
        if "M" in s:
            return int(float(s.replace("M", "")) * 1_000_000)
        if "K" in s:
            return int(float(s.replace("K", "")) * 1_000)
        return int(float(s))
    except (ValueError, TypeError, AttributeError):
        return 0


def normalize_posts_for_display(posts: List[Dict]) -> List[Dict[str, Any]]:
    """
    Normalize raw BrightData post items using BrightData's variable names directly.
    Field names match BrightData API (e.g. sd_ml93ir7ph1j7ag6fy.json).
    We also output "permalink" as an alias for "url".
    """
    if posts is None or not posts:
        return []
    out = []
    for post in posts:
        if not post or not isinstance(post, dict):
            continue
        image_url = (
            post.get("image_url")
            or post.get("display_url")
            or post.get("thumbnail_src")
            or post.get("thumbnail")
            or None
        )
        if isinstance(image_url, list):
            image_url = image_url[0] if image_url else None
        caption = post.get("caption") or post.get("caption_text") or ""
        if isinstance(caption, list):
            caption = (caption[0] or "") if caption else ""
        likes_val = post.get("likes")
        if likes_val is None:
            likes_val = 0
        elif isinstance(likes_val, str):
            try:
                likes_val = int(float(likes_val.replace(",", "").replace("+", "").strip() or 0))
            except (ValueError, TypeError):
                likes_val = 0
        comments_val = post.get("comments")
        if comments_val is None:
            comments_val = 0
        elif isinstance(comments_val, str):
            try:
                comments_val = int(float(comments_val.replace(",", "").replace("+", "").strip() or 0))
            except (ValueError, TypeError):
                comments_val = 0
        hashtags = post.get("post_hashtags") or post.get("hashtags") or []
        if isinstance(hashtags, str):
            hashtags = [hashtags] if hashtags else []
        url_val = post.get("url") or post.get("permalink") or post.get("link") or None
        datetime_val = post.get("datetime") or post.get("date") or post.get("timestamp") or post.get("created_at")
        if datetime_val and not isinstance(datetime_val, str) and isinstance(datetime_val, (int, float)):
            try:
                from datetime import datetime as dt
                datetime_val = dt.utcfromtimestamp(datetime_val).isoformat() + "Z" if datetime_val else None
            except (ValueError, OSError, TypeError):
                datetime_val = str(datetime_val) if datetime_val else None
        post_id = post.get("id")
        video_url = post.get("video_url")
        is_pinned = post.get("is_pinned")
        if is_pinned is None:
            is_pinned = False
        out.append({
            "id": post_id,
            "caption": caption[:500] if caption else "",
            "comments": int(comments_val),
            "datetime": datetime_val,
            "image_url": image_url,
            "likes": int(likes_val),
            "content_type": post.get("content_type") or post.get("type") or "post",
            "url": url_val,
            "permalink": url_val,
            "video_url": video_url,
            "is_pinned": bool(is_pinned),
            "post_hashtags": hashtags,
        })
    return out


def get_posts_from_result(result: Dict[str, Any], *, normalize: bool = True) -> List[Dict[str, Any]]:
    """
    Get the posts list from any result dict (e.g. merged BrightData result or API response).
    Returns normalized posts by default; set normalize=False to return raw list.
    """
    raw = result.get("posts")
    if not isinstance(raw, list):
        return []
    if not normalize:
        return raw
    return normalize_posts_for_display(raw)


def get_posts_count_from_result(result: Dict[str, Any]) -> int:
    """
    Get numeric posts count from any result dict. Prefers posts_count/POSTS_COUNT;
    if missing, uses len(posts) when posts is a list.
    """
    raw_count = result.get("posts_count") or result.get("POSTS_COUNT")
    if raw_count is not None and raw_count != "" and not isinstance(raw_count, list):
        return _parse_posts_count(raw_count)
    posts = result.get("posts")
    if isinstance(posts, list) and posts:
        return len(posts)
    return 0


def extract_posts_and_count(brightdata_raw: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], Any]:
    """
    Extract normalized posts list and posts_count from a raw BrightData profile object.
    Returns (normalized_posts_list, posts_count_value).
    posts_count_value may be int or 'N/A' for downstream formatting.
    """
    posts_data = brightdata_raw.get("posts") or []
    if not isinstance(posts_data, list):
        posts_data = []
    normalized = normalize_posts_for_display(posts_data)
    posts_count_val = brightdata_raw.get("posts_count")
    if posts_count_val is None or posts_count_val == "N/A":
        posts_count_val = len(posts_data) if posts_data else "N/A"
    else:
        try:
            if isinstance(posts_count_val, (int, float)):
                posts_count_val = int(posts_count_val)
            elif isinstance(posts_count_val, str):
                s = posts_count_val.strip().replace(",", "").replace("+", "")
                if not s or s.upper() == "N/A":
                    posts_count_val = len(posts_data) if posts_data else "N/A"
                else:
                    posts_count_val = _parse_posts_count(posts_count_val)
            else:
                posts_count_val = len(posts_data) if posts_data else "N/A"
        except (TypeError, ValueError):
            posts_count_val = len(posts_data) if posts_data else "N/A"
    return (normalized, posts_count_val)
