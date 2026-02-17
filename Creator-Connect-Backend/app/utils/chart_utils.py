from pathlib import Path

import uuid
from typing import Any, Dict, List, Tuple, Optional
import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import matplotlib.patheffects as path_effects
# Removed 3D imports - using 2D charts only
from matplotlib.patches import FancyBboxPatch, Circle
import pandas as pd
import logging

matplotlib.use("Agg")

logger = logging.getLogger(__name__)

from app.utils.metric_constants import COLORS, COLOR_SEQUENCE

_CHARTS_DIR = Path("/tmp/creatos_reports/charts")
_CHARTS_DIR.mkdir(parents=True, exist_ok=True)

def _safe_filename(text: str) -> str:
    return "".join(c if c.isalnum() else "_" for c in (text or "chart"))[:80]

def _parse_numeric_value(value: Any, default: float = 0.0) -> float:
    """
    Parse numeric value from string with K/M suffix support.
    Handles: "3.1K", "1.2M", "1,234", "1234", 1234, etc.
    """
    if value is None:
        return default

    if isinstance(value, (int, float)):
        return float(value) if not np.isnan(value) else default

    if not isinstance(value, str):
        return default

    # Clean and normalize
    value_str = str(value).strip().upper().replace(',', '').replace('%', '')

    if not value_str or value_str in ('N/A', 'NAN', 'NONE', ''):
        return default

    try:
        # Handle K/M suffix
        multiplier = 1
        if value_str.endswith('K'):
            multiplier = 1_000
            value_str = value_str[:-1]
        elif value_str.endswith('M'):
            multiplier = 1_000_000
            value_str = value_str[:-1]
        elif value_str.endswith('B'):
            multiplier = 1_000_000_000
            value_str = value_str[:-1]

        parsed = float(value_str) * multiplier
        return parsed if not np.isnan(parsed) else default
    except (ValueError, TypeError):
        logger.warning(f"Failed to parse numeric value: {value}, using default {default}")
        return default

def _save_fig(fig, title: str, prefix: str = None) -> str:
    """Save figure with optimal sizing and styling."""
    try:
        import time
        if prefix is None:
            prefix = uuid.uuid4().hex[:8]
        safe_title = _safe_filename(title)
        # Add timestamp to prevent caching issues across different influencers
        timestamp = int(time.time() * 1000)
        fname = f"{prefix}_{safe_title}_{timestamp}.png"
        out_path = _CHARTS_DIR / fname
        
        fig.set_size_inches(14, 10)
        fig.savefig(str(out_path), bbox_inches="tight", dpi=150, facecolor='white',
                   edgecolor='none', pad_inches=0.5)
        plt.close(fig)
        return str(out_path.resolve())
    except Exception as e:
        try:
            plt.close(fig)
        except:
            pass
        return ""

def save_3d_bar_chart(labels: List[str], values: List[float], title: str,
                      prefix: str = None) -> Tuple[str, str]:
    """Create 2D bar chart (converted from 3D)."""
    try:
        fig, ax = plt.subplots(figsize=(14, 10), facecolor='white')
        num_bars = len(labels)
        x_pos = np.arange(num_bars)
        colors_list = [COLOR_SEQUENCE[i % len(COLOR_SEQUENCE)] for i in range(num_bars)]
        
        # Create 2D bars with enhanced styling
        bars = ax.bar(x_pos, values, color=colors_list, alpha=0.9, 
                     edgecolor='white', linewidth=2)
        
        # Clean, readable labels
        ax.set_xticks(x_pos)
        ax.set_xticklabels(labels, fontsize=13, weight='bold', 
                          color=COLORS['text_dark'], ha='center', rotation=0)
        ax.set_ylabel('Value', fontsize=15, weight='bold', 
                     color=COLORS['text_dark'])
        ax.set_title(title, fontsize=18, weight='bold', 
                    color=COLORS['text_dark'], pad=20)
        
        # Value labels on top of bars
        max_val = max(values) if values else 1
        for i, (bar, val) in enumerate(zip(bars, values)):
            label_y = val + max_val * 0.02
            unit = '%' if val < 100 else ''
            ax.text(bar.get_x() + bar.get_width()/2, label_y,
                   f'{val:.1f}{unit}', ha='center', va='bottom',
                   fontsize=14, weight='bold', color=COLORS['text_dark'])
        
        ax.set_ylim(0, max_val * 1.2)
        ax.grid(True, alpha=0.2, linestyle='--', color=COLORS['grid'], axis='y')
        ax.set_facecolor('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        
        plt.tight_layout()
        
        path = _save_fig(fig, title, prefix)
        return (title, path) if path else (title, "")
    except Exception as e:
        logger.error(f"Failed to create bar chart: {e}")
        try:
            plt.close()
        except:
            pass
        return (title, "")

def save_3d_gauge_chart(value: float, title: str, max_value: float = 100,
                       prefix: str = None) -> Tuple[str, str]:
    """Create modern 2D gauge chart (converted from 3D)."""
    try:
        fig, ax = plt.subplots(figsize=(10, 8), facecolor='white',
                              subplot_kw={'projection': 'polar'})
        
        # Background arc - full semicircle
        ax.barh(1, np.pi, left=0, height=0.5, color=COLORS['background'], 
               alpha=0.3, edgecolor=COLORS['grid'], linewidth=2)
        
        # Value arc with dynamic color
        theta_val = (min(value, max_value) / max_value) * np.pi
        
        if value < 40:
            color = COLORS['accent2']  # Soft coral
        elif value < 70:
            color = COLORS['accent4']  # Powder blue
        else:
            color = COLORS['accent1']  # Soft mint
        
        # Main value arc (2D - single layer) with better styling
        ax.barh(1, theta_val, left=0, height=0.5, color=color, alpha=0.9,
               edgecolor='white', linewidth=3)
        
        # Add percentage indicator marks
        for i in [0, 25, 50, 75, 100]:
            angle = (i / max_value) * np.pi
            ax.plot([angle, angle], [0.8, 1.2], color=COLORS['grid'], 
                   linewidth=1, alpha=0.5)
        
        # Styling
        ax.set_ylim(0, 2.0)
        ax.set_xlim(0, np.pi)
        ax.set_yticks([])
        ax.set_xticks([])
        ax.spines['polar'].set_visible(False)
        ax.set_facecolor('white')
        
        # Large value display with better positioning
        ax.text(np.pi/2, 0.6, f'{value:.1f}%', ha='center', va='center',
               fontsize=64, weight='bold', color=COLORS['text_dark'])
        
        ax.text(np.pi/2, 0.25, title, ha='center', va='center',
               fontsize=16, color=COLORS['text_light'], weight='bold')
        
        plt.tight_layout()
        path = _save_fig(fig, title, prefix)
        return (title, path) if path else (title, "")
    except Exception as e:
        logger.error(f"Failed to create gauge chart: {e}")
        try:
            plt.close()
        except:
            pass
        return (title, "")

def save_3d_donut_chart(labels: List[str], values: List[float], title: str,
                       prefix: str = None) -> Tuple[str, str]:
    """Create 2D donut chart (converted from 3D)."""
    try:
        # Validate inputs
        if not values or len(values) < 2:
            logger.warning(f"Insufficient data for donut chart: {len(values) if values else 0} values")
            return (title, "")

        # Filter out zero or negative values and ensure we have at least 2 segments
        filtered_data = [(label, val) for label, val in zip(labels, values) if val > 0]
        if len(filtered_data) < 2:
            logger.warning(f"Insufficient non-zero data for donut chart: {len(filtered_data)} segments")
            return (title, "")

        labels, values = zip(*filtered_data)
        labels = list(labels)
        values = list(values)

        total = sum(values)
        if total <= 0:
            logger.warning(f"Total value is zero or negative: {total}")
            return (title, "")

        # Check if any segment is too small (less than 2% of total)
        min_percentage = 2.0
        for i, val in enumerate(values):
            percentage = (val / total) * 100
            if percentage < min_percentage:
                logger.warning(f"Segment '{labels[i]}' is too small ({percentage:.2f}%) for donut chart. Minimum {min_percentage}% required.")
                return (title, "")
        
        # Create 2D donut chart
        fig, ax = plt.subplots(figsize=(12, 10), facecolor='white')
        
        colors_list = COLOR_SEQUENCE[:len(labels)]
        
        # Create donut chart using pie chart with hole
        wedges, texts, autotexts = ax.pie(
            values,
            labels=labels,
            colors=colors_list,
            autopct='%1.1f%%',
            startangle=90,
            pctdistance=0.85,
            textprops={'fontsize': 14, 'weight': 'bold', 'color': COLORS.get('text_dark', '#000000')},
            wedgeprops=dict(width=0.5, edgecolor='white', linewidth=3)
        )
        
        # Style the percentage text
        for autotext in autotexts:
            autotext.set_color('white')
            autotext.set_fontweight('bold')
            autotext.set_fontsize(16)
        
        # Style the labels
        for text in texts:
            text.set_fontsize(14)
            text.set_fontweight('bold')
            text.set_color(COLORS.get('text_dark', '#000000'))
        
        # Add center text with total if needed
        ax.text(0, 0, title, ha='center', va='center', 
               fontsize=18, weight='bold', color=COLORS.get('text_dark', '#000000'))
        
        ax.set_aspect('equal')
        plt.tight_layout()
        
        path = _save_fig(fig, title, prefix)
        return (title, path) if path else (title, "")
    except Exception as e:
        logger.error(f"Failed to create donut chart: {e}")
        try:
            plt.close()
        except:
            pass
        return (title, "")

# Comprehensive metric charts logic removed - replaced by targeted chart generation.


def _parse_demographic_data(data_str: str) -> Dict[str, float]:
    """Parse demographic data from various formats."""
    result = {}
    if not data_str or data_str == 'N/A':
        return result
    try:
        import json
        parsed = json.loads(data_str)
        if isinstance(parsed, dict):
            for key, value in parsed.items():
                try:
                    result[str(key).strip()] = float(value)
                except (ValueError, TypeError):
                    pass
            return result
    except (json.JSONDecodeError, ValueError):
        pass
    try:
        parts = data_str.split(',')
        for part in parts:
            part = part.strip()
            if ':' in part:
                key_val = part.split(':', 1)
                if len(key_val) == 2:
                    key = key_val[0].strip()
                    value_str = key_val[1].strip().replace('%', '').strip()
                    try:
                        value = float(value_str)
                        result[key] = value
                    except ValueError:
                        pass
    except Exception:
        pass
    return result


# Unused large number, pie chart, point chart, core metrics, bar chart, and breakdown chart functions removed.
# Only keeping specialized, production-ready charts below.



def save_engagement_breakdown_chart(avg_likes: float, avg_comments: float, total_engagement: float, 
                                    title: str = "Engagement Breakdown", prefix: str = None) -> Tuple[str, str]:
    """Create donut chart showing engagement distribution (likes %, comments %, other %)."""
    try:
        if total_engagement <= 0:
            # Calculate from likes and comments if total not available
            total_engagement = avg_likes + avg_comments
        
        if total_engagement <= 0:
            return (title, "")
        
        likes_pct = (avg_likes / total_engagement * 100) if total_engagement > 0 else 0
        comments_pct = (avg_comments / total_engagement * 100) if total_engagement > 0 else 0
        other_pct = max(0, 100 - likes_pct - comments_pct)
        
        labels = []
        values = []
        
        if likes_pct > 0:
            labels.append("Likes")
            values.append(likes_pct)
        if comments_pct > 0:
            labels.append("Comments")
            values.append(comments_pct)
        if other_pct > 1:  # Only include if > 1%
            labels.append("Other Interactions")
            values.append(other_pct)
        
        if len(labels) < 2:
            # If we don't have enough segments, create a simple 2-segment chart
            if likes_pct > 0:
                labels = ["Likes", "Comments"]
                values = [likes_pct, max(comments_pct, 100 - likes_pct)]
            else:
                return (title, "")
        
        return save_3d_donut_chart(labels, values, title, prefix)
    except Exception as e:
        logger.error(f"Failed to create engagement breakdown chart: {e}")
        return (title, "")


def save_bar_chart_simple(labels: List[str], values: List[float], title: str = "Bar Chart",
                          ylabel: str = "Value", prefix: str = None) -> Tuple[str, str]:
    """Create a simple horizontal bar chart."""
    try:
        if not labels or not values or len(labels) != len(values):
            return (title, "")
        
        fig, ax = plt.subplots(figsize=(10, 4), facecolor='white')
        
        y_pos = range(len(labels))
        bars = ax.barh(y_pos, values, color=[COLORS['primary'], COLORS['accent']][:len(labels)])
        
        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=12)
        ax.set_xlabel(ylabel, fontsize=12, color=COLORS['text_dark'])
        ax.set_title(title, fontsize=16, fontweight='bold', color=COLORS['text_dark'], pad=15)
        
        # Add value labels on bars
        for bar, val in zip(bars, values):
            ax.text(bar.get_width() + 0.5, bar.get_y() + bar.get_height()/2,
                   f'{val:.2f}%', va='center', fontsize=11, color=COLORS['text_dark'])
        
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.set_facecolor('white')
        
        plt.tight_layout()
        path = _save_fig(fig, title, prefix)
        return (title, path) if path else (title, "")
    except Exception as e:
        logger.error(f"Failed to create bar chart: {e}")
        return (title, "")


def save_profile_stats_card(followers: float, following: float, posts: float, 
                           is_verified: bool, name: str, niche: str, location: str,
                           prefix: str = None) -> Tuple[str, str]:
    """Create a professional profile summary card with key metrics and borders."""
    try:
        # Compact, less stretched proportions with bigger fonts
        fig, ax = plt.subplots(figsize=(11, 5), facecolor='white')
        ax.axis('off')
        ax.set_xlim(0, 1)
        ax.set_ylim(0, 1)
        
        # Add border around entire card
        from matplotlib.patches import Rectangle
        border = Rectangle((0.01, 0.01), 0.98, 0.98, 
                          linewidth=3, edgecolor=COLORS['primary'], 
                          facecolor='white', transform=ax.transAxes)
        ax.add_patch(border)
        
        # Inner border for depth
        inner_border = Rectangle((0.02, 0.02), 0.96, 0.96, 
                                linewidth=1, edgecolor=COLORS['grid'], 
                                facecolor='none', transform=ax.transAxes)
        ax.add_patch(inner_border)
        
        # Create a compact layout with bigger fonts
        # Name and Details Area (Left 35%)
        ax.text(0.05, 0.80, name[:22], fontsize=36, weight='bold', 
               color=COLORS['primary'], ha='left', va='top',
               transform=ax.transAxes)
        
        subtext = f"{niche} • {location}" if location else niche
        ax.text(0.05, 0.55, subtext[:38], fontsize=16, 
               color=COLORS['text_light'], ha='left', va='top',
               transform=ax.transAxes)
        
        if is_verified:
            ax.text(0.05, 0.35, "✓ Verified Account", fontsize=15, weight='bold', 
                   color=COLORS['success'], ha='left', va='top',
                   transform=ax.transAxes)
        
        # Divider line
        divider = Rectangle((0.38, 0.08), 0.015, 0.84, 
                           linewidth=1.5, edgecolor=COLORS['grid'], 
                           facecolor=COLORS['grid'], transform=ax.transAxes)
        ax.add_patch(divider)
        
        # Stats Area (Right 62%) - Split into 2 boxes (removed Posts)
        # 1. Followers (Hero) - with box
        followers_box = Rectangle((0.42, 0.12), 0.28, 0.76, 
                                  linewidth=2, edgecolor=COLORS['primary'], 
                                  facecolor=COLORS['background'], 
                                  transform=ax.transAxes, alpha=0.1)
        ax.add_patch(followers_box)
        
        followers_fmt = f"{followers/1_000_000:.2f}M" if followers >= 1_000_000 else f"{followers/1_000:.1f}K"
        ax.text(0.56, 0.58, followers_fmt, fontsize=52, weight='bold', 
               color=COLORS['text_dark'], ha='center', va='center',
               transform=ax.transAxes)
        ax.text(0.56, 0.28, "Followers", fontsize=18, 
               color=COLORS['text_light'], weight='bold', ha='center', va='center',
               transform=ax.transAxes)
        
        # 2. Following - with box
        following_box = Rectangle((0.72, 0.12), 0.26, 0.76, 
                                  linewidth=2, edgecolor=COLORS['secondary'], 
                                  facecolor=COLORS['background'], 
                                  transform=ax.transAxes, alpha=0.1)
        ax.add_patch(following_box)
        
        following_fmt = f"{following/1_000:.1f}K" if following >= 1000 else str(int(following))
        ax.text(0.85, 0.58, following_fmt, fontsize=52, weight='bold', 
               color=COLORS['text_dark'], ha='center', va='center',
               transform=ax.transAxes)
        ax.text(0.85, 0.28, "Following", fontsize=18, 
               color=COLORS['text_light'], weight='bold', ha='center', va='center',
               transform=ax.transAxes)
        
        plt.tight_layout(pad=0.15)
        path = _save_fig(fig, "Profile Stats Card", prefix)
        return ("Profile Stats Card", path) if path else ("Profile Stats Card", "")
    except Exception as e:
        logger.error(f"Failed to create profile stats card: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return ("Profile Stats Card", "")


def save_content_format_chart(post_data: List[Dict], title: str = "Content Format Distribution", 
                              prefix: str = None) -> Tuple[str, str]:
    """Create donut chart showing content format distribution (Reels %, Images %, Carousels %)."""
    try:
        if not post_data or not isinstance(post_data, list):
            return (title, "")
        
        format_counts = {"Reels": 0, "Images": 0, "Carousels": 0}
        
        for post in post_data[:50]:  # Sample first 50 posts
            post_type = str(post.get("type", "") or post.get("media_type", "")).lower()
            if "reel" in post_type or "video" in post_type:
                format_counts["Reels"] += 1
            elif "carousel" in post_type:
                format_counts["Carousels"] += 1
            else:
                format_counts["Images"] += 1
        
        total = sum(format_counts.values())
        if total == 0:
            return (title, "")
        
        labels = [k for k, v in format_counts.items() if v > 0]
        values = [format_counts[k] for k in labels]
        
        if len(labels) < 2:
            return (title, "")
        
        # Convert to percentages
        values = [(v / total * 100) for v in values]
        
        return save_3d_donut_chart(labels, values, title, prefix)
    except Exception as e:
        logger.error(f"Failed to create content format chart: {e}")
        return (title, "")


def save_activity_timeline_chart(posts: List[Dict], title: str = "Content Activity Timeline", 
                                prefix: str = None) -> Tuple[str, str]:
    """Create line chart showing posts per month or engagement over time."""
    try:
        if not posts or not isinstance(posts, list) or len(posts) == 0:
            return (title, "")
        
        # Try to extract dates and engagement from posts
        from datetime import datetime
        from collections import defaultdict
        
        monthly_posts = defaultdict(int)
        monthly_engagement = defaultdict(float)
        
        for post in posts[:100]:  # Sample first 100 posts
            try:
                # Try to get date
                date_str = post.get("timestamp") or post.get("created_at") or post.get("date")
                if date_str:
                    if isinstance(date_str, (int, float)):
                        dt = datetime.fromtimestamp(date_str)
                    else:
                        dt = datetime.fromisoformat(str(date_str).replace('Z', '+00:00'))
                    month_key = dt.strftime("%Y-%m")
                    monthly_posts[month_key] += 1
                    
                    # Try to get engagement
                    likes = _parse_numeric_value(post.get("likes") or post.get("like_count"), 0.0)
                    comments = _parse_numeric_value(post.get("comments") or post.get("comment_count"), 0.0)
                    monthly_engagement[month_key] += (likes + comments)
            except Exception:
                continue
        
        if len(monthly_posts) < 2:
            return (title, "")
        
        # Sort by date
        sorted_months = sorted(monthly_posts.keys())
        post_counts = [monthly_posts[m] for m in sorted_months]
        
        fig, ax = plt.subplots(figsize=(12, 8), facecolor='white')
        
        ax.plot(sorted_months, post_counts, 'o-', color=COLORS['primary'], 
               linewidth=3, markersize=10, markerfacecolor=COLORS['primary'],
               markeredgecolor='white', markeredgewidth=2, alpha=0.9)
        
        ax.fill_between(sorted_months, post_counts, alpha=0.3, color=COLORS['primary'])
        
        ax.set_title(title, fontsize=20, weight='bold', color=COLORS['text_dark'], pad=20)
        ax.set_xlabel('Month', fontsize=14, weight='bold', color=COLORS['text_dark'])
        ax.set_ylabel('Posts per Month', fontsize=14, weight='bold', color=COLORS['text_dark'])
        ax.grid(True, alpha=0.2, linestyle='--', color=COLORS['grid'], axis='y')
        ax.set_facecolor('white')
        
        plt.xticks(rotation=45, ha='right')
        plt.tight_layout()
        path = _save_fig(fig, title, prefix)
        return (title, path) if path else (title, "")
    except Exception as e:
        logger.error(f"Failed to create activity timeline chart: {e}")
        try:
            plt.close()
        except:
            pass
        return (title, "")


def generate_individual_metric_charts(metrics: Dict[str, Any], detail: Dict[str, Any], prefix: str = None) -> List[Tuple[str, str]]:
    """
    Generate ONLY decision-focused charts for single influencer reports.
    
    FINAL LIST (6-7 charts max):
    0. Profile Stats Card (HERO VISUAL - Replaces Core Metrics Table)
    1. Engagement Rate Gauge
    2. Engagement Breakdown (Donut - Likes %, Comments %, Other %)
    3. Audience Authenticity (Donut - Real vs Suspicious)
    4. Content Format Distribution (Donut - Reels, Images, Carousels) - if data available
    5. Content Activity Timeline (Line chart) - if data available
    6. Brand Fit Score (Gauge)
    
    REMOVED: 
    - Followers vs Engagement Efficiency chart (eliminated data duplication)
    - All single-value bar charts, ratio charts, redundant metrics
    - Core Metrics Table (replaced by Profile Stats Card)
    """
    logger.debug(f"🎨 Starting chart generation with prefix: {prefix}")
    logger.debug(f"   Metrics keys: {list(metrics.keys()) if metrics else 'None'}")
    logger.debug(f"   Detail keys sample: {list(detail.keys())[:10] if detail else 'None'}")
    
    charts = []
    
    def safe_get(key: str, default: float = 0.0) -> float:
        """Safely get metric value from metrics dict or detail."""
        val = metrics.get(key) or detail.get(key, default)
        result = _parse_numeric_value(val, default)
        if result != default:
            logger.debug(f"   Found {key} = {result}")
        if result != default:
            logger.debug(f"   Found {key} = {result}")
        return result
        
    # 0. Profile Stats Card (HERO VISUAL - Replaces Table)
    try:
        followers = safe_get("followers", 0)
        following = safe_get("following", 0)
        posts = safe_get("posts", 0) or safe_get("posts_count", 0)
        is_verified = detail.get("is_verified", False)
        name = detail.get("name") or detail.get("NAME", "Influencer")
        niche = detail.get("niche") or detail.get("NICHE", "Creator")
        location = detail.get("location") or detail.get("Location", "")
        
        logger.debug(f"📊 Profile Stats Card data: followers={followers}, following={following}, posts={posts}, name={name}")
        
        if followers > 0:  # Only create card if we have followers data
            chart_result = save_profile_stats_card(
                followers, following, posts, is_verified,
                name, niche, location, prefix
            )
            if chart_result[1]:
                charts.append(chart_result)
                logger.debug(f"✅ Profile Stats Card created: {chart_result[1]}")
            else:
                logger.warning("⚠️ Profile Stats Card returned empty path")
        else:
            logger.warning(f"⚠️ Skipping Profile Stats Card - no followers data (followers={followers})")
    except Exception as e:
        logger.error(f"Profile Stats Card failed: {e}")
    
    # 1. Engagement Rate Gauge (PRIMARY)
    try:
        engagement_rate = safe_get("engagement_rate", 0)
        # Normalize to 0-100 if it's a decimal
        if engagement_rate > 0:
            chart_result = save_3d_gauge_chart(min(engagement_rate, 100), "Engagement Rate", 100, prefix)
            if chart_result[1]:
                charts.append(chart_result)
                logger.debug(f"✅ Engagement Rate chart created: {chart_result[1]}")
            else:
                logger.warning("⚠️ Engagement Rate chart returned empty path")
        else:
            logger.warning(f"⚠️ Skipping Engagement Rate chart - no data (engagement_rate={engagement_rate})")
    except Exception as e:
        logger.error(f"Engagement Rate chart failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    # 2. Engagement Breakdown (Donut - Likes %, Comments %, Other %)
    try:
        avg_likes = safe_get("average_likes", 0) or safe_get("avg_likes", 0)
        avg_comments = safe_get("average_comments", 0) or safe_get("avg_comments", 0)
        total_engagement = avg_likes + avg_comments
        
        if total_engagement > 0:
            chart_result = save_engagement_breakdown_chart(
                avg_likes, avg_comments, total_engagement,
                "Engagement Breakdown", prefix
            )
            if chart_result[1]:  # If path exists
                charts.append(chart_result)
                logger.debug(f"✅ Engagement Breakdown chart created: {chart_result[1]}")
            else:
                logger.warning("⚠️ Engagement Breakdown chart returned empty path")
        else:
            logger.warning(f"⚠️ Skipping Engagement Breakdown chart - no data (total_engagement={total_engagement})")
    except Exception as e:
        logger.error(f"Engagement Breakdown chart failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    # 3. Audience Authenticity (Donut - Real vs Suspicious) - MANDATORY
    try:
        real_pct = safe_get("real_followers_percentage", 0) or safe_get("real_percentage", 0)
        fake_pct = safe_get("suspicious_followers_percentage", 0) or safe_get("fake_follower_ratio", 0)
        
        logger.debug(f"📊 Audience Authenticity data: real_pct={real_pct}, fake_pct={fake_pct}")
        
        # Normalize to 0-100 if decimals
        if 0 < real_pct <= 1:
            real_pct = real_pct * 100
        if 0 < fake_pct <= 1:
            fake_pct = fake_pct * 100
        
        # Calculate fake from real if not available
        if fake_pct <= 0 and real_pct > 0:
            fake_pct = max(0, 100 - real_pct)
        elif real_pct <= 0 and fake_pct > 0:
            real_pct = max(0, 100 - fake_pct)
        
        if real_pct > 0 or fake_pct > 0:
            # Ensure we have both values
            if real_pct <= 0:
                real_pct = max(0, 100 - fake_pct)
            if fake_pct <= 0:
                fake_pct = max(0, 100 - real_pct)
            
            chart_result = save_3d_donut_chart(
                ["Real Followers", "Suspicious/Bot Followers"],
                [real_pct, fake_pct],
                "Audience Authenticity",
                prefix
            )
            if chart_result[1]:
                charts.append(chart_result)
                logger.debug(f"✅ Audience Authenticity chart created: {chart_result[1]}")
            else:
                logger.warning("⚠️ Audience Authenticity chart returned empty path")
        else:
            logger.warning(f"⚠️ Skipping Audience Authenticity chart - no data (real_pct={real_pct}, fake_pct={fake_pct})")
    except Exception as e:
        logger.error(f"Audience Authenticity chart failed: {e}")
        import traceback
        logger.error(traceback.format_exc())
    
    # 4. REMOVED: Followers vs Engagement Efficiency (Combo chart) - Deprecated
    
    # 5. Content Format Distribution (if posts data available)
    try:
        posts_data = detail.get("posts", [])
        if posts_data and isinstance(posts_data, list) and len(posts_data) > 0:
            chart_result = save_content_format_chart(posts_data, "Content Format Distribution", prefix)
            if chart_result[1]:  # If path exists
                charts.append(chart_result)
                logger.debug("✅ Added Content Format Distribution chart")
    except Exception as e:
        logger.error(f"Content Format chart failed: {e}")
    
    # 6. Content Activity Timeline (if posts data available)
    try:
        posts_data = detail.get("posts", [])
        if posts_data and isinstance(posts_data, list) and len(posts_data) > 0:
            chart_result = save_activity_timeline_chart(posts_data, "Content Activity Timeline", prefix)
            if chart_result[1]:  # If path exists
                charts.append(chart_result)
                logger.debug("✅ Added Content Activity Timeline chart")
    except Exception as e:
        logger.error(f"Activity Timeline chart failed: {e}")
    
    result = [(title, path) for title, path in charts if path]
    logger.debug(f"✅ Chart generation complete: {len(result)} charts generated out of {len(charts)} attempted")
    for title, path in result:
        logger.debug(f"   • {title}: {path}")
    return result


def save_posts_engagement_chart(posts_data: List[Dict], title: str = "Recent Posts Engagement",
                                prefix: str = None) -> Tuple[str, str]:
    """Create a point-wise graph showing post engagement over time."""
    try:
        if not posts_data or not isinstance(posts_data, list) or len(posts_data) == 0:
            return (title, "")
        
        from datetime import datetime
        
        # Extract data points
        dates = []
        engagements = []
        likes_list = []
        comments_list = []
        
        for post in posts_data:
            likes = _parse_numeric_value(post.get("likes") or post.get("like_count"), 0.0)
            comments = _parse_numeric_value(post.get("comments") or post.get("comment_count"), 0.0)
            total_engagement = likes + comments
            
            if total_engagement > 0:
                date_str = post.get("datetime") or post.get("date")
                if date_str:
                    try:
                        if isinstance(date_str, (int, float)):
                            dt = datetime.fromtimestamp(date_str)
                        else:
                            dt = datetime.fromisoformat(str(date_str).replace('Z', '+00:00'))
                        dates.append(dt)
                        engagements.append(total_engagement)
                        likes_list.append(likes)
                        comments_list.append(comments)
                    except Exception:
                        continue
        
        if len(dates) < 2:
            return (title, "")
        
        # Sort by date
        sorted_data = sorted(zip(dates, engagements, likes_list, comments_list))
        dates, engagements, likes_list, comments_list = zip(*sorted_data)
        
        # Create the graph
        fig, ax = plt.subplots(figsize=(12, 7), facecolor='white')
        
        # Option A: Use evenly spaced indices instead of dates to prevent clustering
        x_indices = list(range(len(dates)))
        
        # Plot engagement as points with lines
        ax.plot(x_indices, engagements, 'o-', color=COLORS['primary'], 
               linewidth=2.5, markersize=10, markerfacecolor=COLORS['primary'],
               markeredgecolor='white', markeredgewidth=2, alpha=0.9, label='Total Engagement')
        
        # Add fill under the curve
        ax.fill_between(x_indices, engagements, alpha=0.2, color=COLORS['primary'])
        
        # Add value labels on points
        for i, (date, engagement) in enumerate(zip(dates, engagements)):
            if engagement > 0:
                # Format engagement number
                if engagement >= 1_000_000:
                    engagement_str = f"{engagement/1_000_000:.1f}M"
                elif engagement >= 1_000:
                    engagement_str = f"{engagement/1_000:.1f}K"
                else:
                    engagement_str = f"{int(engagement)}"
                
                ax.annotate(engagement_str, 
                          (x_indices[i], engagement),
                          textcoords="offset points",
                          xytext=(0, 15),
                          ha='center', fontsize=10, weight='bold',
                          color=COLORS['text_dark'],
                          bbox=dict(boxstyle='round,pad=0.4', facecolor='white',
                                  alpha=0.9, edgecolor=COLORS['primary'], linewidth=1))
        
        # Format x-axis dates
        ax.set_xlabel('Post Date', fontsize=14, weight='bold', color=COLORS['text_dark'])
        ax.set_ylabel('Engagement (Likes + Comments)', fontsize=14, weight='bold', color=COLORS['text_dark'])
        ax.set_title(title, fontsize=18, weight='bold', color=COLORS['text_dark'], pad=15)
        
        # Format dates on x-axis - use string labels on indices
        date_labels = [dt.strftime('%Y-%m-%d') for dt in dates]
        ax.set_xticks(x_indices)
        ax.set_xticklabels(date_labels, rotation=45, ha='right', fontsize=10)
        
        # Styling
        ax.grid(True, alpha=0.2, linestyle='--', color=COLORS['grid'], axis='y')
        ax.set_facecolor('white')
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['left'].set_color(COLORS['grid'])
        ax.spines['bottom'].set_color(COLORS['grid'])
        
        # Format y-axis to show K/M notation
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, p: f'{x/1_000:.0f}K' if x >= 1_000 else f'{int(x)}'))
        
        plt.tight_layout()
        path = _save_fig(fig, title, prefix)
        return (title, path) if path else (title, "")
    except Exception as e:
        logger.error(f"Failed to create posts engagement chart: {e}")
        import traceback
        logger.error(traceback.format_exc())
        try:
            plt.close()
        except:
            pass
        return (title, "")
