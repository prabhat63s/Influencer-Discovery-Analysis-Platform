"""
Professional Monitoring Service for CreatosConnect
==================================================
Comprehensive tracking of:
- Web Discovery (SerpAPI) calls
- Profile Enrichment (BrightData) calls
- AI Processing (Gemini/OpenRouter) tokens
- Authenticity Checking (Spreadd) calls
- Performance metrics & timing
- Quality metrics (niche/location matching)
- Cost calculations with branded names

Storage: JSON files + in-memory cache
Branding: Web Discovery, Profile Enrichment, AI Processing (no external names)
"""

import json
import os
import hashlib
from pathlib import Path
from datetime import datetime
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, field, asdict
import logging
import psutil # For system metrics
from redis import Redis # For Redis health
from app.config.celery_app import celery_app, REDIS_URL # For Worker health

logger = logging.getLogger(__name__)

# Pricing per 1000 operations (user-facing branded pricing)
PRICING = {
    "web_discovery": 15.0,      # $15 per 1K searches
    "profile_enrichment": 10.0,  # $10 per 1K profiles
    "ai_processing": 10.0        # $10 per 1M tokens
}

# Rate limits
RATE_LIMITS = {
    "monthly_searches": 250
}

@dataclass
class SearchMetrics:
    """Comprehensive search metrics"""
    # Identifiers
    conversation_id: str = ""
    timestamp: str = ""
    query: str = ""

    # Discovery metrics (SerpAPI → Web Discovery)
    web_searches: int = 0
    web_search_failures: int = 0
    # Pipeline field names (mapped to web_searches)
    serpapi_calls: int = 0
    serpapi_failures: int = 0

    # Enrichment metrics (BrightData → Profile Enrichment)
    profiles_enriched: int = 0
    profiles_returned: int = 0
    enrichment_failures: int = 0
    # Pipeline field names
    brightdata_calls: int = 0
    brightdata_failures: int = 0

    # Authenticity metrics (Spreadd)
    authenticity_checks: int = 0
    authenticity_failures: int = 0
    spreadd_successful_checks: int = 0
    # Pipeline field names (mapped to authenticity_checks)
    spreadd_calls: int = 0
    spreadd_failures: int = 0

    # AI metrics (Gemini/OpenRouter → AI Processing)
    ai_calls: int = 0
    tokens_used: int = 0
    ai_failures: int = 0
    # Pipeline field names (mapped to ai_calls/tokens_used)
    gemini_calls: int = 0
    gemini_failures: int = 0
    estimated_tokens_used: int = 0

    # Discovery results
    influencers_discovered: int = 0
    influencers_after_dedup: int = 0
    influencers_sorted: int = 0
    influencers_returned: int = 0
    total_influencers_discovered: int = 0
    total_influencers_after_dedup: int = 0
    total_influencers_sorted: int = 0

    # Quality metrics (%)
    niche_match_rate: float = 0.0
    location_match_rate: float = 0.0
    followers_match_rate: float = 0.0
    engagement_rate_avg: float = 0.0
    authenticity_score_avg: float = 0.0

    # Performance (seconds)
    total_time: float = 0.0
    discovery_time: float = 0.0
    enrichment_time: float = 0.0
    analysis_time: float = 0.0
    # Pipeline field names (mapped to discovery/enrichment/analysis_time)
    total_time_seconds: float = 0.0
    search_time_seconds: float = 0.0
    scraping_time_seconds: float = 0.0
    sort_time_seconds: float = 0.0

    # Cost (calculated) - Individual breakdown
    web_discovery_cost: float = 0.0      # Searching cost
    profile_enrichment_cost: float = 0.0  # Data enrichment cost
    ai_processing_cost: float = 0.0       # AI prompt costing
    total_cost: float = 0.0               # Total cost

    # Errors
    errors: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    
    def add_error(self, error: str):
        """Add an error message"""
        self.errors.append(error)
    
    def add_warning(self, warning: str):
        """Add a warning message"""
        self.warnings.append(warning)
    
    def calculate_success_rate(self) -> float:
        """Calculate success rate percentage"""
        if self.influencers_discovered == 0:
            return 0.0
        return (self.influencers_returned / self.influencers_discovered) * 100
    
    def log_summary(self):
        """Log summary to console (for debugging)"""
        logger.info(f"📊 Metrics Summary for {self.conversation_id}:")
        logger.info(f"   Web Searches: {self.web_searches}")
        logger.info(f"   Profiles Enriched: {self.profiles_enriched}")
        logger.info(f"   AI Calls: {self.ai_calls}")
        logger.info(f"   Tokens Used: {self.tokens_used:,}")
        logger.info(f"   Web Discovery Cost: ${self.web_discovery_cost:.4f}")
        logger.info(f"   Profile Enrichment Cost: ${self.profile_enrichment_cost:.4f}")
        logger.info(f"   AI Processing Cost: ${self.ai_processing_cost:.4f}")
        logger.info(f"   Total Cost: ${self.total_cost:.4f}")
    
    def to_monitoring_dict(self) -> Dict:
        """
        Convert to dict format expected by monitoring.log_search()
        Maps pipeline field names to SearchMetrics fields
        """
        # Map pipeline fields to SearchMetrics fields
        web_searches = self.web_searches or self.serpapi_calls
        web_search_failures = self.web_search_failures or self.serpapi_failures
        authenticity_checks = self.authenticity_checks or self.spreadd_calls
        authenticity_failures = self.authenticity_failures or self.spreadd_failures
        ai_calls = self.ai_calls or self.gemini_calls
        ai_failures = self.ai_failures or self.gemini_failures
        tokens_used = self.tokens_used or self.estimated_tokens_used
        
        # Map timing fields
        discovery_time = self.discovery_time or self.search_time_seconds
        enrichment_time = self.enrichment_time or self.scraping_time_seconds
        analysis_time = self.analysis_time or self.sort_time_seconds
        
        # Map influencer counts
        influencers_discovered = self.influencers_discovered or self.total_influencers_discovered
        influencers_after_dedup = self.influencers_after_dedup or self.total_influencers_after_dedup
        influencers_sorted = self.influencers_sorted or self.total_influencers_sorted

        return {
            "web_searches": web_searches,
            "web_search_failures": web_search_failures,
            "profiles_enriched": self.profiles_enriched or self.brightdata_calls,
            "profiles_returned": self.profiles_returned,
            "enrichment_failures": self.enrichment_failures or self.brightdata_failures,
            "authenticity_checks": authenticity_checks,
            "authenticity_failures": authenticity_failures,
            "tokens_used": tokens_used,
            "ai_calls": ai_calls,
            "ai_failures": ai_failures,
            "influencers_discovered": influencers_discovered,
            "influencers_after_dedup": influencers_after_dedup,
            "influencers_sorted": influencers_sorted,
            "influencers_returned": self.influencers_returned,
            "niche_match_rate": self.niche_match_rate,
            "location_match_rate": self.location_match_rate,
            "followers_match_rate": self.followers_match_rate,
            "engagement_rate_avg": self.engagement_rate_avg,
            "authenticity_score_avg": self.authenticity_score_avg,
            "time_breakdown": {
                "discovery": discovery_time,
                "enrichment": enrichment_time,
                "analysis": analysis_time
            }
        }

    def calculate_cost(self) -> float:
        """Calculate total cost with branded pricing and individual cost breakdowns"""
        # Calculate individual costs
        self.web_discovery_cost = (self.web_searches / 1000) * PRICING["web_discovery"]
        self.profile_enrichment_cost = (self.profiles_enriched / 1000) * PRICING["profile_enrichment"]
        self.ai_processing_cost = (self.tokens_used / 1_000_000) * PRICING["ai_processing"]
        
        # Calculate total cost
        self.total_cost = self.web_discovery_cost + self.profile_enrichment_cost + self.ai_processing_cost
        return self.total_cost

    def to_dict(self) -> Dict:
        """Convert to dict with calculated values including individual cost breakdowns"""
        # Calculate all costs first
        self.calculate_cost()
        
        # Convert to dict
        data = asdict(self)
        
        # Ensure all cost fields are included (calculate_cost() sets them, but ensure they're in dict)
        data['web_discovery_cost'] = self.web_discovery_cost
        data['profile_enrichment_cost'] = self.profile_enrichment_cost
        data['ai_processing_cost'] = self.ai_processing_cost
        data['total_cost'] = self.total_cost
        
        return data


class MonitoringService:
    def __init__(self):
        self.storage_path = Path("storage/monitoring")
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.logs_file = self.storage_path / "search_logs.json"
        self.summary_file = self.storage_path / "usage_summary.json"
        self._ensure_files()

        # In-memory cache (matches old system)
        self._metrics_store: Dict[str, SearchMetrics] = {}

    def _ensure_files(self):
        """Create log files if missing"""
        if not self.logs_file.exists():
            self.logs_file.write_text(json.dumps({"searches": []}, indent=2))
        if not self.summary_file.exists():
            self.summary_file.write_text(json.dumps({"totals": {}}, indent=2))

    def _current_api_key_sig(self) -> str:
        """
        Generate a hash signature of the SerpAPI key without exposing it.
        Uses SHA-256; only the hex digest is stored. If no key is set, uses an empty string.
        """
        serp_key = os.getenv("SERPAPI_API_KEY", "") or os.getenv("SERP_API_KEY", "")
        material = serp_key.encode("utf-8")
        return hashlib.sha256(material).hexdigest()

    def _rebuild_summary_from_logs(self, api_key_sig: str) -> Dict:
        """
        Recalculate usage summary from search_logs.json.
        This prevents stale totals when API keys change.
        """
        totals = {
            "web_searches": 0,
            "profiles_enriched": 0,
            "profiles_returned": 0,
            "tokens_used": 0,
            "total_searches": 0,
            "web_discovery_cost": 0.0,
            "profile_enrichment_cost": 0.0,
            "ai_processing_cost": 0.0,
            "total_cost": 0.0,
        }

        if self.logs_file.exists():
            try:
                data = json.loads(self.logs_file.read_text())
                searches = data.get("searches", [])
                for entry in searches:
                    # Use `or 0` pattern to handle explicitly stored None values
                    totals["web_searches"] += (entry.get("web_searches") or entry.get("serpapi_calls") or 0)
                    totals["profiles_enriched"] += (entry.get("profiles_enriched") or 0)
                    totals["profiles_returned"] += (entry.get("profiles_returned") or 0)
                    totals["tokens_used"] += (entry.get("tokens_used") or 0)
                    # Aggregate individual costs from logs
                    totals["web_discovery_cost"] += (entry.get("web_discovery_cost") or 0.0)
                    totals["profile_enrichment_cost"] += (entry.get("profile_enrichment_cost") or 0.0)
                    totals["ai_processing_cost"] += (entry.get("ai_processing_cost") or 0.0)
                    totals["total_cost"] += (entry.get("total_cost") or 0.0)
                totals["total_searches"] = len(searches)
            except (json.JSONDecodeError, FileNotFoundError):
                pass

        summary = {
            "totals": totals,
            "last_updated": datetime.now().isoformat(),
            "api_key_sig": api_key_sig,
        }
        self.summary_file.write_text(json.dumps(summary, indent=2))
        return summary

    def get_metrics(self, conversation_id: str) -> SearchMetrics:
        """Get or create metrics for conversation (like old system)"""
        if conversation_id not in self._metrics_store:
            self._metrics_store[conversation_id] = SearchMetrics(
                conversation_id=conversation_id,
                timestamp=datetime.now().isoformat()
            )
        return self._metrics_store[conversation_id]

    def log_search(self, conversation_id: str, query: str, metrics: Dict) -> Dict:
        """
        Log completed search with all metrics

        metrics = {
            "web_searches": int,
            "web_search_failures": int,
            "profiles_enriched": int,
            "profiles_returned": int,
            "enrichment_failures": int,
            "authenticity_checks": int,
            "tokens_used": int,
            "ai_calls": int,
            "influencers_discovered": int,
            "influencers_after_dedup": int,
            "influencers_sorted": int,
            "influencers_returned": int,
            "niche_match_rate": float,
            "location_match_rate": float,
            "followers_match_rate": float,
            "engagement_rate_avg": float,
            "authenticity_score_avg": float,
            "time_breakdown": {
                "discovery": float,
                "enrichment": float,
                "analysis": float
            }
        }
        """
        # Robustly map incoming fields (support legacy serpapi_* keys)
        web_searches_val = metrics.get("web_searches", 0) or metrics.get("serpapi_calls", 0)
        web_search_failures_val = metrics.get("web_search_failures", 0) or metrics.get("serpapi_failures", 0)

        api_key_sig = self._current_api_key_sig()

        search_metrics = SearchMetrics(
            conversation_id=conversation_id,
            timestamp=datetime.now().isoformat(),
            query=query,
            web_searches=web_searches_val,
            web_search_failures=web_search_failures_val,
            # Use `or 0` pattern to handle explicitly stored None values
            profiles_enriched=metrics.get("profiles_enriched") or 0,
            profiles_returned=metrics.get("profiles_returned") or 0,
            enrichment_failures=metrics.get("enrichment_failures") or 0,
            authenticity_checks=metrics.get("authenticity_checks") or 0,
            tokens_used=metrics.get("tokens_used") or 0,
            ai_calls=metrics.get("ai_calls") or 0,
            influencers_discovered=metrics.get("influencers_discovered") or 0,
            influencers_after_dedup=metrics.get("influencers_after_dedup") or 0,
            influencers_sorted=metrics.get("influencers_sorted") or 0,
            influencers_returned=metrics.get("influencers_returned") or 0,
            niche_match_rate=metrics.get("niche_match_rate") or 0.0,
            location_match_rate=metrics.get("location_match_rate") or 0.0,
            followers_match_rate=metrics.get("followers_match_rate") or 0.0,
            engagement_rate_avg=metrics.get("engagement_rate_avg") or 0.0,
            authenticity_score_avg=metrics.get("authenticity_score_avg") or 0.0,
            discovery_time=metrics.get("time_breakdown", {}).get("discovery") or 0.0,
            enrichment_time=metrics.get("time_breakdown", {}).get("enrichment") or 0.0,
            analysis_time=metrics.get("time_breakdown", {}).get("analysis") or 0.0
        )

        search_metrics.total_time = (
            search_metrics.discovery_time +
            search_metrics.enrichment_time +
            search_metrics.analysis_time
        )
        search_metrics.calculate_cost()

        # Save to file
        try:
            if self.logs_file.exists():
                data = json.loads(self.logs_file.read_text())
            else:
                data = {"searches": []}
            data["searches"].append(search_metrics.to_dict())
            self.logs_file.write_text(json.dumps(data, indent=2))
        except (json.JSONDecodeError, KeyError, FileNotFoundError) as e:
            logger.warning(f"⚠️ Failed to save search log: {e}. Creating new log file.")
            data = {"searches": [search_metrics.to_dict()]}
            self.logs_file.write_text(json.dumps(data, indent=2))

        # Update summary
        self._update_summary(search_metrics, api_key_sig)

        # Store in memory
        self._metrics_store[conversation_id] = search_metrics

        logger.info(f"✅ Search logged: {conversation_id} - Web Discovery: ${search_metrics.web_discovery_cost:.4f}, Enrichment: ${search_metrics.profile_enrichment_cost:.4f}, AI: ${search_metrics.ai_processing_cost:.4f}, Total: ${search_metrics.total_cost:.4f}")
        return search_metrics.to_dict()

    def _update_summary(self, metrics: SearchMetrics, api_key_sig: str):
        """Update cumulative summary with resilient defaults."""
        try:
            if self.summary_file.exists():
                data = json.loads(self.summary_file.read_text())
            else:
                data = {"totals": {}}
        except (json.JSONDecodeError, FileNotFoundError) as e:
            logger.warning(f"⚠️ Failed to read summary file: {e}. Creating new summary.")
            data = {"totals": {}}

        # Ensure all expected total fields exist
        totals = data.setdefault("totals", {})
        for key, default in {
            "web_searches": 0,
            "profiles_enriched": 0,
            "profiles_returned": 0,
            "tokens_used": 0,
            "total_searches": 0,
            "web_discovery_cost": 0.0,
            "profile_enrichment_cost": 0.0,
            "ai_processing_cost": 0.0,
            "total_cost": 0.0
        }.items():
            totals.setdefault(key, default)

        # Update cumulative totals
        totals["web_searches"] += metrics.web_searches or metrics.serpapi_calls
        totals["profiles_enriched"] += metrics.profiles_enriched
        totals["profiles_returned"] += metrics.profiles_returned
        totals["tokens_used"] += metrics.tokens_used
        totals["total_searches"] += 1
        # Update individual cost totals
        totals["web_discovery_cost"] += metrics.web_discovery_cost
        totals["profile_enrichment_cost"] += metrics.profile_enrichment_cost
        totals["ai_processing_cost"] += metrics.ai_processing_cost
        totals["total_cost"] += metrics.total_cost

        data["totals"] = totals
        data["last_updated"] = datetime.now().isoformat()
        data["api_key_sig"] = api_key_sig

        self.summary_file.write_text(json.dumps(data, indent=2))

    def get_usage_stats(self) -> Dict:
        """Get current usage statistics (agent tool)"""
        current_sig = self._current_api_key_sig()

        if not self.summary_file.exists():
            data = self._rebuild_summary_from_logs(current_sig)
        else:
            try:
                data = json.loads(self.summary_file.read_text())
            except (json.JSONDecodeError, FileNotFoundError):
                data = self._rebuild_summary_from_logs(current_sig)

        stored_sig = data.get("api_key_sig")
        totals = data.get("totals", {})

        # If API key signature changed or totals missing, rebuild from logs
        if stored_sig != current_sig or not totals:
            data = self._rebuild_summary_from_logs(current_sig)
            totals = data.get("totals", {})

        searches_used = totals.get("total_searches", 0)
        
        # Calculate remaining based on monthly limit
        monthly_remaining = max(0, RATE_LIMITS["monthly_searches"] - searches_used)

        # Use stored costs from summary (more accurate than recalculating)
        # Fallback to calculation if stored costs not available (for backward compatibility)
        web_discovery_cost = totals.get("web_discovery_cost")
        if web_discovery_cost is None:
            web_discovery_cost = round((totals.get("web_searches", 0) / 1000) * PRICING["web_discovery"], 4)
        else:
            web_discovery_cost = round(web_discovery_cost, 4)
        
        profile_enrichment_cost = totals.get("profile_enrichment_cost")
        if profile_enrichment_cost is None:
            profile_enrichment_cost = round((totals.get("profiles_enriched", 0) / 1000) * PRICING["profile_enrichment"], 4)
        else:
            profile_enrichment_cost = round(profile_enrichment_cost, 4)
        
        ai_processing_cost = totals.get("ai_processing_cost")
        if ai_processing_cost is None:
            ai_processing_cost = round((totals.get("tokens_used", 0) / 1_000_000) * PRICING["ai_processing"], 4)
        else:
            ai_processing_cost = round(ai_processing_cost, 4)
        
        return {
            "operations": {
                "web_searches": totals.get("web_searches", 0),
                "profiles_enriched": totals.get("profiles_enriched", 0),
                "profiles_returned": totals.get("profiles_returned", 0),
                "ai_tokens": totals.get("tokens_used", 0)
            },
            "costs": {
                "total_spent": round(totals.get("total_cost", 0.0), 4),
                "web_discovery": web_discovery_cost,
                "profile_enrichment": profile_enrichment_cost,
                "ai_processing": ai_processing_cost
            },
            "quota": {
                "searches_used": searches_used,
                "searches_remaining": monthly_remaining,
                "monthly_limit": RATE_LIMITS["monthly_searches"]
            },
            "pricing": {
                "web_discovery_per_1k": PRICING["web_discovery"],
                "profile_enrichment_per_1k": PRICING["profile_enrichment"],
                "ai_processing_per_1m_tokens": PRICING["ai_processing"]
            }
        }

    def get_search_history(self, limit: int = 10) -> List[Dict]:
        """Get recent search history (agent tool)"""
        if not self.logs_file.exists():
            return []

        data = json.loads(self.logs_file.read_text())
        searches = data.get("searches", [])

        return sorted(searches, key=lambda x: x["timestamp"], reverse=True)[:limit]

    def get_cost_breakdown(self) -> Dict:
        """Get detailed cost breakdown (agent tool)"""
        stats = self.get_usage_stats()
        return {
            "breakdown": stats["costs"],
            "operations": stats["operations"],
            "pricing_info": stats["pricing"]
        }

    def get_rate_limit_status(self) -> Dict:
        """Check rate limit status (agent tool)"""
        stats = self.get_usage_stats()
        quota = stats["quota"]

        return {
            "can_search": quota["searches_remaining"] > 0,
            "remaining": quota["searches_remaining"],
            "used": quota["searches_used"],
            "monthly_limit": quota["monthly_limit"]
        }

    # ========================================================================
    # KNOWLEDGE BASE - Metric Explanations
    # ========================================================================
    # Comprehensive explanations for all 40+ metrics calculated in the system

    def explain_metric(self, metric_name: str) -> str:
        """Explain how metrics are calculated (agent tool)"""
        explanations = {
            # ------------------------------------------------------------------
            # CORE METRICS - Primary scoring metrics
            # ------------------------------------------------------------------
            "authenticity_score": """Authenticity Score measures how genuine an influencer's audience is, ranging from 0 to 100.

We analyze follower behavior patterns, engagement quality, and account characteristics to identify real people versus fake or bot accounts. Scores above 80 indicate highly authentic followers, which means your campaign will reach real people who are genuinely interested in the content. This is critical for campaign success because authentic followers actually engage with sponsored content and can become customers.""",

            "quality_score": """Quality Score provides an overall assessment of influencer quality on a scale of 0 to 1.

We evaluate multiple factors including audience authenticity, engagement patterns, account verification status, and profile completeness. Higher scores indicate influencers who are more professional, consistent, and reliable for brand partnerships. Scores above 0.75 suggest high-quality influencers who deliver strong campaign results.""",

            "engagement_rate": """Engagement Rate shows how actively an influencer's audience interacts with their content, expressed as a percentage.

We measure likes, comments, shares, and saves relative to their follower count. Higher rates typically 3-6% or more indicate a highly engaged audience that actually pays attention to the influencer's posts. This matters because engaged followers are more likely to notice and act on sponsored content.""",

            "relevance_score": """Relevance Score indicates how well an influencer matches your specific campaign criteria, on a scale of 0 to 10.

We assess their niche alignment, location match, follower range fit, and content style against your requirements. Scores above 7 indicate highly relevant matches who will naturally resonate with your brand message. Better relevance means more authentic partnerships and better campaign performance.""",

            # ------------------------------------------------------------------
            # MATCHING METRICS - Criteria alignment
            # ------------------------------------------------------------------
            "niche_matching": """Niche Matching uses AI to determine how well an influencer's content aligns with your campaign niche.

We analyze their bio, content themes, hashtags, and posting patterns to understand what they actually create content about. Then we compare this against your campaign requirements to determine relevance. Scores range from 0 to 1, where higher scores mean stronger alignment. A match of 0.9 means the influencer's content strongly aligns with your campaign niche, making them ideal for authentic partnerships.""",

            "location_matching": """Location Matching verifies that an influencer is based in your target geographic area.

We check their stated location from their profile and validate it against your requirements. This works at multiple levels whether you need someone in a specific city, state, or country. Location matching is essential for campaigns targeting local markets, regional brands, or location-specific promotions where the influencer's local presence matters.""",

            "follower_matching": """Follower Range Matching shows how well an influencer's audience size fits your target range.

We compare their current follower count against your specified requirements. Perfect matches fall right in your target range, while partial matches are close but slightly outside. This ensures you get influencers at the right tier whether you want micro influencers for niche engagement, mid-tier for balanced reach, or macro influencers for maximum exposure.""",

            # ------------------------------------------------------------------
            # COST METRICS - Campaign budgeting
            # ------------------------------------------------------------------
            "cost_per_post": """Cost Per Post provides estimated influencer pricing to help you budget campaigns.

We analyze their follower count, engagement rate, audience authenticity, and niche to estimate fair market pricing. Higher engagement and more authentic followers command premium rates. Different niches also have different rate standards.

Typical ranges by tier:
- Nano (1K-10K): $10-$100 per post
- Micro (10K-100K): $100-$500 per post
- Mid-tier (100K-500K): $500-$5,000 per post
- Macro (500K+): $5,000+ per post

These estimates help you budget campaigns and calculate expected ROI before reaching out.""",

            "estimated_reach": """Estimated Reach projects how many unique accounts will actually see sponsored content from this influencer.

We consider their follower count and typical platform distribution patterns. Not all followers see every post due to how social media algorithms work. Stories typically reach 30-40% of followers, while feed posts reach 10-20%. We also factor in engagement quality and audience authenticity to refine estimates.

For example, an influencer with 100K followers might reach 15,000-40,000 unique accounts per post, depending on content type and posting strategy.""",

            # ------------------------------------------------------------------
            # ADVANCED METRICS
            # ------------------------------------------------------------------
            "audience_overlap": """Audience Overlap measures how much shared audience exists between multiple influencers you're considering.

We compare follower demographics, interests, and behavioral patterns to estimate how many people follow both influencers. This matters because working with influencers who share too much audience reduces your overall campaign reach. For example, two influencers with 60% overlap may reach largely the same people, meaning you're paying twice to reach the same audience. Lower overlap means broader reach.""",

            "growth_rate": """Growth Rate shows how quickly an influencer is gaining followers, expressed as a monthly percentage.

We track their follower count over several months to identify growth patterns. Healthy organic growth is typically 3-5% monthly, while strong growth is 5-10%. Sudden spikes above 10% can indicate viral content or potentially purchased followers and warrant closer investigation.

Consistent steady growth indicates rising influence and increasing relevance, while erratic growth patterns may suggest lower quality.""",

            "content_quality": """Content Quality Score assesses the overall professionalism and consistency of an influencer's content.

We evaluate visual quality including resolution and composition, posting frequency and consistency, content variety across different formats like posts and reels, and how effectively they use hashtags and captions. Higher scores indicate professional content creators who produce polished work consistently.

Better content quality typically leads to higher engagement and more successful brand partnerships.""",

            "brand_safety": """Brand Safety Score evaluates whether an influencer's content is appropriate for brand partnerships.

We analyze their content themes, language use, and past controversies to identify potential risks to your brand reputation. This includes checking for inappropriate content, controversial topics, or past brand conflicts.

Higher brand safety scores mean lower risk partnerships, protecting your brand reputation and ensuring the influencer aligns with your brand values."""
        }

        return explanations.get(metric_name, "This metric helps optimize your influencer discovery and campaign performance.")

    # ========================================================================
    # KNOWLEDGE BASE - Process Explanations
    # ========================================================================
    # Detailed explanations of major system processes

    def explain_process(self, process_name: str) -> str:
        """Explain how major processes work (agent tool) - User-focused, concise"""
        explanations = {
            "discovery": """**Finding Influencers**

We search across multiple platforms to find influencers matching your criteria. Typically takes 15-30 seconds and discovers 20-100 potential profiles per search.""",

            "enrichment": """**Analyzing Profiles**

We gather detailed metrics including followers, engagement rates, authenticity scores, and content performance. Takes 30-60 seconds to analyze 10-30 profiles.""",

            "ranking": """**Ranking by Relevance**

Profiles are ranked based on how well they match your criteria. The top results are the best overall matches for your campaign.""",

            "pdf_generation": """**PDF Reports**

We generate professional 11-page reports with influencer profiles, metrics, charts. Takes 5-10 seconds to create.""",

            "slot_filling": """**Clarifying Your Search**

We ask a few quick questions to understand exactly what you're looking for: niche, location, and follower range. This ensures you get the most relevant results.""",

            "static_search": """**Quick Search**

Search through our curated database of 500+ pre-analyzed influencers. Results in 5-10 seconds with minimal cost. Perfect for quick searches.""",

            "dynamic_search": """**Comprehensive Search**

Real-time discovery and analysis of influencers matching your criteria. Takes 60-120 seconds and returns 5-10 highly relevant profiles with detailed metrics and reports."""
        }

        return explanations.get(process_name, "This process is part of the influencer discovery and analysis pipeline.")

    # ========================================================================
    # KNOWLEDGE BASE - Feature Explanations
    # ========================================================================
    # Detailed explanations of system features

    def explain_feature(self, feature_name: str) -> str:
        """Explain how features work (agent tool)"""
        explanations = {
            "web_discovery": """Web Discovery is our intelligent search system that finds influencer profiles matching your criteria.

We search across multiple sources and platforms using AI-generated queries optimized for your specific requirements. The system discovers 20-100 potential influencer profiles per search, extracts their profile information, and removes duplicates.

For dynamic searches, this happens automatically after you specify your requirements. We use 3-8 targeted queries per search to ensure comprehensive coverage. This forms the foundation for detailed profile analysis that follows.""",

            "profile_enrichment": """Profile Enrichment gathers comprehensive metrics and analytics for each influencer we discover.

We retrieve complete profile data including follower counts, engagement metrics, bio information, verification status, and recent post performance. This gives you detailed insights into each influencer's audience size, content strategy, and engagement patterns.

Typically we enrich 10-30 profiles per search, taking 30-60 seconds to gather fresh, real-time data. This data powers our authenticity scoring, quality assessment, and ranking to help you make informed decisions.""",

            "ai_processing": """AI Processing powers the intelligence behind our platform, from understanding your requirements to ranking results.

We use advanced language models to interpret your natural language queries, generate optimized search strategies, match influencers to your niche semantically, assess follower authenticity, calculate quality scores, and rank results by relevance.

This happens throughout your entire search from initial query understanding through final report generation. AI Processing ensures you get accurate matches and intelligent recommendations without needing to specify complex criteria manually.""",

            "authenticity_checking": """Authenticity Checking validates the quality and genuineness of an influencer's followers and engagement.

We analyze follower growth patterns, engagement consistency, audience activity levels, comment quality, and demographic distribution to identify fake followers, bots, and inactive accounts. The system evaluates multiple signals to distinguish genuine audience members from suspicious accounts.

The result is an authenticity score from 0-100. Scores of 80-100 indicate highly authentic audiences with excellent quality. Scores of 60-79 show good authenticity with minor concerns. Lower scores suggest investigation is needed. High authenticity scores protect your campaign ROI by ensuring real people will see your brand message and actually engage with sponsored content.""",

            "time_breakdown": """Time Breakdown tracks how long each phase of your search takes to complete.

We measure three main phases: Discovery Time for finding profiles, Enrichment Time for gathering detailed metrics, and Analysis Time for AI processing and report generation. The total time is the sum of all phases.

Static searches using our database complete quickly in 5-10 seconds. Dynamic real-time searches take longer, typically 60-120 seconds total, with most time spent on profile discovery and enrichment. You can see this breakdown in your search history to understand what each search involved.""",

            "cost_calculation": """Cost Calculation provides transparent, usage-based pricing for all platform operations.

Your search costs come from three services: Web Discovery, Profile Enrichment, and AI Processing. Each is priced based on actual usage. Web Discovery charges per search query executed, Profile Enrichment charges per profile analyzed, and AI Processing charges per token processed.

Static searches using our cached database are very inexpensive, typically under a penny. Dynamic searches with real-time discovery cost more, typically twenty to fifty cents depending on how many profiles we discover and analyze. You get real-time cost tracking with per-search breakdowns and cumulative monitoring. There are no hidden fees, you only pay for what you use."""
        }

        return explanations.get(feature_name, "This feature is part of the CreatosConnect influencer discovery platform.")

    def get_all_metrics(self) -> Dict[str, SearchMetrics]:
        """Get all in-memory metrics (like old system)"""
        return self._metrics_store.copy()

    # ========================================================================
    # SYSTEM HEALTH MONITORING (New for Phase 4)
    # ========================================================================
    
    def get_system_health(self) -> Dict[str, Any]:
        """
        Get current system vitals (CPU, Memory, Redis Status).
        Used by /api/metrics/system endpoint.
        """
        # 1. Check Redis
        try:
            r = Redis.from_url(REDIS_URL, socket_connect_timeout=1)
            redis_status = r.ping()
            r.close()
        except Exception:
            redis_status = False
            
        return {
            "status": "online",
            "timestamp": datetime.now().isoformat(),
            "system": {
                "cpu_percent": psutil.cpu_percent(),
                "memory_percent": psutil.virtual_memory().percent,
            },
            "infrastructure": {
                "redis": "healthy" if redis_status else "down",
                "active_workers": self.get_active_workers_count()
            }
        }

    def get_active_workers_count(self) -> int:
        """Ping Celery to get active worker nodes."""
        try:
           # celery_app.control.ping() returns a list of responses
           # e.g. [{'celery@worker1': {'ok': 'pong'}}]
           workers = celery_app.control.ping(timeout=0.5)
           return len(workers) if workers else 0
        except Exception as e:
            logger.warning(f"Failed to check workers: {e}")
            return 0


# ============================================================================
# GLOBAL INSTANCE
# ============================================================================
# Single monitoring service instance used throughout the application
monitoring = MonitoringService()
