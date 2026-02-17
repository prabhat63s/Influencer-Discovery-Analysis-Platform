from typing import Dict, List, Any

# ============================================================================
# METRIC CONSTANTS & DEFINITIONS
# ============================================================================

# Canonical metric names and their aliases
METRIC_ALIASES = {
    # Engagement
    "engagement_rate": ["engagement_rate"],
    "average_likes": ["average_likes", "avg_likes"],
    "average_comments": ["average_comments", "avg_comments"],
    
    # Authenticity
    "real_percentage": ["real_followers_percentage", "real_percentage", "real_follower_ratio", "real_pct"],
    "fake_percentage": ["fake_percentage", "fake_follower_ratio", "suspicious_followers_percentage", "suspicious_pct"],
    
    # Profile
    "followers": ["followers"],
    "following": ["following"],
    "posts": ["posts", "posts_count"],
    "is_verified": ["is_verified"],
}

# Metrics that should be shown as percentages (0-100)
PERCENTAGE_METRICS = {"engagement_rate", "real_percentage", "fake_percentage"}

# Metrics that need normalization (multiply by 100 if <= 1)
NEEDS_NORMALIZATION = {"real_percentage", "fake_percentage"}

def normalize_metric_value(key: str, value: float) -> float:
    """Normalize a metric value once, at ingestion time."""
    if key in NEEDS_NORMALIZATION and 0 < value <= 1:
        return value * 100
    return value

def get_canonical_name(alias: str) -> str:
    """Get the canonical name for any metric alias."""
    alias_lower = alias.lower()
    for canonical, aliases in METRIC_ALIASES.items():
        if alias_lower in [a.lower() for a in aliases]:
            return canonical
    return alias

# ============================================================================
# VISUAL DESIGN & COLOR PALETTE
# ============================================================================

# Natural, Vibrant Color Palette - Inspired by Nature
COLORS = {
    'primary': '#1E40AF',      # Deep Royal Blue (more saturated, professional)
    'secondary': '#7C3AED',    # Rich Purple (vivid, not pastel)
    'accent1': '#059669',      # Deep Emerald (saturated green)
    'accent2': '#D97706',      # Rich Amber (warm, not pale yellow)
    'accent3': '#047857',      # Forest Green (deep, natural)
    'accent4': '#2563EB',      # Vibrant Blue (bright but not pale)
    'accent5': '#DB2777',      # Bold Pink (saturated)
    'accent6': '#6D28D9',      # Deep Violet (rich purple)
    'accent7': '#EA580C',      # Burnt Orange (warm, saturated)
    'accent8': '#0D9488',      # Deep Teal (rich cyan)
    'text_dark': '#111827',    # Darker Gray (higher contrast)
    'text_light': '#4B5563',   # Medium Gray (readable)
    'white': '#FFFFFF',
    'background': '#F9FAFB',   # Light Background
    'grid': '#D1D5DB',         # Slightly darker grid for visibility
    # Semantic Colors
    'success': '#10B981',      # Emerald Green
    'warning': '#F59E0B',      # Amber
    'danger': '#EF4444',       # Red
    'info': '#3B82F6',         # Blue
    'accent': '#059669',       # Alias for accent1 (Deep Emerald)
}

# Extended color sequence for charts
COLOR_SEQUENCE = [
    COLORS['primary'], COLORS['secondary'], COLORS['accent1'],
    COLORS['accent2'], COLORS['accent4'], COLORS['accent5'],
    COLORS['accent6'], COLORS['accent7'], COLORS['accent8'], COLORS['accent3']
]
