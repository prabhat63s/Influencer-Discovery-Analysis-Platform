
# ============================================================================
# DYNAMIC PDF GENERATOR - dynamic_pdf_generator.py
# Generates AI-enriched PDF reports for influencers (charts, insights, layout)
# ============================================================================

from __future__ import annotations

import json
import logging
import math
import re
import shutil
import tempfile
import time
import unicodedata
import xml.sax.saxutils as saxutils
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib
import matplotlib.pyplot as plt
import numpy as np

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    Image,
    KeepTogether,
    ListFlowable,
    ListItem,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from app.services.core.search_filters import parse_followers_to_int
from app.utils.metric_constants import METRIC_ALIASES, COLORS, normalize_metric_value

# ============================================================================
# METRIC TRACKING SYSTEM - Prevent Duplication
# ============================================================================
class MetricTracker:
    """Track which metrics have been displayed to prevent duplication.
    ONLY allows tracking of permitted metrics per refactor requirements."""
    
    # ALLOWED METRICS ONLY
    ALLOWED_METRICS = {
        "followers", "engagement_rate", "avg_likes", "avg_comments", "posts",
        "following", "is_verified", "real_follower_ratio", "fake_follower_ratio",
        "like_to_follower_ratio", "comment_depth_ratio", "real_percentage", "fake_percentage"
    }
    
    def __init__(self):
        self.shown_metrics = set()
        self.shown_sections = set()
        self.conclusions_given = set()  # Track conclusions to prevent repetition
        self.unique_questions = set()  # Track questions answered per section
    
    def mark_shown(self, metric_name: str):
        """Mark a metric as shown. Only allows permitted metrics."""
        normalized = metric_name.lower()
        # Check if it's an allowed metric or a variation
        if normalized in self.ALLOWED_METRICS:
            self.shown_metrics.add(normalized)
        elif any(allowed in normalized for allowed in self.ALLOWED_METRICS):
            # Allow variations like "real_followers_percentage" -> "real_follower_ratio"
            for allowed in self.ALLOWED_METRICS:
                if allowed in normalized:
                    self.shown_metrics.add(allowed)
                    break
    
    def is_shown(self, metric_name: str) -> bool:
        """Check if a metric has been shown."""
        normalized = metric_name.lower()
        if normalized in self.shown_metrics:
            return True
        # Check variations
        for shown in self.shown_metrics:
            if shown in normalized or normalized in shown:
                return True
        return False
    
    def mark_section(self, section_name: str):
        """Mark a section as processed."""
        self.shown_sections.add(section_name.lower())
    
    def is_section_shown(self, section_name: str) -> bool:
        """Check if a section has been processed."""
        return section_name.lower() in self.shown_sections
    
    def mark_conclusion(self, conclusion_type: str):
        """Mark a type of conclusion as given (e.g., 'final_recommendation', 'suitability_verdict')."""
        self.conclusions_given.add(conclusion_type.lower())
    
    def has_conclusion(self, conclusion_type: str) -> bool:
        """Check if a conclusion type has already been given."""
        return conclusion_type.lower() in self.conclusions_given
    
    def mark_question(self, section: str, question: str):
        """Mark a question as answered in a section."""
        key = f"{section.lower()}:{question.lower()}"
        self.unique_questions.add(key)
    
    def is_question_answered(self, section: str, question: str) -> bool:
        """Check if a question has been answered in a section."""
        key = f"{section.lower()}:{question.lower()}"
        return key in self.unique_questions


# ============================================================================
# DATA VALIDATION LAYER - Prevent Zero Override
# ============================================================================
class DataValidator:
    """Validate data before PDF generation to prevent zero values when header has real data."""
    
    def __init__(self, detail: Dict[str, Any]):
        self.detail = detail
        self.metrics = detail.get("metrics", {})
        self.authoritative_values = {}  # Store authoritative values from header/metrics
        self._extract_authoritative_values()
    
    def _extract_authoritative_values(self):
        """Extract authoritative values from header and metrics."""
        # Followers - check multiple sources
        followers = self.metrics.get("followers") or self.detail.get("followers")
        if followers:
            try:
                if isinstance(followers, str):
                    from app.services.core.search_filters import parse_followers_to_int
                    followers = parse_followers_to_int(followers)
                if isinstance(followers, (int, float)) and followers > 0:
                    self.authoritative_values["followers"] = int(followers)
            except Exception:
                pass
        
        # Engagement rate
        eng = self.metrics.get("engagement_rate") or self.detail.get("engagement_rate")
        if eng:
            eng_val = _safe_float(eng)
            if eng_val and eng_val > 0:
                self.authoritative_values["engagement_rate"] = eng_val
        
        # Real followers percentage
        real = (self.metrics.get("real_percentage") or 
                self.metrics.get("real_follower_ratio") or
                self.detail.get("real_percentage") or
                self.detail.get("real_followers_percentage"))
        if real:
            real_val = _safe_float(real)
            if real_val and real_val > 0:
                self.authoritative_values["real_percentage"] = real_val
        
        # Average likes
        likes = self.metrics.get("avg_likes") or self.metrics.get("average_likes") or self.detail.get("avg_likes") or self.detail.get("average_likes")
        if likes:
            likes_val = _safe_float(likes)
            if likes_val and likes_val > 0:
                self.authoritative_values["avg_likes"] = likes_val
        
        # Average comments
        comments = self.metrics.get("avg_comments") or self.metrics.get("average_comments") or self.detail.get("avg_comments") or self.detail.get("average_comments")
        if comments:
            comments_val = _safe_float(comments)
            if comments_val and comments_val > 0:
                self.authoritative_values["avg_comments"] = comments_val
    
    def get_validated_value(self, key: str, value: Any) -> Any:
        """Return validated value - never return 0 if authoritative value exists."""
        # If we have an authoritative value, use it
        if key in self.authoritative_values:
            auth_val = self.authoritative_values[key]
            # Only override if current value is 0 or missing
            if not value or (isinstance(value, (int, float)) and value == 0):
                return auth_val
            return value
        
        # If no authoritative value, return original (could be 0 or None)
        return value
    
    def format_missing_data(self, key: str, value: Any) -> str:
        """Format missing data as 'Not Available' instead of '0'."""
        validated = self.get_validated_value(key, value)
        
        if validated is None:
            return "Not Available"
        
        if isinstance(validated, (int, float)):
            if validated == 0:
                # Check if we have authoritative value
                if key in self.authoritative_values:
                    return str(self.authoritative_values[key])
                return "Not Available"
            return str(validated)
        
        if isinstance(validated, str):
            if validated.lower() in ("n/a", "nan", "none", "null", ""):
                return "Not Available"
            return validated
        
        return "Not Available"
    
    def get_data_confidence(self, key: str) -> str:
        """Return confidence level: High, Medium, or Low."""
        if key in self.authoritative_values:
            return "High"
        
        value = self.detail.get(key) or self.metrics.get(key)
        if value and value not in (None, "", "N/A", 0):
            return "Medium"
        
        return "Low"


# ============================================================================
# INDUSTRY BENCHMARK HELPER
# ============================================================================
def get_industry_benchmarks(detail: Dict[str, Any], conversation_id: Optional[str] = None) -> Dict[str, Any]:
    """Get industry benchmarks from peers if available."""
    benchmarks = {}
    
    try:
        if conversation_id:
            from app.services.data import temp_store
            all_results = temp_store.load_session(conversation_id)
            
            if all_results and isinstance(all_results, dict):
                results = all_results.get("results", [])
                if not results:
                    results = all_results.get("industry_standards", [])
                
                if results and len(results) > 1:
                    # Find peers (industry_standard = True)
                    peers = [r for r in results if r.get("industry_standard") is True]
                    
                    if peers:
                        # Calculate benchmarks
                        peer_followers = []
                        peer_engagement = []
                        peer_authenticity = []
                        
                        for peer in peers:
                            f = _safe_float(peer.get("followers"))
                            if f and f > 0:
                                peer_followers.append(f)
                            
                            e = _safe_float(peer.get("engagement_rate"))
                            if e and e > 0:
                                peer_engagement.append(e)
                            
                            r = _safe_float(peer.get("real_percentage") or peer.get("real_followers_percentage"))
                            if r and r > 0:
                                peer_authenticity.append(r)
                        
                        if peer_followers:
                            benchmarks["followers_median"] = sorted(peer_followers)[len(peer_followers) // 2]
                            benchmarks["followers_max"] = max(peer_followers)
                            benchmarks["followers_min"] = min(peer_followers)
                        
                        if peer_engagement:
                            benchmarks["engagement_median"] = sorted(peer_engagement)[len(peer_engagement) // 2]
                            benchmarks["engagement_max"] = max(peer_engagement)
                            benchmarks["engagement_min"] = min(peer_engagement)
                        
                        if peer_authenticity:
                            benchmarks["authenticity_median"] = sorted(peer_authenticity)[len(peer_authenticity) // 2]
                            benchmarks["authenticity_max"] = max(peer_authenticity)
                            benchmarks["authenticity_min"] = min(peer_authenticity)
    except Exception as e:
        logger.debug(f"Could not load industry benchmarks: {e}")
    
    return benchmarks


def split_text_into_bullets(text: str, max_items: int = 4) -> List[str]:
    """Convert paragraph text into bullet-sized sentences."""
    if not text:
        return []
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    bullets = [s.strip() for s in sentences if s.strip()]
    return bullets[:max_items]


def _remove_metric_repetition(text: str, metric_tracker: Optional[MetricTracker] = None) -> str:
    """Remove repeated metric mentions from text to avoid duplication."""
    if not text or not metric_tracker:
        return text
    
    patterns_to_remove = []
    if metric_tracker.is_shown("followers"):
        patterns_to_remove.append(r'\d+[,\d]*\s*followers?')
    if metric_tracker.is_shown("engagement_rate"):
        patterns_to_remove.append(r'\d+\.?\d*\s*%?\s*engagement')
    if metric_tracker.is_shown("real_percentage"):
        patterns_to_remove.append(r'\d+\.?\d*\s*%\s*real')
    
    result = text
    for pattern in patterns_to_remove:
        result = re.sub(pattern, '', result, flags=re.IGNORECASE)
    
    result = re.sub(r'\s+', ' ', result).strip()
    return result if result else text


def _parse_demographic_string(data_str: str) -> Dict[str, float]:
    """Parse demographic string into dictionary of values."""
    if not data_str or data_str in {"N/A", "nan"}:
        return {}
    result: Dict[str, float] = {}
    try:
        parsed = json.loads(data_str)
        if isinstance(parsed, dict):
            for key, value in parsed.items():
                num = _safe_float(value)
                if num is not None:
                    result[str(key).strip()] = num
            if result:
                return result
    except (json.JSONDecodeError, TypeError):
        pass
    parts = [segment.strip() for segment in data_str.split(",") if segment.strip()]
    for part in parts:
        if ":" in part:
            left, right = part.split(":", 1)
            num = _safe_float(right)
            if num is not None:
                result[left.strip()] = num
        elif " " in part:
            *label_parts, value_str = part.split()
            label = " ".join(label_parts).strip()
            num = _safe_float(value_str)
            if label and num is not None:
                result[label] = num
    return result


def _sanitize_text_remove_metrics(text: str, metric_tracker: Optional[MetricTracker] = None, 
                                  section_context: str = None) -> str:
    """
    Remove numeric metric values from text to prevent duplication.
    CRITICAL: This ensures metrics shown in tables/charts NEVER appear in text.
    Now section-aware: removes metrics that are NOT relevant to the current section.
    
    Strategy:
    1. If metric_tracker is provided, remove only metrics that have been shown
    2. Section-specific: Remove metrics that don't belong to current section
    3. Always remove standalone percentages and large numbers that could be metrics
    """
    if not text:
        return text
    
    import re
    
    # Comprehensive patterns to remove numeric metric values
    all_patterns = {
        "followers": [
            r'\d+[,\d]*\s*(million|m|k|thousand)?\s*followers?',
            r'followers?[:\s]*\d+[,\d]*',
            r'follower\s*count[:\s]*\d+[,\d]*',
            r'\d+[,\d]*\s*(million|m|k)\s*followers?',
        ],
        "engagement_rate": [
            r'\d+\.?\d*\s*%?\s*engagement\s*rate',
            r'engagement\s*rate[:\s]*\d+\.?\d*\s*%?',
            r'\d+\.?\d*\s*%?\s*engagement',
            r'engagement[:\s]*\d+\.?\d*\s*%?',
        ],
        "avg_likes": [
            r'\d+[,\d]*\s*(average\s*)?likes?',
            r'average\s*likes?[:\s]*\d+[,\d]*',
            r'likes?[:\s]*\d+[,\d]*',
        ],
        "avg_comments": [
            r'\d+[,\d]*\s*(average\s*)?comments?',
            r'average\s*comments?[:\s]*\d+[,\d]*',
            r'comments?[:\s]*\d+[,\d]*',
        ],
        "posts": [
            r'\d+[,\d]*\s*posts?',
            r'posts?[:\s]*\d+[,\d]*',
        ],
        "real_follower_ratio": [
            r'\d+\.?\d*\s*%?\s*real\s*followers?',
            r'real\s*followers?[:\s]*\d+\.?\d*\s*%?',
            r'\d+\.?\d*\s*%?\s*authentic',
            r'authenticity[:\s]*\d+\.?\d*\s*%?',
            r'\d+\.?\d*\s*%?\s*authentic\s*followers?',
        ],
        "fake_follower_ratio": [
            r'\d+\.?\d*\s*%?\s*suspicious',
            r'suspicious[:\s]*\d+\.?\d*\s*%?',
            r'\d+\.?\d*\s*%?\s*fake',
            r'fake[:\s]*\d+\.?\d*\s*%?',
        ],
        "like_to_follower_ratio": [
            r'\d+\.?\d*\s*%?\s*like.*follower',
            r'like.*follower[:\s]*\d+\.?\d*\s*%?',
            r'like.*follower\s*ratio[:\s]*\d+\.?\d*\s*%?',
        ],
        "comment_depth_ratio": [
            r'\d+\.?\d*\s*comment.*depth',
            r'comment.*depth[:\s]*\d+\.?\d*',
            r'comment.*depth\s*ratio[:\s]*\d+\.?\d*',
        ],
    }
    
    # Section-specific metric filtering
    # Each section should ONLY mention its own metrics
    section_allowed_metrics = {
        "profile_strategy": ["followers", "following", "posts", "is_verified"],
        "audience_authenticity": ["real_follower_ratio", "fake_follower_ratio"],
        "engagement_quality": ["like_to_follower_ratio", "comment_depth_ratio", "avg_likes", "avg_comments"],
        "engagement_rate": ["engagement_rate"],
        "post_analysis": [],  # Post analysis should NOT mention engagement_rate, followers, etc.
        "key_metrics": ["followers", "following", "engagement_rate", "avg_likes", "avg_comments", "total_posts"],
    }
    
    # Determine which patterns to remove
    patterns_to_remove = []
    
    if section_context and section_context.lower() in section_allowed_metrics:
        # Section-specific: Remove ALL metrics EXCEPT those allowed for this section
        allowed = section_allowed_metrics[section_context.lower()]
        for metric_name, patterns in all_patterns.items():
            if metric_name not in allowed:
                patterns_to_remove.extend(patterns)
        
        # CRITICAL: Always remove engagement_rate from all sections EXCEPT engagement_rate section
        if section_context.lower() != "engagement_rate":
            patterns_to_remove.extend(all_patterns["engagement_rate"])
    elif metric_tracker:
        # Only remove metrics that have been shown
        for metric_name, patterns in all_patterns.items():
            if metric_tracker.is_shown(metric_name):
                patterns_to_remove.extend(patterns)
    else:
        # No tracker - remove ALL metric patterns as safety measure
        for patterns in all_patterns.values():
            patterns_to_remove.extend(patterns)
    
    # Remove all matching patterns
    sanitized = text
    for pattern in patterns_to_remove:
        sanitized = re.sub(pattern, '', sanitized, flags=re.IGNORECASE)
    
    # Remove standalone percentages and large numbers that could be metrics
    # CRITICAL: Remove engagement rate patterns more aggressively if not in engagement_rate section
    if not section_context or section_context.lower() != "engagement_rate":
        sanitized = re.sub(r'\b\d+[,\d]*\.?\d*\s*%\s*(engagement|engagement\s*rate)', '', sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r'\bengagement\s*rate[:\s]*\d+[,\d]*\.?\d*\s*%?', '', sanitized, flags=re.IGNORECASE)
        sanitized = re.sub(r'\b\d+[,\d]*\.?\d*\s*%\s*engagement', '', sanitized, flags=re.IGNORECASE)
    
    sanitized = re.sub(r'\b\d+[,\d]*\s*%\s*(real|suspicious|authentic|like|follower)', '', sanitized, flags=re.IGNORECASE)
    sanitized = re.sub(r'\b\d+[,\d]*\s*(million|m|k|thousand)\s*(followers?|likes?|comments?|posts?)', '', sanitized, flags=re.IGNORECASE)
    
    # Remove any remaining numeric patterns that look like metrics
    # Exclude "engagement" from this pattern if we're in engagement_rate section
    if section_context and section_context.lower() == "engagement_rate":
        sanitized = re.sub(r'\b\d+[,\d]*\s+(followers?|likes?|comments?|posts?|authentic|suspicious|real)', '', sanitized, flags=re.IGNORECASE)
    else:
        sanitized = re.sub(r'\b\d+[,\d]*\s+(followers?|likes?|comments?|posts?|engagement|authentic|suspicious|real)', '', sanitized, flags=re.IGNORECASE)
    
    # Clean up extra spaces and punctuation
    sanitized = re.sub(r'\s+', ' ', sanitized)
    sanitized = re.sub(r'\s*,\s*,', ',', sanitized)  # Remove double commas
    sanitized = re.sub(r'\s*\.\s*\.', '.', sanitized)  # Remove double periods
    sanitized = re.sub(r'^\s*[.,]\s*', '', sanitized)  # Remove leading punctuation
    sanitized = sanitized.strip()
    
    # If text becomes too short or empty after sanitization, return a generic qualitative statement
    if len(sanitized) < 10:
        return "This metric provides valuable insights for campaign planning and partnership evaluation."
    
    return sanitized


def generate_chart_ai_content(
    detail: Dict[str, Any],
    chart_title: str,
    chart_data: Optional[Dict[str, Any]] = None,
    metric_tracker: Optional[MetricTracker] = None,
) -> Tuple[Optional[str], Optional[List[str]]]:
    """
    Use OpenAI API (via agent_service) to craft chart explanations dynamically.
    CRITICAL: Always uses OpenAI LLM, NO fallbacks. Retries on failure.
    NO numeric values - purely qualitative insights.
    Charts show numbers visually; text provides meaning only.
    """
    from app.services.llm.agent_service import generate_section_insights
    import time
    
    # Pass full detail data so LLM has complete context
    # This ensures comprehensive, data-driven insights
    section_payload = {
        "chart_title": chart_title,
        "chart_data": chart_data or {},
    }
    
    # Use full detail for comprehensive context
    # LLM will generate insights based on all available data
    full_detail = detail.copy()
    
    # Retry logic - try up to 3 times to get LLM response
    max_retries = 3
    for attempt in range(max_retries):
        try:
            # CRITICAL: Comprehensive prompt for 4-5 lines of insights
            # Check if this is NOT the Engagement Rate chart - if so, exclude engagement_rate from discussion
            is_engagement_rate_chart = "engagement rate" in chart_title.lower()
            engagement_rate_warning = "" if is_engagement_rate_chart else " CRITICAL: Do NOT mention engagement rate percentage - focus ONLY on this specific chart's metric."
            
            section_name = (
                f"{chart_title} Chart Analysis - Generate comprehensive POSITIVE, data-driven, QUALITATIVE insights "
                f"in 4-5 detailed sentences (minimum 4 sentences). Focus on what this specific metric/chart reveals "
                f"about campaign planning, brand partnership potential, audience understanding, and strategic value. "
                f"Do NOT repeat generic statements. Do NOT mention 'absence' or 'lack'. Use actual data context from "
                f"the influencer profile. Explain what this metric reveals about performance, campaign suitability, "
                f"and strategic value for brands. Be specific and actionable.{engagement_rate_warning}"
            )
            
            logger.debug(f"🔄 Attempt {attempt + 1}/{max_retries}: Generating OpenAI insights for {chart_title}")
            ai_text = generate_section_insights(
                detail=full_detail,
                section_name=section_name,
                section_data=section_payload,
            )
            
            if ai_text and ai_text.strip() and len(ai_text.strip()) > 50:
                ai_text = ai_text.strip()
                logger.debug(f"✅ OpenAI generated insights for {chart_title} ({len(ai_text)} chars)")
                
                # CRITICAL: Sanitize to remove any numeric values that AI might have included
                ai_text = _sanitize_text_remove_metrics(ai_text, metric_tracker, section_context="engagement_rate")
                bullets = split_text_into_bullets(ai_text)
                # Also sanitize bullets
                if bullets:
                    bullets = [_sanitize_text_remove_metrics(bullet, metric_tracker) for bullet in bullets if bullet.strip()]
                return ai_text, bullets or None
            else:
                logger.warning(f"⚠️ LLM returned empty/short response for {chart_title}, attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(1)  # Wait before retry
                    continue
                else:
                    logger.error(f"❌ Failed to get LLM response for {chart_title} after {max_retries} attempts")
                    # Raise exception instead of falling back
                    raise ValueError(f"LLM failed to generate insights for {chart_title} after {max_retries} attempts")
                    
        except Exception as exc:
            logger.exception(f"❌ LLM chart explanation failed for {chart_title}, attempt {attempt + 1}: {exc}")
            if attempt < max_retries - 1:
                time.sleep(2)  # Wait longer before retry
                continue
            else:
                # Final attempt failed - raise exception
                logger.error(f"❌ All LLM attempts failed for {chart_title}")
                raise ValueError(f"LLM generation failed for {chart_title}: {str(exc)}")
    
    # Should never reach here, but just in case
    raise ValueError(f"Failed to generate LLM insights for {chart_title}")


# =============================================================================
# PDF FORMATTING HELPERS (single source – used across all report sections)
# =============================================================================
# Production-safe coercion and display formatting for metrics. Handles N/A,
# percentages, locale-style numbers; used by executive summary, charts, tables.
# =============================================================================

def _safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Coerce value to float with safe handling of strings (N/A, percentages, commas).
    Returns default on invalid or empty input; avoids raising in report generation.
    """
    if value is None:
        return default
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned or cleaned.lower() in {"n/a", "nan", "none", "null"}:
            return default
        cleaned = cleaned.replace(",", "").replace("%", "")
        try:
            return float(cleaned)
        except ValueError:
            return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _format_number(value: Any, decimals: int = 2) -> Optional[str]:
    """Format numeric value with fixed decimal places for PDF display."""
    num = _safe_float(value)
    return f"{num:.{decimals}f}" if num is not None else None


def _format_percent(value: Any, decimals: int = 2, assume_fraction: bool = True) -> Optional[str]:
    """Format value as percentage; if assume_fraction and value in [0,1], scale by 100."""
    num = _safe_float(value)
    if num is None:
        return None
    if assume_fraction and abs(num) <= 1:
        num *= 100
    return f"{num:.{decimals}f}%"


def _format_currency(value: Any, decimals: int = 2) -> Optional[str]:
    """Format value as INR currency with thousand separators."""
    num = _safe_float(value)
    return f"₹{num:,.{decimals}f}" if num is not None else None


def _format_integer(value: Any) -> Optional[str]:
    """Format integer with thousand separators for large counts."""
    num = _safe_float(value)
    return f"{int(round(num)):,}" if num is not None else None


def build_executive_summary_text(detail: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build executive summary with ONLY allowed metrics.
    Returns: {strengths: List[str], risks: List[str], verdict: str}
    NO raw numbers, NO metric names explicitly mentioned.
    """
    engagement_rate = _safe_float(detail.get("engagement_rate", 0), 0.0)

    
    real_pct = _safe_float(detail.get("real_percentage") or detail.get("real_followers_percentage") or detail.get("real_follower_ratio"), 0.0)
    fake_pct = _safe_float(detail.get("fake_follower_ratio") or detail.get("suspicious_followers_percentage"), 0.0)
    
    # If fake_pct not available, calculate from real
    if fake_pct == 0 and real_pct > 0:
        fake_pct = max(0.0, 100.0 - real_pct)
    
    strengths = []
    risks = []
    
    # Strengths derived ONLY from engagement_rate and real_follower_ratio
    if engagement_rate > 5.0:
        strengths.append("Above-average audience interaction indicates strong campaign potential")
    elif engagement_rate > 3.0:
        strengths.append("Standard engagement levels suitable for brand collaborations")
    elif engagement_rate > 0:
        strengths.append("Active audience engagement supports campaign reach")
    
    if real_pct > 80:
        strengths.append("High follower authenticity reduces brand risk and improves conversion potential")
    elif real_pct > 65:
        strengths.append("Adequate audience quality for standard campaign execution")
    elif real_pct > 0:
        strengths.append("Authentic follower base supports campaign credibility")
    
    if detail.get("is_verified", False):
        strengths.append("Verified account status adds brand credibility and trust")
    
    # Limit to 3 strengths
    strengths = strengths[:3]
    if not strengths:
        strengths = ["Suitable for initial campaign testing"]
    
    # Risks derived ONLY from fake_follower_ratio
    if fake_pct > 30 or (real_pct > 0 and real_pct < 50):
        risks.append("High fake follower ratio requires contract safeguards and quarterly audits")
    elif fake_pct > 15 or (real_pct > 0 and real_pct < 70):
        risks.append("Moderate authenticity concerns - recommend performance guarantees")
    elif fake_pct > 0:
        risks.append("Some authenticity concerns - recommend monitoring")
    
    if engagement_rate > 0 and engagement_rate < 2.0:
        risks.append("Low engagement may reduce campaign effectiveness - recommend pilot before commitment")
    elif engagement_rate > 0 and engagement_rate < 3.0:
        risks.append("Below-average engagement requires performance monitoring")
    
    if not detail.get("is_verified", False) and fake_pct > 20:
        risks.append("Unverified account with significant bot activity presents brand safety risk")
    
    # Limit to 3 risks
    risks = risks[:3]
    if not risks:
        risks = ["Standard influencer partnership risks apply"]
    
    # Final verdict: Recommended or Pilot Only
    if real_pct > 70 and engagement_rate > 3.0:
        verdict = "Recommended for brand partnerships"
    elif real_pct > 50 and engagement_rate > 2.0:
        verdict = "Pilot Only - suitable for pilot campaigns with monitoring"
    else:
        verdict = "Pilot Only - requires authenticity verification before full partnership"
    
    return {
        "strengths": strengths,
        "risks": risks,
        "verdict": verdict
    }


def build_strengths(detail: Dict[str, Any]) -> List[str]:
    """B2B Strengths: Business advantages only (concise, actionable)"""
    engagement_rate = _safe_float(detail.get("engagement_rate", 0))
    real_pct = _safe_float(detail.get("real_percentage", detail.get("real_followers_percentage", 0)))
    is_verified = detail.get("is_verified", False)
    
    # Safely extract posts count - handle list, string, or number
    posts_raw = detail.get("posts", 0)
    posts = 0
    if posts_raw:
        if isinstance(posts_raw, (int, float)):
            posts = int(posts_raw)
        elif isinstance(posts_raw, list):
            posts = len(posts_raw)  # If it's a list, use length
        else:
            posts = _safe_float(posts_raw, 0) or 0
            if posts:
                posts = int(posts)

    strengths = []

    if engagement_rate and engagement_rate > 0.05:
        strengths.append("Above-average audience interaction improves campaign ROI")
    elif engagement_rate and engagement_rate > 0.03:
        strengths.append("Standard engagement levels suitable for brand collaborations")

    if real_pct and real_pct > 80:
        strengths.append("High follower authenticity reduces brand risk and improves conversion")
    elif real_pct and real_pct > 65:
        strengths.append("Adequate audience quality for standard campaigns")

    if is_verified:
        strengths.append("Verified account status adds brand credibility and trust")

    if posts and posts > 500:
        strengths.append("Extensive content library demonstrates reliability and consistency")

    return strengths if strengths else ["Suitable for initial campaign testing"]


def build_weaknesses(detail: Dict[str, Any]) -> List[str]:
    """B2B Weaknesses: Business risks and concerns only (actionable mitigation)"""
    engagement_rate = _safe_float(detail.get("engagement_rate", 0))
    real_pct = _safe_float(detail.get("real_percentage", detail.get("real_followers_percentage", 0)))
    suspicious = detail.get("suspicious_fake_followers", 0)
    is_verified = detail.get("is_verified", False)

    weaknesses = []

    if engagement_rate and engagement_rate < 0.02:
        weaknesses.append("Low engagement may reduce campaign effectiveness - recommend pilot before commitment")
    elif engagement_rate and engagement_rate < 0.03:
        weaknesses.append("Below-average engagement requires performance monitoring")

    if real_pct and real_pct < 50:
        weaknesses.append("High fake follower ratio requires contract safeguards and quarterly audits")
    elif real_pct and real_pct < 70:
        weaknesses.append("Moderate authenticity concerns - recommend performance guarantees")

    if not is_verified and suspicious > 5000:
        weaknesses.append("Unverified account with significant bot activity presents brand safety risk")

    if not weaknesses:
        weaknesses.append("Standard influencer partnership risks apply")

    return weaknesses

class AIInsightsGenerator:
    """Generate influencer insights using OpenAI API - NO FALLBACKS."""
    
    @staticmethod
    def generate_insights(detail: Dict[str, Any], user_prompt: Optional[str] = None) -> Dict[str, Any]:
        """Generate comprehensive AI insights using OpenAI API ONLY - with retries, NO fallbacks."""
        from app.services.llm.agent_service import generate_openai_insights
        import time
        
        max_retries = 3
        for attempt in range(max_retries):
            try:
                logger.debug(f"🔄 Attempt {attempt + 1}/{max_retries}: Generating OpenAI insights for influencer")
                insights = generate_openai_insights(detail=detail, user_prompt=user_prompt, model=None)
                if insights and isinstance(insights, dict) and (insights.get("strengths") or insights.get("weaknesses") or insights.get("verdict")):
                    logger.debug(f"✅ OpenAI generated comprehensive insights")
                    return insights
                else:
                    logger.warning(f"⚠️ LLM returned incomplete insights, attempt {attempt + 1}")
                    if attempt < max_retries - 1:
                        time.sleep(2)
                        continue
                    else:
                        raise ValueError("LLM returned incomplete insights after all retries")
            except Exception as exc:
                logger.exception(f"❌ LLM insights generation failed, attempt {attempt + 1}: {exc}")
                if attempt < max_retries - 1:
                    time.sleep(3)  # Wait longer before retry
                    continue
                else:
                    # Final attempt failed - raise exception instead of falling back
                    raise ValueError(f"LLM insights generation failed after {max_retries} attempts: {str(exc)}")
        
        # Should never reach here
        raise ValueError("Failed to generate LLM insights")

matplotlib.use("Agg")

logger = logging.getLogger(__name__)

LOGO_PATH = Path("/Users/mprince/Desktop/CreatosConnect/backend/app/static/logo.png")


# Natural, Vibrant Colors - Inspired by Nature
SOFT_COLORS = {
    'primary': colors.HexColor("#338AE1"),      # Deep Royal Blue (professional, saturated)
    'secondary': colors.HexColor("#5C0DE4"),    # Rich Purple (vivid)
    'accent1': colors.HexColor("#1BA14A"),      # Deep Emerald (saturated green)
    'accent2': colors.HexColor("#DD8928"),      # Rich Amber (warm, vibrant)
    'accent3': colors.HexColor("#1BA981"),      # Forest Green (natural, deep)
    'accent4': colors.HexColor("#2C69EC"),      # Vibrant Blue (bright)
    'text_dark': colors.HexColor('#111827'),    # Darker Gray (higher contrast)
    'text_light': colors.HexColor('#4B5563'),   # Medium Gray (readable)
    'white': colors.HexColor('#FFFFFF'),
    'background': colors.HexColor('#F9FAFB'),   # Light Background
    'grid': colors.HexColor('#D1D5DB'),         # Grid Gray (visible)
}

# Backward compatibility - map old names to new colors
PRIMARY_COLORS = {
    "coral": SOFT_COLORS['accent2'],
    "lavender": SOFT_COLORS['secondary'],
    "mint": SOFT_COLORS['accent1'],
    "sky": SOFT_COLORS['accent4'],
    "peach": SOFT_COLORS['accent2'],
    "aqua": SOFT_COLORS['accent4'],
    "gold": SOFT_COLORS['accent3'],
    "emerald": SOFT_COLORS['accent1'],
    "black": SOFT_COLORS['text_dark'],
    "white": SOFT_COLORS['white'],
    "light_gray": SOFT_COLORS['background'],
    "medium_gray": SOFT_COLORS['grid'],
    "dark_gray": SOFT_COLORS['text_light'],
}

# ============================================================================
# PROFESSIONAL TYPOGRAPHY SYSTEM
# ============================================================================

def get_typography_styles():
    """
    Professional typography hierarchy:
    - Display: Large titles (cover page)
    - H1: Main section headings
    - H2: Subsection headings
    - H3: Minor headings
    - Body: Regular content
    - Caption: Small notes, labels
    """
    base_styles = getSampleStyleSheet()
    
    styles = {
        'display': ParagraphStyle(
            'Display',
            parent=base_styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=48,
            leading=56,
            textColor=SOFT_COLORS['primary'],
            alignment=TA_CENTER,
            spaceAfter=24,
            spaceBefore=12,
            letterSpacing=2,
        ),
        
        'h1': ParagraphStyle(
            'Heading1',
            parent=base_styles['Heading1'],
            fontName='Helvetica-Bold',
            fontSize=32,
            leading=40,
            textColor=SOFT_COLORS['primary'],
            alignment=TA_LEFT,
            spaceAfter=20,
            spaceBefore=28,
            letterSpacing=1,
        ),
        
        'h2': ParagraphStyle(
            'Heading2',
            parent=base_styles['Heading2'],
            fontName='Helvetica-Bold',
            fontSize=24,
            leading=32,
            textColor=SOFT_COLORS['secondary'],
            alignment=TA_LEFT,
            spaceAfter=16,
            spaceBefore=24,
            letterSpacing=0.5,
        ),
        
        'h3': ParagraphStyle(
            'Heading3',
            parent=base_styles['Heading3'],
            fontName='Helvetica-Bold',
            fontSize=18,
            leading=24,
            textColor=SOFT_COLORS['text_dark'],
            alignment=TA_LEFT,
            spaceAfter=12,
            spaceBefore=16,
        ),
        
        'h4': ParagraphStyle(
            'Heading4',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=15,
            leading=20,
            textColor=SOFT_COLORS['text_dark'],
            alignment=TA_LEFT,
            spaceAfter=10,
            spaceBefore=14,
        ),
        
        'body': ParagraphStyle(
            'Body',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=11,
            leading=18,
            textColor=SOFT_COLORS['text_dark'],
            alignment=TA_JUSTIFY,
            spaceAfter=8,
            spaceBefore=0,
            firstLineIndent=0,
        ),
        
        'body_bold': ParagraphStyle(
            'BodyBold',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=11,
            leading=18,
            textColor=SOFT_COLORS['text_dark'],
            alignment=TA_LEFT,
            spaceAfter=8,
            spaceBefore=0,
        ),
        
        'caption': ParagraphStyle(
            'Caption',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=9,
            leading=13,
            textColor=SOFT_COLORS['text_light'],
            alignment=TA_LEFT,
            spaceAfter=6,
            spaceBefore=0,
        ),
        
        'label': ParagraphStyle(
            'Label',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=12,
            leading=16,
            textColor=SOFT_COLORS['text_dark'],
            alignment=TA_LEFT,
            spaceAfter=4,
            spaceBefore=0,
        ),
        
        'value': ParagraphStyle(
            'Value',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=12,
            leading=16,
            textColor=SOFT_COLORS['text_dark'],
            alignment=TA_LEFT,
            spaceAfter=4,
            spaceBefore=0,
        ),
        
        'highlight': ParagraphStyle(
            'Highlight',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=14,
            leading=20,
            textColor=SOFT_COLORS['secondary'],
            alignment=TA_CENTER,
            spaceAfter=10,
            spaceBefore=8,
        ),
        
        'username': ParagraphStyle(
            'Username',
            parent=base_styles['Normal'],
            fontName='Helvetica',
            fontSize=22,
            leading=28,
            textColor=SOFT_COLORS['text_light'],
            alignment=TA_CENTER,
            spaceAfter=16,
            spaceBefore=6,
            letterSpacing=1,
        ),
        
        'metric_large': ParagraphStyle(
            'MetricLarge',
            parent=base_styles['Normal'],
            fontName='Helvetica-Bold',
            fontSize=16,
            leading=22,
            textColor=SOFT_COLORS['text_dark'],
            alignment=TA_CENTER,
            spaceAfter=6,
            spaceBefore=4,
        ),
    }
    
    return styles


# =============================================================================
# Chart metric mapping (uses _safe_float / _format_* from PDF formatting block above)
# =============================================================================

def _map_metrics_for_charts(calculated_metrics: Dict[str, float], detail: Dict[str, Any]) -> Dict[str, float]:
    """
    Map calculated metric names to what chart generator expects.
    Also add derived metrics that charts need.
    """
    mapped = calculated_metrics.copy()

    # Helper to safely get values - handles string formats like "110.57k"
    def safe_get(key, default=0.0):
        val = mapped.get(key, detail.get(key, default))
        if val is None or val == "":
            return default

        try:
            # If it's already a number, return it
            if isinstance(val, (int, float)):
                return float(val)

            # If it's a string, try to parse it
            if isinstance(val, str):
                val = val.strip().replace("%", "")

                # Handle "N/A", "nan", etc.
                if val.lower() in ("n/a", "nan", "none", "null", ""):
                    return default

                # Handle formats like "110.57k", "1.2M", etc.
                if 'k' in val.lower() or 'm' in val.lower():
                    from app.services.core.search_filters import parse_followers_to_int
                    return float(parse_followers_to_int(val))

                # Try direct float conversion
                return float(val)

            return default
        except (ValueError, TypeError, AttributeError):
            return default

    # CRITICAL: Always ensure engagement_rate is present from detail if not in calculated.
    # We standardize on PERCENTAGE scale (0‑100) for engagement_rate across the app.
    if "engagement_rate" not in mapped:
        engagement_rate_val = detail.get("engagement_rate", 0.0)
        logger.debug(f"_map_metrics: engagement_rate from detail = {engagement_rate_val} (type: {type(engagement_rate_val)})")
        if engagement_rate_val:
            if isinstance(engagement_rate_val, str):
                engagement_rate_val = _safe_float(engagement_rate_val.replace("%", ""), 0.0) or 0.0
            else:
                engagement_rate_val = _safe_float(engagement_rate_val, 0.0) or 0.0
            # If value looks like a decimal (0‑1), convert it to percentage.

            # Cap engagement rate at 100% (can't exceed follower count)
            if engagement_rate_val > 100.0:
                logger.warning(
                    f"Engagement rate capped from {engagement_rate_val:.2f}% to 100% in PDF mapping"
                )
                engagement_rate_val = 100.0
            mapped["engagement_rate"] = engagement_rate_val

    # Calculate like_to_follower_ratio and comment_to_follower_ratio if not present
    followers = safe_get("followers", 0.0)
    avg_likes = safe_get("average_likes", 0.0) or safe_get("avg_likes", 0.0)
    avg_comments = safe_get("average_comments", 0.0) or safe_get("avg_comments", 0.0)

    if "like_to_follower_ratio" not in mapped and followers > 0 and avg_likes > 0:
        mapped["like_to_follower_ratio"] = (avg_likes / followers) * 100  # As percentage

    if "comment_to_follower_ratio" not in mapped and followers > 0 and avg_comments > 0:
        mapped["comment_to_follower_ratio"] = (avg_comments / followers) * 100  # As percentage

    # Map metric names to chart generator expectations
    # Chart generator expects: like_to_follower_ratio, comment_to_follower_ratio
    # Calculation creates: like_rate, comment_rate (as percentages)
    if "like_rate" in mapped and "like_to_follower_ratio" not in mapped:
        mapped["like_to_follower_ratio"] = safe_get("like_rate", 0.0)  # Already a percentage

    if "comment_rate" in mapped and "comment_to_follower_ratio" not in mapped:
        mapped["comment_to_follower_ratio"] = safe_get("comment_rate", 0.0)  # Already a percentage

    # Real/fake follower ratios - ALWAYS derive from detail data
    # Support multiple incoming key names and normalize to percentage float (0-100)
    real_pct = None
    for candidate in (
        "real_followers_percentage",
        "real_percentage",
        "real_pct",
        "real_follower_ratio",
        "real_followers_ratio",
        "real_followers",
    ):
        if candidate in detail and detail.get(candidate) is not None:
            real_pct = detail.get(candidate)
            break

    # If still not found, try nested metrics keys
    if real_pct is None and isinstance(calculated_metrics, dict):
        for candidate in ("real_follower_ratio", "real_percentage", "real_pct"):
            if candidate in calculated_metrics:
                real_pct = calculated_metrics.get(candidate)
                break

    # Normalize to numeric percentage (0-100)
    if isinstance(real_pct, str):
        real_pct = real_pct.strip()
        # allow values like '81.61' or '81.61%' or '0.8161'
        if real_pct.endswith("%"):
            real_pct = _safe_float(real_pct.replace("%", ""), 0.0) or 0.0
        else:
            parsed = _safe_float(real_pct, None)
            if parsed is None:
                real_pct = 0.0
            elif 0 < parsed <= 1:
                # fractional form -> convert to percent
                real_pct = parsed * 100.0
            else:
                real_pct = parsed
    elif isinstance(real_pct, (int, float)):
        # If value looks like fraction (0-1), convert to percent
        if 0 < float(real_pct) <= 1:
            real_pct = float(real_pct) * 100.0
        else:
            real_pct = float(real_pct)
    else:
        real_pct = 0.0

    # Suspicious / fake percentage: try multiple keys as well
    suspicious_pct = None
    for candidate in (
        "suspicious_followers_percentage",
        "suspicious_pct",
        "fake_follower_ratio",
        "fake_percentage",
        "fake_follower_pct",
    ):
        if candidate in detail and detail.get(candidate) is not None:
            suspicious_pct = detail.get(candidate)
            break

    if suspicious_pct is None and isinstance(calculated_metrics, dict):
        for candidate in ("fake_follower_ratio", "fake_percentage"):
            if candidate in calculated_metrics:
                suspicious_pct = calculated_metrics.get(candidate)
                break

    if isinstance(suspicious_pct, str):
        suspicious_pct = suspicious_pct.strip()
        if suspicious_pct.endswith("%"):
            suspicious_pct = _safe_float(suspicious_pct.replace("%", ""), 0.0) or 0.0
        else:
            parsed = _safe_float(suspicious_pct, None)
            if parsed is None:
                suspicious_pct = 0.0
            elif 0 < parsed <= 1:
                suspicious_pct = parsed * 100.0
            else:
                suspicious_pct = parsed
    elif isinstance(suspicious_pct, (int, float)):
        if 0 < float(suspicious_pct) <= 1:
            suspicious_pct = float(suspicious_pct) * 100.0
        else:
            suspicious_pct = float(suspicious_pct)
    else:
        suspicious_pct = None

    # If suspicious not provided, calculate from real
    if suspicious_pct is None:
        if real_pct and real_pct > 0:
            suspicious_pct = max(0.0, 100.0 - real_pct)
        else:
            suspicious_pct = 0.0

    # Final mapped values
    if "real_follower_ratio" not in mapped:
        mapped["real_follower_ratio"] = real_pct

    if "fake_follower_ratio" not in mapped:
        mapped["fake_follower_ratio"] = suspicious_pct
    
    # Comment depth ratio (ALLOWED METRIC)
    avg_likes = safe_get("average_likes", 0.0) or safe_get("avg_likes", 0.0)
    avg_comments = safe_get("average_comments", 0.0) or safe_get("avg_comments", 0.0)
    
    if "comment_depth_ratio" not in mapped:
        if avg_likes > 0:
            mapped["comment_depth_ratio"] = avg_comments / avg_likes
        else:
            mapped["comment_depth_ratio"] = 0.0
    
    # Remove all forbidden metrics if they exist
    forbidden_metrics = [
        "growth_saturation_index", "activity_saturation_index",
        "cost_per_follower", "cost_per_engagement", "cost_per_real_follower",
        "post_efficiency_score", "audience_interaction_score",
        "engagement_velocity", "health_score", "influencer_quality_score",
        "brand_fit_score"
    ]
    for metric in forbidden_metrics:
        mapped.pop(metric, None)
    
    return mapped


 # --- Cleans influencer name by removing extra characters. ---
def _clean_name(name: str) -> str:
    """Clean influencer name by removing extra characters like '()', '[]', etc."""
    if not name:
        return "Unknown Influencer"
    
    # Remove common patterns: "Name ()", "Name []", etc.
    name = re.sub(r'\s*\([^)]*\)\s*', '', name)  # Remove (content)
    name = re.sub(r'\s*\[[^\]]*\]\s*', '', name)  # Remove [content]
    name = re.sub(r'\s*\{[^}]*\}\s*', '', name)  # Remove {content}
    name = re.sub(r'\s+', ' ', name)  # Normalize whitespace
    name = name.strip()
    
    # Normalize Unicode characters
    try:
        name = unicodedata.normalize('NFKD', name)
        name = ''.join([c for c in name if not unicodedata.combining(c)])
    except Exception:
        pass
    
    # Escape XML special characters
    name = saxutils.escape(name)
    
    return name if name else "Unknown Influencer"


 # --- Highlights numeric values inside rich text. ---
def _highlight_numbers(text: str, bold_all: bool = False) -> str:
    """Highlight numbers with soft accent color."""
    if not isinstance(text, str):
        text = str(text)

    # Remove stray box/placeholder characters that show up in PDF (e.g., "■")
    text = text.replace("■", "")

    if '<font' in text or '<b>' in text:
        return text
    
    pattern = r'(₹\s*\d+(?:,\d{3})*(?:\.\d+)?|\d+(?:,\d{3})*(?:\.\d+)?%?)'
    
    def replace_number(match):
        num = match.group(1)
        return f'<font color="#FFB4A2" face="Helvetica-Bold">{num}</font>'
    
    highlighted = re.sub(pattern, replace_number, text)
    
    if bold_all:
        return f'<b>{highlighted}</b>'
    return highlighted


def _create_gradient_heading(text: str, size: str = "large") -> str:
    """Create modern gradient-style heading with soft colors."""
    if size == "large":
        return f'<font color="#8B9EB7" face="Helvetica-Bold" size="20">{text}</font>'
    else:
        words = text.split()
        if len(words) <= 2:
            return f'<font color="#B8A9C9" face="Helvetica-Bold">{text}</font>'
        
        colored_words = []
        colors_cycle = ["#8B9EB7", "#B8A9C9", "#A8D5BA", "#FFB4A2"]
        for i, word in enumerate(words):
            color = colors_cycle[i % len(colors_cycle)]
            colored_words.append(f'<font color="{color}">{word}</font>')
        return f'<b>{" ".join(colored_words)}</b>'


 # --- Creates a styled bullet‑list block. ---
def _list_block(items: List[str], body_style: ParagraphStyle) -> ListFlowable:
    """Create bulleted list."""
    flow_items: List[ListItem] = []
    for item in items or []:
        paragraph = Paragraph(item, body_style)
        flow_items.append(ListItem(paragraph, leftIndent=10))
    return ListFlowable(flow_items, bulletType="bullet", start=None, leftIndent=18)


def _add_l_shaped_border(canvas_obj: canvas.Canvas, doc) -> None:
    """Add modern complete border with soft colors."""
    width, height = A4
    canvas_obj.saveState()
    
    # Outer border (soft primary)
    canvas_obj.setStrokeColor(SOFT_COLORS['primary'])
    canvas_obj.setLineWidth(4)
    canvas_obj.line(0.4 * inch, 0.4 * inch, 0.4 * inch, height - 0.4 * inch)
    canvas_obj.line(0.4 * inch, 0.4 * inch, width - 0.4 * inch, 0.4 * inch)
    canvas_obj.line(width - 0.4 * inch, 0.4 * inch, width - 0.4 * inch, height - 0.4 * inch)
    canvas_obj.line(0.4 * inch, height - 0.4 * inch, width - 0.4 * inch, height - 0.4 * inch)
    
    # Inner accent border (soft secondary)
    canvas_obj.setStrokeColor(SOFT_COLORS['secondary'])
    canvas_obj.setLineWidth(2)
    canvas_obj.line(0.45 * inch, 0.45 * inch, 0.45 * inch, height - 0.45 * inch)
    canvas_obj.line(0.45 * inch, 0.45 * inch, width - 0.45 * inch, 0.45 * inch)
    canvas_obj.line(width - 0.45 * inch, 0.45 * inch, width - 0.45 * inch, height - 0.45 * inch)
    canvas_obj.line(0.45 * inch, height - 0.45 * inch, width - 0.45 * inch, height - 0.45 * inch)
    
    canvas_obj.restoreState()


 # --- Adds header, footer & watermark to pages. ---
def _add_header_footer(canvas_obj: canvas.Canvas, doc, is_last_page: bool = False) -> None:
    """Render header/footer with date only - professional styling."""
    width, height = A4
    canvas_obj.saveState()

    # Subtle watermark
    if LOGO_PATH.exists():
        try:
            canvas_obj.setFillAlpha(0.015)
            logo_width = width * 0.35
            logo_height = logo_width * 0.6
            canvas_obj.drawImage(
                str(LOGO_PATH),
                x=(width - logo_width) / 2,
                y=(height - logo_height) / 2,
                width=logo_width,
                height=logo_height,
                mask="auto",
            )
            canvas_obj.setFillAlpha(1)
        except Exception:
            pass

    # Footer text - professional styling (LEFT SIDE)
    canvas_obj.setFont('Helvetica-Bold', 10)
    canvas_obj.setFillColor(SOFT_COLORS['primary'])
    canvas_obj.drawString(0.6 * inch, 0.5 * inch, 'CreatorConnect Analytics')

    # Date on last page only (RIGHT SIDE - moved up to prevent border overlap)
    if is_last_page:
        from datetime import datetime
        date_only = datetime.now().strftime('%B %d, %Y')  # Only date, no time
        canvas_obj.setFont('Helvetica', 9)
        canvas_obj.setFillColor(SOFT_COLORS['text_light'])
        canvas_obj.drawRightString(width - 0.6 * inch, 0.5 * inch, f'Generated: {date_only}')  # Moved up from 0.44

    canvas_obj.restoreState()


 # --- Adds chart + explanation + insights to PDF. ---
def _add_chart_with_detailed_explanation(
    story: List[Any],
    chart_path: str,
    chart_title: str,
    explanation: str,
    key_insights: List[str],
    styles: Any,
    data_points: Optional[List[Tuple[str, str]]] = None,
    show_data_table: bool = False,
    force_page_break: bool = True,
    metric_tracker: Optional[MetricTracker] = None,
) -> None:
    """
    Add chart with comprehensive explanation below - one metric per page.
    CRITICAL: Explanations must be QUALITATIVE ONLY - no numeric values.
    """
    # Chart title - use same heading style as other sections for consistency
    typo = get_typography_styles()
    heading_style = typo['h1']
    
    # Add spacing before heading to match other sections
    story.append(Spacer(1, 0.3 * inch))
    
    # Decorative underline - match other sections
    line_table = Table([[""]], colWidths=[6.5 * inch])
    line_table.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 3, SOFT_COLORS['secondary'])]))

    # Chart image - larger size
    chart_file = Path(chart_path)
    image_added = False
    chart_elements = [
        Paragraph(chart_title.upper(), heading_style),
        line_table,
        Spacer(1, 0.2 * inch)
    ]

    if chart_file.exists() and chart_file.stat().st_size > 0:
        try:
            img = Image(chart_path, width=5.5 * inch, height=3.5 * inch)
            chart_elements.append(img)
            image_added = True
        except Exception as exc:
            logger.error("Failed to add chart %s: %s", chart_path, exc)
            image_added = False
    else:
        logger.warning("Chart file not found or empty: %s", chart_path)
        image_added = False

    if not image_added:
        error_style = ParagraphStyle(
            "ErrorStyle",
            parent=styles["Normal"],
            fontSize=10,
            textColor=SOFT_COLORS['text_light'],
            alignment=TA_CENTER,
            spaceAfter=12,
        )
        chart_elements.append(Paragraph(f"<i>[Chart: {chart_title} - Image not available]</i>", error_style))

    # Wrap title + line + image together to prevent page breaks
    story.append(KeepTogether(chart_elements))
    story.append(Spacer(1, 0.25 * inch))

    # Detailed explanation section with better formatting
    explanation_heading_style = ParagraphStyle(
        "ExplanationHeading",
        parent=styles["Normal"],
        fontSize=12,
        fontName="Helvetica-Bold",
        textColor=SOFT_COLORS['primary'],
        spaceAfter=10,
        spaceBefore=12,
        leftIndent=10,
    )

    explanation_body_style = ParagraphStyle(
        "ExplanationBody",
        parent=styles["Normal"],
        fontSize=10,
        leading=16,
        alignment=TA_JUSTIFY,
        textColor=SOFT_COLORS['text_dark'],
        spaceAfter=10,
        leftIndent=15,
        rightIndent=15,
    )

    # CRITICAL: Only show explanation OR key insights, not both (to avoid duplication)
    # If we have both, use key insights only (they're more concise)
    if key_insights and len(key_insights) > 0:
        # Show only key insights (no analysis paragraph to avoid duplication)
        # CRITICAL: Sanitize each insight to remove numeric values
        key_insights = [_sanitize_text_remove_metrics(insight, metric_tracker) for insight in key_insights if insight.strip()]
        try:
            story.append(Paragraph('<b>💡 Key Insights:</b>', explanation_heading_style))

            insights_style = ParagraphStyle(
                "InsightsStyle",
                parent=styles["Normal"],
                fontSize=10,
                leading=15,
                textColor=SOFT_COLORS['text_dark'],
                spaceAfter=6,
                leftIndent=20,
            )

            formatted_insights = []
            for insight in key_insights:
                try:
                    formatted_insights.append(_highlight_numbers(insight, bold_all=False))
                except Exception:
                    formatted_insights.append(insight)

            for formatted_insight in formatted_insights:
                story.append(Paragraph(f'• {formatted_insight}', insights_style))
        except Exception as insight_exc:
            logger.error("Failed to add insights: %s", insight_exc)
    elif explanation:
        # Only show explanation if no insights available
        try:
            story.append(Paragraph('<b>📊 Analysis:</b>', explanation_heading_style))
            # CRITICAL: Sanitize explanation to remove numeric values
            sanitized_explanation = _sanitize_text_remove_metrics(explanation, metric_tracker)
            story.append(Paragraph(_highlight_numbers(sanitized_explanation), explanation_body_style))
        except Exception as exp_exc:
            logger.error("Failed to add explanation: %s", exp_exc)

    # Only add page break if explicitly requested (for major section transitions)
    if force_page_break:
        story.append(Spacer(1, 0.2 * inch))  # Use spacer instead of hard page break


 # --- Builds the PDF cover page. ---
def _create_cover_page(detail: Dict[str, Any], styles: Any) -> List[Any]:
    """Create professional cover page with clear typography hierarchy."""
    story = []
    story.append(Spacer(1, 0.3 * inch))  # Reduced from 0.5

    # Logo section
    if LOGO_PATH.exists():
        try:
            story.append(Image(str(LOGO_PATH), width=2 * inch, height=2 * inch))  # Reduced from 2.5
            story.append(Spacer(1, 0.15 * inch))  # Reduced from 0.3
        except Exception:
            placeholder_style = ParagraphStyle(
                "LogoPlaceholder",
                parent=styles["Normal"],
                fontSize=24,  # Reduced from 28
                alignment=TA_CENTER,
                fontName="Helvetica-Bold",
                textColor=SOFT_COLORS['primary'],
            )
            story.append(Paragraph('<b>CREATORSCONNECT</b>', placeholder_style))
            story.append(Spacer(1, 0.15 * inch))  # Reduced from 0.3

    # Get typography styles
    typo = get_typography_styles()

    # Main title and decorative line - keep together
    title_elements = [
        Paragraph(
            '<font color="#1E40AF">INFLUENCER</font><br/>'  # Updated color
            '<font color="#7C3AED">ANALYTICS REPORT</font>',  # Updated color
            typo['display']
        ),
        Spacer(1, 0.15 * inch),  # Reduced from 0.25
    ]

    # Decorative line
    line_table = Table([[""]], colWidths=[6.5 * inch])
    line_table.setStyle(TableStyle([
        ('LINEABOVE', (0, 0), (-1, 0), 3, SOFT_COLORS['primary']),
        ('LINEBELOW', (0, 0), (-1, 0), 2, SOFT_COLORS['secondary']),
    ]))
    title_elements.append(line_table)
    title_elements.append(Spacer(1, 0.15 * inch))  # Reduced from 0.3

    story.append(KeepTogether(title_elements))

    # Influencer name, username, and platform - keep together
    influencer_name = detail.get("_normalized_name") or detail.get("name", "Unknown Influencer")
    username = detail.get("username") or detail.get("Username") or influencer_name

    # Profile Photo - Add circular profile image
    identity_elements = []
    profile_pic_url = (
        detail.get("profile_pic_url") or
        detail.get("profile_picture_url") or
        detail.get("profile_image") or
        detail.get("image")
    )

    if profile_pic_url:
        try:
            import requests
            import io

            # Download profile image
            response = requests.get(profile_pic_url, timeout=5)
            if response.status_code == 200:
                img_data = io.BytesIO(response.content)
                img = Image(img_data, width=1.5*inch, height=1.5*inch)  # Reduced from 2 inches
                # Center the image
                img.hAlign = 'CENTER'
                identity_elements.append(img)
                identity_elements.append(Spacer(1, 0.1 * inch))  # Reduced from 0.2
                logger.debug(f"✅ Added profile photo to PDF cover from {profile_pic_url}")
        except Exception as e:
            logger.warning(f"Failed to add profile photo to PDF: {e}")

    name_style = ParagraphStyle(
        'CoverName',
        parent=typo['h1'],
        fontSize=32,
        alignment=TA_CENTER,
        spaceAfter=8,
    )

    platform = detail.get('platform', 'Instagram').upper()
    badge_style = ParagraphStyle(
        'PlatformBadge',
        parent=typo['h3'],
        fontSize=18,
        textColor=SOFT_COLORS['white'],
        alignment=TA_CENTER,
        leading=24,
    )

    platform_table = Table(
        [[Paragraph(f'<b>{platform}</b>', badge_style)]],
        colWidths=[4.5 * inch]
    )
    platform_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), SOFT_COLORS['primary']),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 15),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 15),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BOX', (0, 0), (-1, -1), 2, SOFT_COLORS['secondary']),
        ('ROUNDEDCORNERS', [12, 12, 12, 12]),
    ]))

    # Add name, username, and platform to identity elements
    identity_elements.extend([
        Paragraph(f'<b>{influencer_name}</b>', name_style),
        Paragraph(f'@{username}', typo['username']),
        Spacer(1, 0.15 * inch),  # Reduced from 0.3
        platform_table,
        Spacer(1, 0.2 * inch)  # Reduced from 0.4
    ])

    story.append(KeepTogether(identity_elements))

    # CRITICAL: Remove numeric metrics from cover page - they appear in Profile Stats Card
    # Cover page shows only qualitative branding text
    story.append(Paragraph(
        '<b>Professional Influencer Analytics</b>',
        typo['metric_large']
    ))

    # Use PageBreak to ensure next section starts cleanly
    story.append(PageBreak())
    
    # PROFILE DETAILS Section - Right after cover page
    # Match the same heading style as other sections
    story.append(Spacer(1, 0.3 * inch))
    heading_style = typo['h1']
    story.append(Paragraph("PROFILE DETAILS", heading_style))
    profile_line = Table([[""]], colWidths=[6.5 * inch])
    profile_line.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 3, SOFT_COLORS['secondary'])]))
    story.append(profile_line)
    story.append(Spacer(1, 0.2 * inch))
    
    label_style = typo['label']
    value_style = typo['value']
    
    normalized_name = detail.get("_normalized_name") or detail.get("name") or detail.get("NAME") or "N/A"
    username = detail.get("username") or detail.get("Username") or normalized_name
    
    # Comprehensive profile data - only show fields with valid data
    profile_data = [
        [Paragraph('<b>Attribute</b>', label_style), Paragraph('<b>Details</b>', value_style)],
    ]
    
    # Add fields only if they have valid data (not N/A, not empty, not 0 for counts)
    if normalized_name and normalized_name not in ('N/A', '', 'Unknown'):
        profile_data.append([
            Paragraph('<b>Full Name</b>', label_style),
            Paragraph(f'<b>{normalized_name}</b>', value_style)
        ])
    
    if username and username not in ('N/A', '', 'Unknown'):
        profile_data.append([
            Paragraph('<b>Username</b>', label_style),
            Paragraph(_highlight_numbers(f'<b>@{username}</b>'), value_style)
        ])
    
    platform = detail.get("platform", "Instagram")
    if platform and platform not in ('N/A', ''):
        profile_data.append([
            Paragraph('<b>Platform</b>', label_style),
            Paragraph(f'<b>{platform.title()}</b>', value_style)
        ])
    
    profile_link = detail.get("PROFILE_LINK") or detail.get("profile_link") or f"instagram.com/{username}"
    if profile_link and profile_link not in ('N/A', ''):
        profile_data.append([
            Paragraph('<b>Instagram Profile</b>', label_style),
            Paragraph(f'{str(profile_link)[:60]}', value_style)
        ])
    
    niche = detail.get("niche") or detail.get("NICHE") or detail.get("category_name") or "N/A"
    if niche and niche not in ('N/A', '', 'General', 'Unknown'):
        profile_data.append([
            Paragraph('<b>Niche</b>', label_style),
            Paragraph(f'<b>{niche}</b>', value_style)
        ])
    
    biography = detail.get("biography", "")
    if biography and biography not in ('N/A', '', 'nan', 'None'):
        bio_text = str(biography)[:150] if len(str(biography)) > 150 else str(biography)
        profile_data.append([
            Paragraph('<b>Bio</b>', label_style),
            Paragraph(f'{bio_text}', value_style)
        ])
    
    category = detail.get("category_name") or detail.get("business_category_name", "")
    if category and category not in ('N/A', '', 'Creator', 'Unknown'):
        profile_data.append([
            Paragraph('<b>Category</b>', label_style),
            Paragraph(f'{category}', value_style)
        ])
    
    # Always show verification status
    profile_data.append([
        Paragraph('<b>Verified</b>', label_style),
        Paragraph(f'<b>{"✓ Verified" if detail.get("is_verified") else "Not Verified"}</b>', value_style)
    ])
    
    # Always show business account status
    profile_data.append([
        Paragraph('<b>Business Account</b>', label_style),
        Paragraph(f'<b>{"✓ Yes" if detail.get("is_business_account") else "Personal"}</b>', value_style)
    ])
    
    # Only show highlights if count > 0
    highlights_count = detail.get("highlights_count", 0)
    if highlights_count and highlights_count > 0:
        profile_data.append([
            Paragraph('<b>Highlights</b>', label_style),
            Paragraph(f'<b>{highlights_count}</b>', value_style)
        ])
    
    profile_table = Table(profile_data, colWidths=[2.8 * inch, 3.7 * inch])
    profile_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), SOFT_COLORS['primary']),
        ("TEXTCOLOR", (0, 0), (-1, 0), SOFT_COLORS['white']),
        ("FONTNAME", (0, 0), (-1, 0), 'Helvetica-Bold'),
        ("FONTSIZE", (0, 0), (-1, 0), 13),
        ("FONTNAME", (0, 1), (0, -1), 'Helvetica-Bold'),
        ("FONTNAME", (1, 1), (-1, -1), 'Helvetica'),
        ("FONTSIZE", (0, 1), (-1, -1), 12),
        ("TEXTCOLOR", (0, 1), (-1, -1), SOFT_COLORS['text_dark']),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 12),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 12),
        ("LEFTPADDING", (0, 0), (-1, -1), 15),
        ("RIGHTPADDING", (0, 0), (-1, -1), 15),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT_COLORS['background']]),
        ("BOX", (0, 0), (-1, -1), 2, SOFT_COLORS['grid']),
        ("GRID", (0, 0), (-1, -1), 1, SOFT_COLORS['grid']),
        ("LINEBELOW", (0, 0), (-1, 0), 2, SOFT_COLORS['secondary']),
    ]))
    # Wrap with KeepTogether
    story.append(KeepTogether([profile_table]))
    story.append(Spacer(1, 0.3 * inch))
    
    return story


 # --- Generates AI insight sections for dynamic data. ---
def _generate_dynamic_ai_insights(detail: Dict[str, Any], metric_tracker: Optional[MetricTracker] = None) -> Dict[str, Any]:
    """
    Generate AI insights for dynamic search results using OpenAI API ONLY - NO FALLBACKS.
    CRITICAL: All insights are sanitized to remove numeric values.
    """
    import time
    
    max_retries = 3
    for attempt in range(max_retries):
        try:
            logger.info(f"🔄 Attempt {attempt + 1}/{max_retries}: Generating OpenAI insights for dynamic search")
            insights = AIInsightsGenerator.generate_insights(detail)
            
            if insights and isinstance(insights, dict):
                # CRITICAL: Sanitize all AI-generated text to remove numeric metrics
                if metric_tracker:
                    if isinstance(insights.get("executive_summary"), str):
                        insights["executive_summary"] = _sanitize_text_remove_metrics(insights["executive_summary"], metric_tracker)
                    if isinstance(insights.get("strengths"), list):
                        insights["strengths"] = [_sanitize_text_remove_metrics(s, metric_tracker) for s in insights["strengths"] if s]
                    if isinstance(insights.get("weaknesses"), list):
                        insights["weaknesses"] = [_sanitize_text_remove_metrics(w, metric_tracker) for w in insights["weaknesses"] if w]
                    if isinstance(insights.get("verdict"), str):
                        insights["verdict"] = _sanitize_text_remove_metrics(insights["verdict"], metric_tracker)
                
                logger.debug(f"✅ OpenAI generated dynamic AI insights")
                return insights
            else:
                logger.warning(f"⚠️ OpenAI returned invalid insights, attempt {attempt + 1}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    raise ValueError("OpenAI returned invalid insights after all retries")
                    
        except Exception as exc:
            logger.exception(f"❌ OpenAI insights generation failed, attempt {attempt + 1}: {exc}")
            if attempt < max_retries - 1:
                time.sleep(3)  # Wait longer before retry
                continue
            else:
                # Final attempt failed - raise exception instead of falling back
                raise ValueError(f"OpenAI insights generation failed after {max_retries} attempts: {str(exc)}")
    
    # Should never reach here
    raise ValueError("Failed to generate OpenAI insights")


def _create_audience_quality_section(
    detail: Dict[str, Any],
    styles: Any,
    metric_tracker: Optional[MetricTracker] = None,
    data_validator: Optional[DataValidator] = None,
) -> List[Any]:
    """Create Audience Quality section with donut chart for real_follower_ratio / fake_follower_ratio."""
    story = []
    typo = get_typography_styles()
    heading_style = typo['h1']
    body_style = typo['body']
    subheading_style = typo['h3']
    
    # Get authenticity data
    real_pct = _safe_float(detail.get("real_percentage") or detail.get("real_followers_percentage") or detail.get("real_follower_ratio"), 0.0)
    fake_pct = _safe_float(detail.get("fake_follower_ratio") or detail.get("suspicious_followers_percentage"), 0.0)
    
    # If fake_pct not available, calculate from real
    if fake_pct == 0 and real_pct > 0:
        fake_pct = max(0.0, 100.0 - real_pct)
    elif real_pct == 0 and fake_pct > 0:
        real_pct = max(0.0, 100.0 - fake_pct)
    
    # Skip section if no authenticity data
    if real_pct == 0 and fake_pct == 0:
        return story
    
    # Page break before new section
    story.append(PageBreak())
    story.append(Paragraph("AUDIENCE AUTHENTICITY", heading_style))
    line = Table([[""]], colWidths=[6.5 * inch])
    line.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 3, SOFT_COLORS['secondary'])]))
    story.append(line)
    story.append(Spacer(1, 0.2 * inch))
    
    # Generate donut chart
    try:
        from app.utils.chart_utils import save_3d_donut_chart
        import tempfile
        from pathlib import Path
        
        tmpdir = Path(tempfile.mkdtemp())
        chart_title, chart_path = save_3d_donut_chart(
            labels=["Real Followers", "Suspicious Followers"],
            values=[real_pct, fake_pct],
            title="Follower Authenticity",
            prefix="audience_quality"
        )
        
        if chart_path and Path(chart_path).exists():
            img = Image(chart_path, width=5 * inch, height=4 * inch)
            story.append(img)
            story.append(Spacer(1, 0.2 * inch))
    except Exception as e:
        logger.warning(f"Failed to generate audience quality chart: {e}")
    
    # AI Insights (LLM GENERATED ONLY - 4-5 lines comprehensive analysis)
    story.append(Paragraph('<b>AI Insights</b>', subheading_style))
    
    try:
        from app.services.llm.agent_service import generate_section_insights
        import time
        
        section_payload = {
            "section_type": "Audience Authenticity",
            "real_followers_percentage": real_pct,
            "suspicious_followers_percentage": fake_pct,
        }
        
        section_name = (
            "Audience Authenticity Analysis - Generate comprehensive POSITIVE, data-driven, QUALITATIVE insights "
            "in 4-5 detailed sentences (minimum 4 sentences) about follower authenticity, real vs suspicious followers, "
            "brand safety, campaign risk assessment, and partnership suitability. Focus on what authenticity levels reveal "
            "about audience quality, campaign ROI potential, brand safety, and strategic partnership recommendations. "
            "Do NOT repeat generic statements. Be specific about authenticity implications and brand partnership value. "
            "CRITICAL: Do NOT mention engagement rate, followers count, or any other metrics - focus ONLY on authenticity and follower quality."
        )
        
        # Retry logic for LLM
        max_retries = 3
        interpretation = None
        for attempt in range(max_retries):
            try:
                logger.debug(f"🔄 Attempt {attempt + 1}/{max_retries}: Generating OpenAI insights for Audience Authenticity")
                interpretation = generate_section_insights(
                    detail=detail,
                    section_name=section_name,
                    section_data=section_payload,
                )
                if interpretation and interpretation.strip() and len(interpretation.strip()) > 50:
                    logger.debug(f"✅ OpenAI generated Audience Authenticity insights ({len(interpretation)} chars)")
                    break
                else:
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
            except Exception as e:
                logger.warning(f"⚠️ LLM attempt {attempt + 1} failed for Audience Authenticity: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    raise
        
        if interpretation and interpretation.strip():
            interpretation = _sanitize_text_remove_metrics(interpretation, metric_tracker, section_context="audience_authenticity")
            story.append(Paragraph(interpretation, body_style))
        else:
            raise ValueError("LLM returned empty Audience Authenticity insights")
            
    except Exception as e:
        logger.error(f"❌ Failed to generate LLM insights for Audience Authenticity: {e}")
        story.append(Paragraph("AI insights generation is in progress. Please regenerate the PDF.", body_style))
    
    # Mark metrics as shown
    if metric_tracker:
        metric_tracker.mark_shown("real_follower_ratio")
        metric_tracker.mark_shown("fake_follower_ratio")
        metric_tracker.mark_section("audience_quality")
    
    return story


def _create_engagement_quality_section(
    detail: Dict[str, Any],
    styles: Any,
    metric_tracker: Optional[MetricTracker] = None,
) -> List[Any]:
    """Create Engagement Quality section with combined bar chart for like_to_follower_ratio and comment_depth_ratio."""
    story = []
    typo = get_typography_styles()
    heading_style = typo['h1']
    body_style = typo['body']
    subheading_style = typo['h3']
    
    # Get engagement metrics
    metrics = detail.get("metrics", {})
    like_ratio = _safe_float(metrics.get("like_to_follower_ratio") or detail.get("like_to_follower_ratio"), 0.0)
    comment_depth = _safe_float(metrics.get("comment_depth_ratio") or detail.get("comment_depth_ratio"), 0.0)
    
    # Calculate if not available
    if like_ratio == 0:
        followers = _safe_float(detail.get("followers"), 0.0)
        avg_likes = _safe_float(detail.get("avg_likes") or detail.get("average_likes"), 0.0)
        if followers > 0 and avg_likes > 0:
            like_ratio = (avg_likes / followers) * 100
    
    if comment_depth == 0:
        avg_likes = _safe_float(detail.get("avg_likes") or detail.get("average_likes"), 0.0)
        avg_comments = _safe_float(detail.get("avg_comments") or detail.get("average_comments"), 0.0)
        if avg_likes > 0:
            comment_depth = (avg_comments / avg_likes)  # Keep as ratio (0-1 range typically)
    
    # Skip if no data
    if like_ratio == 0 and comment_depth == 0:
        return story
    
    # Page break before new section
    story.append(PageBreak())
    story.append(Paragraph("ENGAGEMENT QUALITY", heading_style))
    line = Table([[""]], colWidths=[6.5 * inch])
    line.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 3, SOFT_COLORS['secondary'])]))
    story.append(line)
    story.append(Spacer(1, 0.2 * inch))
    
    # Generate combined bar chart with proper scale
    try:
        from app.utils.chart_utils import save_bar_chart_simple
        import tempfile
        from pathlib import Path
        
        tmpdir = Path(tempfile.mkdtemp())
        
        # Combine both metrics into one chart with normalized scale
        labels = []
        values = []
        
        if like_ratio > 0:
            labels.append("Like to Follower Ratio")
            values.append(like_ratio)
        
        if comment_depth > 0:
            labels.append("Comment Depth Ratio")
            values.append(comment_depth)
        
        if labels and values:
            # Normalize both metrics to same scale for proper comparison
            # like_ratio is already in percentage (0-100), comment_depth is ratio (0-1 typically)
            # Convert comment_depth to percentage scale for fair comparison
            normalized_values = []
            for i, val in enumerate(values):
                if i == 1 and val < 1:  # comment_depth is typically < 1, convert to percentage
                    normalized_values.append(val * 100)
                else:  # like_ratio is already percentage
                    normalized_values.append(val)
            
            chart_title, chart_path = save_bar_chart_simple(
                labels=labels,
                values=normalized_values,
                title="Engagement Quality Metrics",
                ylabel="Percentage (%)",
                prefix="engagement_quality_combined"
            )
            if chart_path and Path(chart_path).exists():
                img = Image(chart_path, width=5 * inch, height=3.5 * inch)
                story.append(img)
                story.append(Spacer(1, 0.2 * inch))
    except Exception as e:
        logger.warning(f"Failed to generate engagement quality charts: {e}")
    
    # AI Insights (LLM GENERATED ONLY - 4-5 lines comprehensive analysis)
    story.append(Paragraph('<b>AI Insights</b>', subheading_style))
    
    try:
        from app.services.llm.agent_service import generate_section_insights
        import time
        
        section_payload = {
            "section_type": "Engagement Quality",
            "like_to_follower_ratio": like_ratio,
            "comment_depth_ratio": comment_depth,
        }
        
        section_name = (
            "Engagement Quality Analysis - Generate comprehensive POSITIVE, data-driven, QUALITATIVE insights "
            "in 4-5 detailed sentences (minimum 4 sentences) about engagement quality metrics including like-to-follower "
            "ratio and comment depth ratio. Focus on what these metrics reveal about audience intent, interaction depth, "
            "content resonance, campaign potential, and brand partnership suitability. Do NOT repeat generic statements. "
            "Be specific about engagement patterns and their implications for campaign planning and brand partnerships. "
            "CRITICAL: Do NOT mention engagement rate percentage - focus ONLY on engagement quality metrics (like-to-follower ratio, comment depth)."
        )
        
        # Retry logic for LLM
        max_retries = 3
        interpretation = None
        for attempt in range(max_retries):
            try:
                logger.debug(f"🔄 Attempt {attempt + 1}/{max_retries}: Generating OpenAI insights for Engagement Quality")
                interpretation = generate_section_insights(
                    detail=detail,
                    section_name=section_name,
                    section_data=section_payload,
                )
                if interpretation and interpretation.strip() and len(interpretation.strip()) > 50:
                    logger.debug(f"✅ OpenAI generated Engagement Quality insights ({len(interpretation)} chars)")
                    break
                else:
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
            except Exception as e:
                logger.warning(f"⚠️ LLM attempt {attempt + 1} failed for Engagement Quality: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    raise
        
        if interpretation and interpretation.strip():
            interpretation = _sanitize_text_remove_metrics(interpretation, metric_tracker, section_context="engagement_quality")
            story.append(Paragraph(interpretation, body_style))
        else:
            raise ValueError("LLM returned empty Engagement Quality insights")
            
    except Exception as e:
        logger.error(f"❌ Failed to generate LLM insights for Engagement Quality: {e}")
        story.append(Paragraph("AI insights generation is in progress. Please regenerate the PDF.", body_style))
    
    # Mark metrics as shown
    if metric_tracker:
        metric_tracker.mark_shown("like_to_follower_ratio")
        metric_tracker.mark_shown("comment_depth_ratio")
        metric_tracker.mark_section("engagement_quality")
    
    return story


def _create_final_recommendation_section(
    detail: Dict[str, Any],
    insights: Dict[str, Any],
    styles: Any,
    metric_tracker: Optional[MetricTracker] = None,
) -> List[Any]:
    """Create Final Recommendation section - text only, no metrics, no charts."""
    story = []
    typo = get_typography_styles()
    heading_style = typo['h1']
    body_style = typo['body']
    subheading_style = typo['h3']
    
    # Page break before new section
    story.append(PageBreak())
    story.append(Paragraph("FINAL RECOMMENDATION", heading_style))
    line = Table([[""]], colWidths=[6.5 * inch])
    line.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 3, SOFT_COLORS['secondary'])]))
    story.append(line)
    story.append(Spacer(1, 0.2 * inch))
    
    # Get verdict from executive summary
    exec_data = build_executive_summary_text(detail)
    verdict = exec_data.get("verdict", "Pilot Only - requires verification")
    
    # Suitability
    story.append(Paragraph('<b>Suitability</b>', subheading_style))
    story.append(Paragraph(verdict, body_style))
    story.append(Spacer(1, 0.15 * inch))
    
    # Monitoring recommendation
    story.append(Paragraph('<b>Monitoring Recommendation</b>', subheading_style))
    if "Recommended" in verdict:
        monitoring = "Standard performance monitoring recommended. Track campaign KPIs including reach, engagement, and conversion metrics on a weekly basis."
    else:
        monitoring = "Enhanced monitoring required. Implement weekly performance reviews and quarterly authenticity audits to ensure campaign effectiveness."
    story.append(Paragraph(monitoring, body_style))
    story.append(Spacer(1, 0.15 * inch))
    
    # Campaign type fit
    story.append(Paragraph('<b>Campaign Type Fit</b>', subheading_style))
    engagement_rate = _safe_float(detail.get("engagement_rate", 0), 0.0)

    
    if engagement_rate > 5:
        campaign_fit = "Suitable for high-engagement campaigns including product launches, brand awareness, and community building initiatives."
    elif engagement_rate > 3:
        campaign_fit = "Ideal for standard brand partnerships, sponsored content, and promotional campaigns with defined KPIs."
    else:
        campaign_fit = "Best suited for reach-focused campaigns and brand exposure initiatives. Consider pilot programs before long-term commitments."
    
    story.append(Paragraph(campaign_fit, body_style))
    
    # Mark conclusion
    if metric_tracker:
        metric_tracker.mark_conclusion("final_recommendation")
        metric_tracker.mark_section("final_recommendation")
    
    return story


 # --- Generates full multi‑page analysis & charts. ---

def _add_post_analysis_section(story, detail, chart_assets, styles, metric_tracker):
    """
    Add a dedicated section for post analysis with deep insights and specific charts.
    Extracts data from raw posts if LLM post_analysis is not available.
    """
    post_analysis = detail.get("post_analysis", {})
    posts_data = detail.get("posts", [])
    has_post_charts = any("post" in t[0].lower() or "content" in t[0].lower() or "timeline" in t[0].lower() for t in chart_assets) if chart_assets else False
    
    # Check if we have ANY post-related data to show
    has_post_data = (
        post_analysis.get("post_analysis_available") or 
        (isinstance(posts_data, list) and len(posts_data) > 0) or
        has_post_charts or
        post_analysis.get("top_performing_content_type") or
        post_analysis.get("best_hashtags")
    )
    
    if not has_post_data:
        logger.debug("⏭️ Skipping Post Analysis section - no post data available")
        return
    
    logger.debug("📝 Adding Post Analysis section to PDF")
    
    
    # Section Header - ensure it starts on new page
    story.append(PageBreak())

    # 1. High-level Insights Grid
    insights_data = []
    
    # Top Content Type (from LLM analysis)
    content_type_val = post_analysis.get('top_performing_content_type')
    if content_type_val:
        insights_data.append(["Top Content Type", content_type_val])
    
    # Posting Frequency
    if post_analysis.get('posting_frequency'):
        insights_data.append(["Posting Frequency", post_analysis['posting_frequency']])
        
    # Engagement Quality
    if post_analysis.get('engagement_quality'):
        insights_data.append(["Engagement Quality", post_analysis['engagement_quality']])
    
    # Removed "Posts Analyzed" line as requested
    
        
    if insights_data:
        table_data = [[Paragraph(f"<b>{row[0]}:</b> {row[1]}", styles['Normal']) for row in insights_data]]
        col_width = 6.5 * inch / len(insights_data)
        t = Table(table_data, colWidths=[col_width] * len(insights_data))
        t.setStyle(TableStyle([
            ('VALIGN', (0,0), (-1,-1), 'TOP'),
            ('BOX', (0,0), (-1,-1), 1, SOFT_COLORS['grid']),
            ('BACKGROUND', (0,0), (-1,-1), SOFT_COLORS['background']),
            ('LEFTPADDING', (0,0), (-1,-1), 10),
            ('RIGHTPADDING', (0,0), (-1,-1), 10),
            ('TOPPADDING', (0,0), (-1,-1), 10),
            ('BOTTOMPADDING', (0,0), (-1,-1), 10),
        ]))
        story.append(t)
        story.append(Spacer(1, 0.2 * inch))

    # 2. Content Type Distribution (from extracted or LLM)
    typo = get_typography_styles()
    subheading_style = typo['h3']
    body_style = typo['body']
    
    # 3. Key Themes & Hashtags
    themes = post_analysis.get('content_themes', [])
    hashtags = post_analysis.get('best_hashtags', [])
    
    if themes or hashtags:
        col1_content = []
        if themes:
            col1_content.append(Paragraph("<b>Content Themes</b>", subheading_style))
            for theme in themes[:5]:
                col1_content.append(Paragraph(f"• {theme}", body_style))
                
        col2_content = []
        if hashtags:
            col2_content.append(Paragraph("<b>Top Hashtags</b>", subheading_style))
            hashtag_str = ", ".join([f"#{h}" if not str(h).startswith('#') else str(h) for h in hashtags[:8]])
            col2_content.append(Paragraph(hashtag_str, body_style))
            
        if col1_content or col2_content:
            data = [[col1_content if col1_content else [Spacer(1, 0.1*inch)], col2_content if col2_content else [Spacer(1, 0.1*inch)]]]
            t = Table(data, colWidths=[3.2 * inch, 3.2 * inch])
            t.setStyle(TableStyle([('VALIGN', (0,0), (-1,-1), 'TOP')]))
            story.append(t)
            story.append(Spacer(1, 0.2 * inch))

    # 4. LLM Deep Insights
    if post_analysis.get('key_insights'):
        story.append(Paragraph("Strategic Insights", subheading_style))
        for insight in post_analysis['key_insights']:
            story.append(Paragraph(f"• {insight}", body_style))
        story.append(Spacer(1, 0.2 * inch))

    # 5. Recent Posts Analysis - Point-wise Graph
    if isinstance(posts_data, list) and len(posts_data) > 0:
        # Use proper heading style like other sections
        typo = get_typography_styles()
        heading_style = typo['h1']
        story.append(Paragraph("RECENT POSTS ANALYSIS", heading_style))
        line = Table([[""]], colWidths=[6.5 * inch])
        line.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 3, SOFT_COLORS['secondary'])]))
        story.append(line)
        story.append(Spacer(1, 0.2 * inch))
        
        # Generate point-wise graph for posts
        try:
            from app.utils.chart_utils import save_posts_engagement_chart
            from pathlib import Path
            import tempfile
            
            # Prepare data for graph
            chart_title, chart_path = save_posts_engagement_chart(
                posts_data[:12],  # Show up to 12 most recent posts
                "Recent Posts Engagement",
                prefix=f"post_analysis_{detail.get('Id', 'unknown')}"
            )
            
            if chart_path and Path(chart_path).exists():
                img = Image(chart_path, width=6.5 * inch, height=4.5 * inch)
                story.append(img)
                story.append(Spacer(1, 0.3 * inch))
            else:
                logger.warning("Failed to generate posts engagement chart")
        except Exception as e:
            logger.warning(f"Failed to create posts engagement chart: {e}")
            # Fallback: show simple text summary
            story.append(Paragraph(f"Analyzed {len(posts_data)} recent posts with engagement data.", body_style))
            story.append(Spacer(1, 0.2 * inch))
    
    # 6. AI Insights for Post Analysis Section
    try:
        from app.services.llm.agent_service import generate_section_insights
        import time
        
        # Prepare section-specific data for AI
        section_payload = {
            "section_type": "Post Analysis & Content Strategy",
            "posts_count": len(posts_data) if isinstance(posts_data, list) else 0,
            "top_content_type": post_analysis.get('top_performing_content_type'),
            "posting_frequency": post_analysis.get('posting_frequency'),
            "content_themes": post_analysis.get('content_themes', [])[:5],
            "best_hashtags": post_analysis.get('best_hashtags', [])[:8],
        }
        
        section_name = (
            "Post Analysis & Content Strategy - Generate comprehensive POSITIVE, data-driven, QUALITATIVE insights "
            "in 4-5 detailed sentences (minimum 4 sentences) about the influencer's content strategy, posting patterns, "
            "content themes, hashtag usage, and content performance. Focus on what the content strategy reveals about "
            "brand partnership potential, content quality, audience engagement patterns, and strategic value for campaigns. "
            "Do NOT mention specific numbers (e.g., '12 posts', '3.1M followers', '3.34% engagement rate') as they are visible "
            "in the visuals above. Focus on the *implications* of the content strategy for brand partnerships. "
            "Do NOT repeat information from other sections. Be specific about content strategy implications. "
            "CRITICAL: Do NOT mention engagement rate, followers count, or any other profile metrics - focus ONLY on content strategy, posting patterns, themes, and hashtag usage."
        )
        
        # Retry logic for LLM
        max_retries = 3
        post_insights = None
        for attempt in range(max_retries):
            try:
                post_insights = generate_section_insights(
                    detail=detail,
                    section_name=section_name,
                    section_data=section_payload,
                )
                if post_insights and post_insights.strip() and len(post_insights.strip()) > 50:
                    break
                else:
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
                else:
                    logger.warning(f"Failed to generate Post Analysis insights: {e}")
        
        if post_insights and post_insights.strip():
            # Sanitize to remove any metrics that shouldn't be in this section
            post_insights = _sanitize_text_remove_metrics(post_insights, metric_tracker, section_context="post_analysis")
            story.append(Paragraph("<b>AI Insights</b>", subheading_style))
            story.append(Paragraph(post_insights, body_style))
            story.append(Spacer(1, 0.2 * inch))
    except Exception as e:
        logger.warning(f"Failed to generate Post Analysis AI insights: {e}")
    
    # 7. Post Charts - only if they exist
    post_charts = []
    target_keywords = ['content format', 'activity timeline', 'posting behavior', 'content activity']
    
    if chart_assets:
        for title, path in chart_assets:
            title_lower = title.lower()
            if any(x in title_lower for x in target_keywords):
                if path and Path(path).exists() and Path(path).stat().st_size > 0:
                    post_charts.append((title, path))

    for chart_title, chart_path in post_charts:
        try:
            explanation, key_insights = generate_chart_ai_content(
                detail, chart_title, {}, metric_tracker
            )
            _add_chart_with_detailed_explanation(
                story, chart_path, chart_title, explanation,
                key_insights or [], styles, force_page_break=False,
                metric_tracker=metric_tracker
            )
        except Exception as e:
            logger.error(f"Failed to add post chart {chart_title}: {e}")

def _create_detailed_analysis_with_charts(
    detail: Dict[str, Any],
    insights: Dict[str, Any],
    chart_assets: List[Tuple[str, str]],
    styles: Any,
    metric_tracker: Optional[Any] = None,
    data_validator: Optional[DataValidator] = None,
    benchmarks: Optional[Dict[str, Any]] = None,
    current_page_count: int = 0,
    max_pages: int = 18,
) -> List[Any]:
    """Create detailed multi-page analysis with charts and explanations."""
    story = []
    typo = get_typography_styles()
    
    heading_style = typo['h1']
    body_style = typo['body']
    subheading_style = typo['h3']
    label_style = typo['label']
    value_style = typo['value']
    
    # 1. PROFILE OVERVIEW & HERO STATS
    # Use spacer instead of hard page break
    story.append(Spacer(1, 0.3 * inch))
    story.append(Paragraph("PROFILE ANALYTICS", heading_style))
    line = Table([[""]], colWidths=[6.5 * inch])
    line.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 3, COLORS['secondary'])]))
    story.append(line)
    story.append(Spacer(1, 0.2 * inch))
    
    # Create Key Metrics Table (without profile information)
    story.append(Paragraph('<b>Key Metrics</b>', subheading_style))
    story.append(Spacer(1, 0.15 * inch))
    
    # Extract followers and following
    followers = detail.get("followers") or detail.get("metrics", {}).get("followers", 0)
    following = detail.get("following") or detail.get("metrics", {}).get("following", 0)
    
    # Format followers
    try:
        if isinstance(followers, str):
            from app.services.core.search_filters import parse_followers_to_int
            followers = parse_followers_to_int(followers)
        followers_val = float(followers) if followers else 0.0
        if followers_val >= 1_000_000:
            followers_str = f"{followers_val/1_000_000:.2f}M"
        elif followers_val >= 1_000:
            followers_str = f"{followers_val/1_000:.1f}K"
        else:
            followers_str = f"{int(followers_val):,}"
    except (ValueError, TypeError):
        followers_str = "N/A"
    
    # Format following
    try:
        following_val = float(following) if following else 0.0
        if following_val >= 1_000:
            following_str = f"{following_val/1_000:.1f}K"
        else:
            following_str = f"{int(following_val):,}"
    except (ValueError, TypeError):
        following_str = "N/A"
    
    # Extract metrics from detail
    engagement_rate = detail.get("engagement_rate") or detail.get("metrics", {}).get("engagement_rate", 0)
    avg_likes = detail.get("average_likes") or detail.get("avg_likes") or detail.get("metrics", {}).get("average_likes", 0) or detail.get("metrics", {}).get("avg_likes", 0)
    avg_comments = detail.get("average_comments") or detail.get("avg_comments") or detail.get("metrics", {}).get("average_comments", 0) or detail.get("metrics", {}).get("avg_comments", 0)
    
    # Get total posts - prioritize posts_count (actual total) over posts (which might be a sample list)
    # Check multiple possible locations and field names
    total_posts = (
        detail.get("posts_count") or 
        detail.get("POSTS_COUNT") or
        detail.get("metrics", {}).get("posts_count", 0) or
        detail.get("metrics", {}).get("POSTS_COUNT", 0)
    )
    
    # If posts_count is not available, check if posts is a number (not a list)
    if not total_posts or total_posts == 0:
        posts_raw = detail.get("posts") or detail.get("POSTS") or detail.get("metrics", {}).get("posts", 0)
        if posts_raw and not isinstance(posts_raw, list):
            # posts is a number, use it
            try:
                total_posts = float(posts_raw) if posts_raw else 0
            except (ValueError, TypeError):
                total_posts = 0
        # DO NOT use len(posts_raw) if posts is a list - that's sample posts, not total count
        # Only use it as absolute last resort if we have no other option
        elif posts_raw and isinstance(posts_raw, list) and not detail.get("posts_count") and not detail.get("POSTS_COUNT"):
            # This is a fallback - ideally posts_count should always be available
            # But if we truly have no posts_count anywhere, use list length as last resort
            total_posts = len(posts_raw)
        else:
            total_posts = 0
    
    # Format engagement rate
    try:
        if isinstance(engagement_rate, str):
            engagement_rate = float(str(engagement_rate).replace("%", "").strip())
        else:
            engagement_rate = float(engagement_rate) if engagement_rate else 0.0
        # If it's a decimal (0-1), convert to percentage

        engagement_rate_str = f"{engagement_rate:.2f}%"
    except (ValueError, TypeError):
        engagement_rate_str = "N/A"
    
    # Format avg likes
    try:
        avg_likes_val = float(avg_likes) if avg_likes else 0.0
        if avg_likes_val >= 1_000_000:
            avg_likes_str = f"{avg_likes_val/1_000_000:.2f}M"
        elif avg_likes_val >= 1_000:
            avg_likes_str = f"{avg_likes_val/1_000:.1f}K"
        else:
            avg_likes_str = f"{int(avg_likes_val):,}"
    except (ValueError, TypeError):
        avg_likes_str = "N/A"
    
    # Format avg comments
    try:
        avg_comments_val = float(avg_comments) if avg_comments else 0.0
        if avg_comments_val >= 1_000_000:
            avg_comments_str = f"{avg_comments_val/1_000_000:.2f}M"
        elif avg_comments_val >= 1_000:
            avg_comments_str = f"{avg_comments_val/1_000:.1f}K"
        else:
            avg_comments_str = f"{int(avg_comments_val):,}"
    except (ValueError, TypeError):
        avg_comments_str = "N/A"
    
    # Format total posts
    try:
        # total_posts should already be a number at this point (not a list)
        # But handle list case just in case
        if isinstance(total_posts, list):
            total_posts_val = float(len(total_posts))
        else:
            total_posts_val = float(total_posts) if total_posts else 0.0
        if total_posts_val >= 1_000_000:
            total_posts_str = f"{total_posts_val/1_000_000:.2f}M"
        elif total_posts_val >= 1_000:
            total_posts_str = f"{total_posts_val/1_000:.1f}K"
        else:
            total_posts_str = f"{int(total_posts_val):,}"
    except (ValueError, TypeError):
        total_posts_str = "N/A"
    
    # Create Key Metrics table (only metrics, no profile information)
    metrics_data = [
        ["Metric", "Value"],
        ["Followers", followers_str],
        ["Following", following_str],
        ["Engagement Rate", engagement_rate_str],
        ["Avg Likes", avg_likes_str],
        ["Avg Comments", avg_comments_str],
        ["Total Posts", total_posts_str],
    ]
    
    # Create styled table with theme colors
    metrics_table = Table(metrics_data, colWidths=[2.5*inch, 4.0*inch], repeatRows=1)
    metrics_table.setStyle(TableStyle([
        # Header row styling
        ('BACKGROUND', (0, 0), (-1, 0), SOFT_COLORS['secondary']),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 13),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 14),
        ('TOPPADDING', (0, 0), (-1, 0), 14),
        # Data rows styling
        ('BACKGROUND', (0, 1), (-1, -1), colors.white),
        ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 11),
        # Label column styling (bold)
        ('FONTNAME', (0, 1), (0, -1), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0, 1), (0, -1), SOFT_COLORS['text_dark']),
        # Value column styling
        ('TEXTCOLOR', (1, 1), (1, -1), SOFT_COLORS['text_light']),
        # Grid and borders
        ('GRID', (0, 0), (-1, -1), 1, SOFT_COLORS['grid']),
        ('LINEBELOW', (0, 0), (-1, 0), 2, colors.white),
        # Alignment and padding
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 14),
        ('RIGHTPADDING', (0, 0), (-1, -1), 14),
        ('TOPPADDING', (0, 1), (-1, -1), 10),
        ('BOTTOMPADDING', (0, 1), (-1, -1), 10),
        # Alternating row backgrounds
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, SOFT_COLORS['background']]),
    ]))
    story.append(metrics_table)
    story.append(Spacer(1, 0.3 * inch))
    
    # Add AI Insights for Key Metrics section
    try:
        from app.services.llm.agent_service import generate_section_insights
        import time
        
        section_payload = {
            "section_type": "Key Metrics Analysis",
            "followers": followers_str,
            "following": following_str,
            "engagement_rate": engagement_rate_str,
            "avg_likes": avg_likes_str,
            "avg_comments": avg_comments_str,
            "total_posts": total_posts_str,
        }
        
        section_name = (
            "Key Metrics Analysis - Generate comprehensive POSITIVE, data-driven, QUALITATIVE insights "
            "in 4-5 detailed sentences (minimum 4 sentences) about the influencer's key performance metrics including "
            "followers, following, engagement rate, average likes, average comments, and total posts. Focus on what these "
            "metrics reveal about audience size, engagement quality, content performance, and strategic value for brand partnerships. "
            "Do NOT mention specific numbers (e.g., '3.1M followers', '3.34% engagement rate') as they are visible in the table above. "
            "Focus on the *implications* and *strategic value* of these metrics for campaign planning and brand partnerships. "
            "Be specific about what these metrics indicate about the influencer's market position and partnership potential."
        )
        
        # Retry logic for LLM
        max_retries = 3
        key_metrics_insights = None
        for attempt in range(max_retries):
            try:
                logger.debug(f"🔄 Attempt {attempt + 1}/{max_retries}: Generating OpenAI insights for Key Metrics")
                key_metrics_insights = generate_section_insights(
                    detail=detail,
                    section_name=section_name,
                    section_data=section_payload,
                )
                if key_metrics_insights and key_metrics_insights.strip() and len(key_metrics_insights.strip()) > 50:
                    logger.debug(f"✅ OpenAI generated Key Metrics insights ({len(key_metrics_insights)} chars)")
                    break
                else:
                    if attempt < max_retries - 1:
                        time.sleep(1)
                        continue
            except Exception as e:
                logger.warning(f"⚠️ LLM attempt {attempt + 1} failed for Key Metrics: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
        
        if key_metrics_insights and key_metrics_insights.strip():
            # Sanitize to remove any metrics that shouldn't be in this section
            key_metrics_insights = _sanitize_text_remove_metrics(key_metrics_insights, metric_tracker, section_context="key_metrics")
            story.append(Paragraph("<b>AI Insights</b>", subheading_style))
            story.append(Paragraph(key_metrics_insights, body_style))
            story.append(Spacer(1, 0.2 * inch))
        else:
            story.append(Paragraph("AI insights for key metrics are being generated.", body_style))
            story.append(Spacer(1, 0.2 * inch))
    except Exception as e:
        logger.error(f"❌ Failed to generate LLM insights for Key Metrics section: {e}")
        story.append(Paragraph("AI insights generation for key metrics is in progress. Please regenerate the PDF.", body_style))
        story.append(Spacer(1, 0.2 * inch))
    
    # Mark metrics as shown to prevent duplication
    if metric_tracker:
        metric_tracker.mark_shown("followers")
        metric_tracker.mark_shown("following")
        metric_tracker.mark_shown("posts")
        metric_tracker.mark_shown("is_verified")
        metric_tracker.mark_section("profile_analytics")
    
    # Use spacer instead of hard page break
    story.append(Spacer(1, 0.3 * inch))
    
    # AUDIENCE QUALITY SECTION (Donut Chart)
    audience_section = _create_audience_quality_section(detail, styles, metric_tracker, data_validator)
    if audience_section:  # Only add if section has content
        story.extend(audience_section)
    
    # ENGAGEMENT QUALITY SECTION (Bar Charts)
    engagement_section = _create_engagement_quality_section(detail, styles, metric_tracker)
    if engagement_section:  # Only add if section has content
        story.extend(engagement_section)
    
    # ADD ONLY REQUIRED METRIC CHARTS: Engagement Rate, Engagement Breakdown, Audience Authenticity
    # Filter chart_assets to only include required metrics and avoid duplicates
    # Note: Profile Stats Card is already shown in PROFILE ANALYTICS section above
    required_metrics = {
        "Engagement Rate": ["engagement rate", "engagement_rate"],
        "Engagement Breakdown": ["engagement breakdown", "engagement_breakdown"],
        "Audience Authenticity": ["audience authenticity", "audience_authenticity", "real followers", "fake followers"]
    }
    
    # Track which metrics we've already shown to avoid duplicates
    shown_metrics = set()
    
    if chart_assets and len(chart_assets) > 0:
        story.append(PageBreak())
        # Removed "KEY METRICS ANALYSIS" heading as requested
        
        # Filter and add only required charts
        # SKIP Profile Stats Card - already added in PROFILE ANALYTICS section above
        # SKIP Audience Authenticity - already shown in _create_audience_quality_section
        for chart_title, chart_path in chart_assets:
            if not chart_path:
                continue
            
            # Skip Profile Stats Card - already displayed in PROFILE ANALYTICS section
            if "Profile Stats Card" in chart_title:
                logger.debug(f"Skipping {chart_title} - already displayed in PROFILE ANALYTICS section")
                continue
            
            # Skip Audience Authenticity - already displayed in AUDIENCE AUTHENTICITY section
            chart_lower = chart_title.lower()
            if any(keyword in chart_lower for keyword in ["audience authenticity", "audience_authenticity", "real followers", "fake followers"]):
                logger.debug(f"Skipping {chart_title} - already displayed in AUDIENCE AUTHENTICITY section")
                continue
                
            chart_file = Path(chart_path)
            if not chart_file.exists():
                continue
            
            # Check if this chart matches a required metric
            metric_found = None
            for metric_name, keywords in required_metrics.items():
                if any(keyword in chart_lower for keyword in keywords):
                    if metric_name not in shown_metrics:
                        metric_found = metric_name
                        shown_metrics.add(metric_name)
                        break
            
            if metric_found:
                try:
                    # Generate AI explanation for this chart - LLM ONLY, NO FALLBACKS
                    explanation, key_insights = generate_chart_ai_content(
                        detail, chart_title, {}, metric_tracker
                    )
                    
                    # CRITICAL: Only use LLM-generated content, never fallback
                    if not explanation or not explanation.strip():
                        logger.error(f"❌ LLM returned empty explanation for {chart_title}, skipping chart")
                        continue
                    
                    # Add chart with LLM-generated AI insights
                    _add_chart_with_detailed_explanation(
                        story, chart_path, chart_title, explanation,
                        key_insights or [], styles, force_page_break=False,
                        metric_tracker=metric_tracker
                    )
                except Exception as chart_exc:
                    logger.error(f"❌ Failed to generate LLM insights for chart {chart_title}: {chart_exc}")
                    # Skip this chart if LLM fails - don't use fallback
                    logger.warning(f"⚠️ Skipping chart {chart_title} due to LLM failure")
                    continue
    
    # POST ANALYSIS SECTION (Replaced with dedicated function)
    _add_post_analysis_section(story, detail, chart_assets, styles, metric_tracker)
    
    # COMPREHENSIVE AI INSIGHTS SECTION
    story.append(PageBreak())
    story.append(Paragraph("AI-POWERED INSIGHTS", heading_style))
    insights_line = Table([[""]], colWidths=[6.5 * inch])
    insights_line.setStyle(TableStyle([("LINEBELOW", (0, 0), (-1, 0), 3, SOFT_COLORS['secondary'])]))
    story.append(insights_line)
    story.append(Spacer(1, 0.2 * inch))
    
    # Executive Summary removed per requirements - all insights are in metric sections
    
    # Strengths & Opportunities Analysis
    strengths = insights.get("strengths", [])
    if strengths:
        strengths_heading = [
            Paragraph('<b>Key Strengths</b>', subheading_style),
            Spacer(1, 0.05 * inch)
        ]
        story.append(KeepTogether(strengths_heading))

        for i, strength in enumerate(strengths[:7], 1):  # Show more strengths
            sanitized_strength = _sanitize_text_remove_metrics(strength, metric_tracker)
            if sanitized_strength and sanitized_strength.strip():
                story.append(Paragraph(f'<b>{i}.</b> {sanitized_strength}', body_style))

        story.append(Spacer(1, 0.2 * inch))

    weaknesses = insights.get("weaknesses", [])
    if weaknesses:
        opportunities_heading = [
            Paragraph('<b>Growth Opportunities & Considerations</b>', subheading_style),
            Spacer(1, 0.05 * inch)
        ]
        story.append(KeepTogether(opportunities_heading))
        
        for i, weakness in enumerate(weaknesses[:7], 1):  # Show more opportunities
            sanitized_weakness = _sanitize_text_remove_metrics(weakness, metric_tracker)
            if sanitized_weakness and sanitized_weakness.strip():
                story.append(Paragraph(f'<b>{i}.</b> {sanitized_weakness}', body_style))
        
        story.append(Spacer(1, 0.2 * inch))
    
    # Brand Fit Analysis
    niche = detail.get("niche") or detail.get("NICHE", "Digital Creator")
    is_verified = detail.get("is_verified", False)
    engagement_rate = _safe_float(detail.get("engagement_rate", 0), 0.0)

    
    story.append(Paragraph('<b>Brand Fit Analysis</b>', subheading_style))
    story.append(Spacer(1, 0.1 * inch))
    
    brand_fit_text = f"This influencer demonstrates strong potential for brand collaborations within the {niche} space. "
    if is_verified:
        brand_fit_text += "Verified account status adds credibility and trustworthiness to partnerships. "
    if engagement_rate > 3:
        brand_fit_text += "Active audience engagement indicates high potential for campaign effectiveness and ROI. "
    else:
        brand_fit_text += "Consider engagement optimization strategies to maximize campaign performance. "
    brand_fit_text += "Overall brand alignment is favorable for strategic partnerships and long-term collaborations."
    
    sanitized_brand_fit = _sanitize_text_remove_metrics(brand_fit_text, metric_tracker)
    story.append(Paragraph(sanitized_brand_fit, body_style))
    story.append(Spacer(1, 0.2 * inch))
    
    
    # Mark authenticity as shown
    if metric_tracker:
        metric_tracker.mark_shown("real_percentage")
        metric_tracker.mark_section("audience_authenticity")
    
    
    return story


 # ============================================================================
# MAIN ASYNC PIPELINE
# Main entrypoint that builds the complete dynamic-search PDF
# ============================================================================
def generate_dynamic_pdf(
    influencer_id: str,
    influencer_data: Dict[str, Any],
    conversation_id: Optional[str] = None,
    max_retries: int = 1,
    retry_delay: float = 1.0
) -> Dict[str, Any]:
    """
    Generate comprehensive PDF report for dynamic search results with 3D charts and AI insights.

    Args:
        influencer_id: Unique influencer identifier
        influencer_data: Dictionary containing influencer data from dynamic search
        conversation_id: Optional conversation ID for temp_store lifecycle tracking
        max_retries: Maximum retry attempts
        retry_delay: Delay between retries

    Returns:
        Dictionary with 'path' (Path), 'size_bytes' (int), and 'name' (str)
    """
    from pathlib import Path
    import os
    from dotenv import load_dotenv

    # Load .env and get project root
    _PROJECT_ROOT = Path(__file__).resolve().parents[3]
    load_dotenv(_PROJECT_ROOT / ".env")

    # Base reports directory
    if conversation_id:
        from app.services.data import temp_store
        base_report_path = temp_store.get_report_path(conversation_id, influencer_id)
        reports_path = base_report_path.parent
    else:
        reports_path = _PROJECT_ROOT / "storage" / "reports"

    reports_path.mkdir(parents=True, exist_ok=True)
    
    last_error = None
    
    for attempt in range(max_retries + 1):
        tmpdir = Path(tempfile.mkdtemp(prefix=f"dynamic_report_{influencer_id}_"))
        
        try:
            if attempt > 0:
                time.sleep(retry_delay)
            
            logger.info("Starting comprehensive dynamic PDF generation attempt %s", attempt + 1)

            # Create defensive copy
            import copy
            detail_copy = copy.deepcopy(influencer_data)

            logger.debug("Dynamic PDF: incoming influencer_data keys: %s", list(influencer_data.keys())[:50])
            logger.debug("Dynamic PDF: sample keys from influencer (if nested): %s", list(influencer_data.get('influencer', {}).keys())[:50] if isinstance(influencer_data.get('influencer'), dict) else None)

            # Log key values BEFORE flattening
            logger.debug("=" * 70)
            logger.debug("PDF GENERATOR - INPUT DATA CHECK:")
            logger.debug(f"   Name (top-level): {detail_copy.get('name') or detail_copy.get('NAME')}")
            logger.debug(f"   Followers (top-level): {detail_copy.get('followers')}")
            logger.debug(f"   Engagement (top-level): {detail_copy.get('engagement_rate')}")
            logger.debug(f"   Has nested 'influencer' key: {('influencer' in detail_copy)}")
            if 'influencer' in detail_copy and isinstance(detail_copy['influencer'], dict):
                logger.debug(f"   Name (nested): {detail_copy['influencer'].get('name') or detail_copy['influencer'].get('NAME')}")
                logger.debug(f"   Followers (nested): {detail_copy['influencer'].get('followers')}")
                logger.debug(f"   Engagement (nested): {detail_copy['influencer'].get('engagement_rate')}")
            logger.debug("=" * 70)

            # IMPORTANT: If data is wrapped in an "influencer" object, flatten it to top level
            # This is common in dynamic search results where structure is:
            # {"influencer_id": "...", "influencer": {...all data...}}
            if "influencer" in detail_copy and isinstance(detail_copy["influencer"], dict):
                influencer_obj = detail_copy["influencer"]
                # Merge influencer object to top level (but don't overwrite existing keys)
                for key, value in influencer_obj.items():
                    if key not in detail_copy:
                        detail_copy[key] = value
                logger.debug("Flattened nested influencer object to top level")

                # Log AFTER flattening
                logger.debug("AFTER FLATTENING:")
                logger.debug(f"   Name: {detail_copy.get('name') or detail_copy.get('NAME')}")
                logger.debug(f"   Followers: {detail_copy.get('followers')}")
                logger.debug(f"   Engagement: {detail_copy.get('engagement_rate')}")

            # Extract and clean name (remove extra characters like "()")
            influencer_name = (
                detail_copy.get("name") or
                detail_copy.get("NAME") or
                detail_copy.get("Name") or
                detail_copy.get("id_name") or
                detail_copy.get("username") or
                "Unknown Influencer"
            )
            influencer_name = _clean_name(str(influencer_name))
            detail_copy["_normalized_name"] = influencer_name

            logger.info("Extracted and cleaned influencer name: %s (ID: %s)", influencer_name, influencer_id)

            # Build user-friendly report filename like "<InfluencerName>_Report.pdf"
            safe_slug = re.sub(r"[^A-Za-z0-9]+", "_", influencer_name).strip("_") or "Influencer"
            report_name = f"{safe_slug}_Report.pdf"
            report_path = reports_path / report_name

            logger.debug(f"📁 PDF will be saved to: {report_path}")
            logger.debug(f"📁 Reports directory: {reports_path}")
            logger.debug(f"📁 Directory exists: {reports_path.exists()}")
            
            # Initialize metric tracker early so we can use it for AI insights sanitization
            metric_tracker = MetricTracker()
            
            # Generate AI insights (will be sanitized after Profile Stats Card is shown)
            # Note: Create metric_tracker early but insights will be sanitized after metrics are marked
            temp_metric_tracker = MetricTracker()
            insights = detail_copy.get("ai_insights")
            if not isinstance(insights, dict):
                logger.debug("Generating new AI insights for dynamic search")
                # Note: metric_tracker is empty at this point, but insights will be sanitized later
                insights = _generate_dynamic_ai_insights(detail_copy, temp_metric_tracker)
            
            # ============================================================================
# CHARTS & ASSETS: generate and fallback chart creation
# ============================================================================
            # Generate charts for all metrics
            chart_assets = []
            try:
                # Get metrics from top level (should be there after flattening above)
                metrics = detail_copy.get("metrics", {})

                if metrics and len(metrics) > 0:
                    logger.debug("✓ Found %s metrics in data", len(metrics))
                    logger.debug("Available metrics: %s", list(metrics.keys())[:10])

                # If metrics are still missing, calculate them on-the-fly
                if not metrics or len(metrics) == 0:
                    logger.debug("Metrics not found in data, deriving from detail fields...")
                    logger.debug("Available keys in detail_copy: %s", list(detail_copy.keys())[:20])
                    try:
                        # Try API import first
                        from app.services.core.prompt_service import calculate_influencer_metrics
                        calculated_metrics = calculate_influencer_metrics(detail_copy)
                        if calculated_metrics and len(calculated_metrics) > 0:
                            # Map metric names to what chart generator expects
                            metrics = _map_metrics_for_charts(calculated_metrics, detail_copy)
                            detail_copy["metrics"] = metrics
                            logger.debug("Calculated %s metrics via API (mapped to %s)", len(calculated_metrics), len(metrics))
                        else:
                            logger.error("API calculation returned empty metrics")
                            raise ValueError("Metrics calculation returned empty results")
                    except Exception as calc_exc:
                        logger.error("API calculation failed: %s", calc_exc)
                        raise ValueError(f"Failed to calculate metrics: {str(calc_exc)}")
                
                logger.debug(f"🔍 METRICS CHECK: metrics={type(metrics)}, len={len(metrics) if metrics else 0}")
                logger.debug(f"   Metrics keys: {list(metrics.keys()) if metrics else 'None'}")
                
                if metrics and len(metrics) > 0:
                    # ------------------------------------------------------------------
                    # CRITICAL: normalize key numeric fields on detail_copy so that
                    # PDF tables & prose use the SAME values as the UI/charts.
                    #
                    # In some dynamic flows, top‑level fields like followers,
                    # engagement_rate or real_percentage may be empty/0 even though
                    # the computed metrics dict has the correct numbers. That caused
                    # PDFs to show 0 values while the UI showed correct metrics.
                    # ------------------------------------------------------------------
                    try:
                        logger.debug("=== NORMALIZING DATA FOR PDF ===")
                        logger.debug(f"detail_copy followers BEFORE: {detail_copy.get('followers')}")
                        logger.debug(f"metrics followers: {metrics.get('followers')}")

                        # Followers - ALWAYS use metrics if available, parse strings if not
                        maybe_followers = metrics.get("followers")
                        if isinstance(maybe_followers, (int, float)) and maybe_followers > 0:
                            detail_copy["followers"] = int(maybe_followers)
                            logger.debug(f"✓ Set followers from metrics: {int(maybe_followers)}")
                        elif detail_copy.get("followers"):
                            # Parse string format like "110.57k" to integer
                            parsed = parse_followers_to_int(str(detail_copy.get("followers")))
                            if parsed > 0:
                                detail_copy["followers"] = parsed
                                logger.debug(f"✓ Parsed followers from string: {parsed}")

                        logger.debug(f"detail_copy followers AFTER: {detail_copy.get('followers')}")

                        # Engagement rate: ALWAYS prefer metrics over detail_copy
                        logger.debug(f"detail_copy engagement_rate BEFORE: {detail_copy.get('engagement_rate')}")
                        logger.debug(f"metrics engagement_rate: {metrics.get('engagement_rate')}")

                        existing_eng = detail_copy.get("engagement_rate")
                        try:
                            existing_eng_val = float(str(existing_eng).replace("%", "").strip()) if existing_eng not in (None, "", "N/A", "nan") else 0.0
                        except Exception:
                            existing_eng_val = 0.0

                        metric_eng = metrics.get("engagement_rate")
                        try:
                            metric_eng_val = float(str(metric_eng).replace("%", "").strip()) if metric_eng not in (None, "", "N/A", "nan") else 0.0
                        except Exception:
                            metric_eng_val = 0.0

                        # ALWAYS use metrics if available and valid
                        if metric_eng_val > 0:
                            detail_copy["engagement_rate"] = metric_eng_val
                            logger.debug(f"✓ Set engagement_rate from metrics: {metric_eng_val}%")
                        elif existing_eng_val > 0:
                            detail_copy["engagement_rate"] = existing_eng_val
                            logger.debug(f"✓ Kept existing engagement_rate: {existing_eng_val}%")

                        # Real followers percentage: align with metrics["real_follower_ratio"]
                        # or metrics["real_percentage"] if present.
                        existing_real = detail_copy.get("real_followers_percentage", detail_copy.get("real_percentage"))
                        try:
                            existing_real_val = float(str(existing_real).replace("%", "").strip()) if existing_real not in (None, "", "N/A", "nan") else 0.0
                        except Exception:
                            existing_real_val = 0.0

                        metric_real = (
                            metrics.get("real_follower_ratio")
                            if "real_follower_ratio" in metrics
                            else metrics.get("real_percentage")
                        )
                        try:
                            metric_real_val = float(str(metric_real).replace("%", "").strip()) if metric_real not in (None, "", "N/A", "nan") else 0.0
                        except Exception:
                            metric_real_val = 0.0

                        if metric_real_val > 0 and existing_real_val <= 0:
                            detail_copy["real_percentage"] = metric_real_val
                            detail_copy["real_followers_percentage"] = metric_real_val

                        # Suspicious / fake followers percentage: align with metrics["fake_follower_ratio"]
                        existing_susp = detail_copy.get("suspicious_followers_percentage")
                        try:
                            existing_susp_val = float(str(existing_susp).replace("%", "").strip()) if existing_susp not in (None, "", "N/A", "nan") else 0.0
                        except Exception:
                            existing_susp_val = 0.0

                        metric_fake = metrics.get("fake_follower_ratio")
                        try:
                            metric_fake_val = float(str(metric_fake).replace("%", "").strip()) if metric_fake not in (None, "", "N/A", "nan") else 0.0
                        except Exception:
                            metric_fake_val = 0.0

                        if metric_fake_val > 0 and existing_susp_val <= 0:
                            detail_copy["suspicious_followers_percentage"] = metric_fake_val

                        # Rate: ensure available so cost/ROI tables are non‑zero
                        if not detail_copy.get("rate") and not detail_copy.get("RATE"):
                            metric_rate = metrics.get("rate") or metrics.get("RATE")
                            try:
                                metric_rate_val = float(metric_rate) if metric_rate not in (None, "", "N/A", "nan") else 0.0
                            except Exception:
                                metric_rate_val = 0.0
                            if metric_rate_val > 0:
                                detail_copy["rate"] = metric_rate_val
                                detail_copy["RATE"] = metric_rate_val

                        # SUMMARY: Log final normalized values
                        logger.debug("=== NORMALIZATION COMPLETE - FINAL VALUES ===")
                        logger.debug(f"Followers: {detail_copy.get('followers')}")
                        logger.debug(f"Engagement Rate: {detail_copy.get('engagement_rate')}")
                        logger.debug(f"Real Followers %: {detail_copy.get('real_followers_percentage')}")
                        logger.debug(f"Suspicious %: {detail_copy.get('suspicious_followers_percentage')}")
                        logger.debug(f"Rate: {detail_copy.get('rate') or detail_copy.get('RATE')}")
                        logger.debug("=" * 50)

                    except Exception as norm_exc:
                        logger.error("Failed to normalize metrics onto detail_copy: %s", norm_exc)
                        import traceback
                        logger.error(traceback.format_exc())

                    # Generate individual charts for each metric
                    try:
                        from app.utils.chart_utils import generate_individual_metric_charts
                    except SyntaxError as syntax_err:
                        logger.error(f"Syntax error in chart_utils.py: {syntax_err}")
                        logger.error(f"  File: {syntax_err.filename}, Line: {syntax_err.lineno}")
                        logger.error(f"  Text: {syntax_err.text}")
                        raise
                    except Exception as import_err:
                        logger.error(f"Failed to import chart_utils: {import_err}")
                        raise
                    
                    chart_assets = generate_individual_metric_charts(
                        metrics,
                        detail_copy,
                        prefix=f"dynamic_{influencer_id}"
                    )
                    
                    # DEBUG: Log chart generation
                    logger.debug(f"🎨 Chart generation called with {len(metrics)} metrics")
                    logger.debug(f"   Detail keys: {list(detail_copy.keys())[:10]}")
                    logger.debug(f"   Followers: {detail_copy.get('followers')}, Posts: {detail_copy.get('posts')}")
                    
                    # DEBUG: Log generated charts
                    logger.debug(f"📊 Generated {len(chart_assets)} chart assets:")
                    for title, path in chart_assets:
                        logger.debug(f"   • {title}: {path}")
                    
                    # Filter out post analysis charts if posts = 0
                    # CRITICAL: Check both posts and posts_count, handle list case
                    posts_raw = detail_copy.get("posts", 0) or detail_copy.get("posts_count", 0)
                    posts_count = 0.0
                    if posts_raw:
                        if isinstance(posts_raw, list):
                            posts_count = float(len(posts_raw))
                            logger.debug(f"📊 Post analysis check: posts is list with {posts_count} items")
                        elif isinstance(posts_raw, (int, float)):
                            posts_count = float(posts_raw)
                            logger.debug(f"📊 Post analysis check: posts is number: {posts_count}")
                        else:
                            posts_count = _safe_float(posts_raw, 0.0)
                            logger.debug(f"📊 Post analysis check: posts converted to float: {posts_count}")
                    else:
                        logger.debug("⚠️ Post analysis check: No posts data found (posts={}, posts_count={})".format(
                            detail_copy.get("posts"), detail_copy.get("posts_count")))
                    
                    # Also check if we have actual post objects in the list to generate charts from
                    has_post_data = False
                    if isinstance(detail_copy.get("posts"), list) and len(detail_copy.get("posts")) > 0:
                         has_post_data = True

                    if not has_post_data and posts_count == 0:
                        chart_assets = [
                            (title, path) for title, path in chart_assets 
                            if not (
                                ("post" in title.lower() and "analysis" in title.lower()) or
                                "content format" in title.lower() or
                                "activity timeline" in title.lower() or
                                "content activity" in title.lower()
                            )
                        ]
                        logger.debug("Filtered out post analysis charts (no post data)")
                    else:
                        logger.debug(f"✅ Post analysis charts will be included (posts_count={posts_count}, has_data={has_post_data})")
                    
                    logger.debug("Generated %s individual metric charts for dynamic search", len(chart_assets))
                else:
                    logger.warning("No metrics available for chart generation (tried calculation). Metrics dict: %s", metrics)
            except SyntaxError as syntax_err:
                logger.error("❌ CRITICAL: Syntax error in chart_utils.py")
                logger.error(f"   File: {getattr(syntax_err, 'filename', 'chart_utils.py')}")
                logger.error(f"   Line: {syntax_err.lineno}")
                logger.error(f"   Message: {syntax_err.msg}")
                logger.error(f"   Text: {getattr(syntax_err, 'text', 'N/A')}")
                if hasattr(syntax_err, 'offset') and syntax_err.offset:
                    logger.error(f"   Position: {syntax_err.offset}")
                import traceback
                logger.error(traceback.format_exc())
                chart_assets = []  # Set empty to prevent further errors
            except ImportError as import_exc:
                logger.error("chart_utils import failed, skipping chart generation: %s", import_exc)
                import traceback
                logger.debug(traceback.format_exc())
                chart_assets = []  # Set empty to prevent further errors
            except Exception as chart_exc:
                logger.error("3D chart generation failed: %s", chart_exc)
                import traceback
                logger.debug(traceback.format_exc())
                chart_assets = []  # Set empty to prevent further errors
            
            # Build comprehensive PDF content
            styles = getSampleStyleSheet()
            story = []
            
            # Initialize data validator and metric tracker
            data_validator = DataValidator(detail_copy)
            metric_tracker = MetricTracker()  # Create fresh tracker for PDF generation
            
            # Get industry benchmarks if available
            benchmarks = get_industry_benchmarks(detail_copy, conversation_id)
            if benchmarks:
                detail_copy["_industry_benchmarks"] = benchmarks
            
            # Page counter for enforcement (target: 12-18 pages max)
            page_count = 0
            MAX_PAGES = 18
            MIN_PAGES = 12
            
            # CRITICAL STRUCTURE: cover → Profile Stats Card → charts → insights
            # Cover page
            cover_story = _create_cover_page(detail_copy, styles)
            story.extend(cover_story)
            page_count += 1
            
            # Detailed analysis with charts (includes Profile Stats Card FIRST, then charts, then insights)
            # This ensures metrics are marked as shown before any text content
            analysis_story = _create_detailed_analysis_with_charts(
                detail_copy, insights, chart_assets, styles, 
                metric_tracker, data_validator, benchmarks, page_count, MAX_PAGES
            )
            story.extend(analysis_story)
            
            # CRITICAL: Sanitize AI insights NOW that all metrics have been marked as shown
            if isinstance(insights, dict):
                if isinstance(insights.get("executive_summary"), str):
                    insights["executive_summary"] = _sanitize_text_remove_metrics(insights["executive_summary"], metric_tracker)
                if isinstance(insights.get("strengths"), list):
                    insights["strengths"] = [_sanitize_text_remove_metrics(s, metric_tracker) for s in insights["strengths"] if s]
                if isinstance(insights.get("weaknesses"), list):
                    insights["weaknesses"] = [_sanitize_text_remove_metrics(w, metric_tracker) for w in insights["weaknesses"] if w]
                if isinstance(insights.get("verdict"), str):
                    insights["verdict"] = _sanitize_text_remove_metrics(insights["verdict"], metric_tracker)
            
            # Executive summary removed per requirements
            # All insights are now included in individual metric sections with AI analysis
            
            # Create PDF document with professional margins
            doc = SimpleDocTemplate(
                str(report_path),
                pagesize=A4,
                rightMargin=0.7 * inch,
                leftMargin=0.7 * inch,
                topMargin=0.85 * inch,
                bottomMargin=0.85 * inch,
            )
            
            # Build PDF with page callbacks
            def page_callback(canvas_obj, doc):
                _add_l_shaped_border(canvas_obj, doc)
                is_last = canvas_obj.getPageNumber() == doc.page
                _add_header_footer(canvas_obj, doc, is_last_page=is_last)
            
            doc.build(story, onFirstPage=page_callback, onLaterPages=page_callback)

            # Verify PDF was created
            if not report_path.exists():
                raise FileNotFoundError(f"PDF was not created at expected path: {report_path}")

            size_bytes = report_path.stat().st_size
            logger.debug(f"✅ PDF file created: {report_path} ({size_bytes:,} bytes)")

            # Cleanup temp directory
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass

            logger.info(
                "✅ Dynamic PDF generated successfully: %s (%.2f KB)",
                report_name, size_bytes / 1024
            )
            
            return {
                "path": report_path,
                "size_bytes": size_bytes,
                "name": report_name
            }
            
        except Exception as e:
            last_error = e
            logger.error(f"❌ PDF generation attempt {attempt + 1} failed: {e}")
            logger.error(f"   Error type: {type(e).__name__}")
            logger.error(f"   Report path: {report_path if 'report_path' in locals() else 'Not set'}")
            import traceback
            traceback.print_exc()
            # Cleanup on error
            try:
                shutil.rmtree(tmpdir, ignore_errors=True)
            except Exception:
                pass
            if attempt < max_retries:
                continue
            else:
                raise
    
    raise Exception(f"PDF generation failed after {max_retries + 1} attempts: {last_error}")
