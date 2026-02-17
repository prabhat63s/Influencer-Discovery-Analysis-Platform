"""
Image Utilities Module
======================
Centralized functions for handling profile images across all scrapers.

This ensures consistent profile image extraction from various sources:
- BrightData API
- Spreadd API
- SerpAPI
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

logger = logging.getLogger(__name__)


def extract_profile_image(
    data: Dict,
    username: Optional[str] = None,
    source: str = "unknown"
) -> str:
    """
    Extract profile image URL from various data sources.

    Priority order:
    1. BrightData fields (profile_image_link, profile_image_url, profile_picture_url)
    2. Spreadd/SerpAPI fields (profile_pic_url, profile_image, image, avatar)
    3. Existing fields from previous scrapers

    Args:
        data: Dictionary containing influencer data
        username: Instagram username (not used, kept for compatibility)
        source: Data source name for logging

    Returns:
        Profile image URL string or None if not found
    """
    # Try all possible profile image field names (prioritized by reliability)
    profile_image_fields = [
        # BrightData field (HIGHEST PRIORITY - actual Instagram CDN URL)
        'profile_image_link',  # ⭐ This is what BrightData returns

        # Already processed fields (from other scrapers)
        'profile_pic_url',
        'profile_image',
        'image',

        # Fallback alternatives (less common)
        'profile_image_url',
        'profile_picture_url',
        'profile_pic',
        'avatar',
        'avatar_url',
        'picture',
        'photo_url',
    ]

    for field in profile_image_fields:
        if field in data and data[field]:
            image_url = str(data[field]).strip()
            if image_url and image_url != "N/A" and image_url != "null":
                # REJECT unavatar.io URLs completely - do not use this service
                if 'unavatar.io' in image_url.lower():
                    logger.debug(f"Rejected unavatar.io URL from '{field}' in {source}: {image_url[:100]}")
                    continue  # Skip this URL and try next field
                logger.debug(f"Found profile image in '{field}' from {source}: {image_url[:100]}")
                return image_url

    # No profile image found
    logger.debug(f"No profile image found for influencer from {source}, returning None")
    return None


def normalize_profile_image_fields(data: Dict, username: Optional[str] = None, source: str = "unknown") -> Dict:
    """
    Normalize profile image fields in influencer data.

    Ensures consistent field names across all scrapers:
    - profile_pic_url (primary field)
    - profile_image (secondary)
    - image (tertiary)

    Args:
        data: Dictionary containing influencer data
        username: Instagram username for fallback
        source: Data source name for logging

    Returns:
        Updated dictionary with normalized profile image fields
    """
    profile_image_url = extract_profile_image(data, username, source)

    # Set all standard profile image field names
    data["profile_pic_url"] = profile_image_url
    data["profile_image"] = profile_image_url
    data["image"] = profile_image_url

    return data


def extract_username_from_profile_url(url: Optional[str]) -> Optional[str]:
    """
    Extract Instagram username from profile URL.

    Args:
        url: Instagram profile URL

    Returns:
        Username string or None
    """
    if not url:
        return None

    import re

    url = str(url).strip().lower()

    # Filter out non-profile URLs
    invalid_patterns = ['/p/', '/reel/', '/tv/', '/stories/', '/explore/', '/accounts/', '/direct/']
    for pattern in invalid_patterns:
        if pattern in url:
            return None

    # Extract username
    match = re.search(r"instagram\.com/([a-zA-Z0-9._]+)/?(?:\?|$)", url)
    if match:
        username = match.group(1).strip().lstrip("@")
        if 1 <= len(username) <= 30 and re.match(r'^[a-zA-Z0-9._]+$', username):
            return username

    return None
