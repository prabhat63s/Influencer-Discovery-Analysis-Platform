"""
Search Mode Service
===================
Unified hybrid search: DB-first, then full / partial / no-match per living_database_workflow.
- Full match: serve from DB, trigger background refresh.
- Partial match: serve DB results, signal remaining count (controller may run pipeline for rest).
- No match: signal web discovery.
Inputs are validated and bounded to prevent abuse and injection risk.
"""
import logging
from datetime import datetime
from typing import List, Dict, Any, Tuple, Optional

from sqlalchemy import select, or_, and_
from sqlalchemy.orm import selectinload

from app.models.db_models import Influencer
from app.config.database import AsyncSessionLocal
from app.services.reporting.monitoring_service import SearchMetrics
from app.services.data.redis_cache import cache_response

logger = logging.getLogger(__name__)

# -----------------------------------------------------------------------------
# Constants (workflow-aligned)
# -----------------------------------------------------------------------------
# Staleness: only trigger BrightData refresh when last update was >= 12 hours ago.
# If last update was less than 12 hours ago, do not call BrightData.
STALE_THRESHOLD_HOURS = 12
MAX_NICHE_LENGTH = 200
MAX_LOCATION_LENGTH = 200
MAX_NUM_RESULTS = 1000
DEFAULT_NUM_RESULTS = 500


def _sanitize_search_param(value: Optional[str], max_len: int) -> Optional[str]:
    """
    Return stripped, length-limited string for safe use in ILIKE queries.
    Escapes SQL LIKE wildcards (% and _) to prevent semantic injection.
    ORM uses bound parameters so no raw SQL concatenation.
    """
    if value is None or not isinstance(value, str):
        return None
    s = value.strip()[:max_len]
    if not s:
        return None
    # Escape LIKE metacharacters so user input cannot broaden match
    s = s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return s


class SearchModeService:
    """
    Routes search to Living DB or web discovery.
    Returns (results or None, source_label, remaining_count).
    """

    @staticmethod
    async def unified_search(
        user_query: str,
        parsed_query: Dict[str, Any],
        conversation_id: str,
        metrics: SearchMetrics,
    ) -> Tuple[Optional[List[Dict[str, Any]]], str, int]:
        """
        Unified search entry. Returns (results, source, remaining_count).
        - FULL_MATCH: results from DB, remaining_count=0.
        - PARTIAL_MATCH: results from DB, remaining_count = requested - len(results).
        - WEB_DISCOVERY: results=None, remaining_count = requested.
        """
        requested = min(
            int(parsed_query.get("num_results") or DEFAULT_NUM_RESULTS),
            MAX_NUM_RESULTS,
        )
        requested = max(1, requested)

        local_results = await SearchModeService.search_local_db(parsed_query)
        count = len(local_results) if local_results else 0

        if count >= requested:
            # Full match: serve from DB, trigger background refresh
            logger.info("Local full match: found %s influencers in DB", count)
            SearchModeService._check_staleness_and_refresh(
                local_results[:requested]  # type: ignore
            )
            serialized = [
                SearchModeService._serialize_influencer(inf)
                for inf in (local_results or [])[:requested]
            ]
            return serialized, "LOCAL_DB", 0

        if count == 0:
            logger.info("Local miss: triggering web discovery")
            return None, "WEB_DISCOVERY", requested

        # Partial match: return DB results; remaining = requested - count
        remaining = requested - count
        logger.info("Partial match: %s from DB, %s remaining", count, remaining)
        SearchModeService._check_staleness_and_refresh(local_results)  # type: ignore
        serialized = [
            SearchModeService._serialize_influencer(inf) for inf in (local_results or [])
        ]
        return serialized, "PARTIAL_MATCH", remaining

    @staticmethod
    async def search_local_db(parsed_query: Dict[str, Any]) -> List[Influencer]:
        """
        Query local DB with validated, length-bounded params. Safe for production.
        """
        niche = _sanitize_search_param(
            parsed_query.get("niche"), MAX_NICHE_LENGTH
        )
        location = _sanitize_search_param(
            parsed_query.get("location"), MAX_LOCATION_LENGTH
        )
        min_followers = parsed_query.get("min_followers")
        max_followers = parsed_query.get("max_followers")
        num_results = min(
            int(parsed_query.get("num_results") or DEFAULT_NUM_RESULTS),
            MAX_NUM_RESULTS,
        )
        num_results = max(1, num_results)

        async with AsyncSessionLocal() as session:
            try:
                stmt = select(Influencer).options(
                    selectinload(Influencer.metrics_history)
                )
                filters = []

                if niche and niche.lower() != "generic":
                    # ORM binds; escape='\\' so escaped %/_ in niche are literal (security)
                    pattern_niche = f"%{niche}%" if niche else ""
                    filters.append(
                        or_(
                            Influencer.niche.ilike(pattern_niche, escape="\\"),
                            Influencer.biography.ilike(pattern_niche, escape="\\"),
                        )
                    )
                if location and location.lower() != "global":
                    pattern_loc = f"%{location}%" if location else ""
                    filters.append(Influencer.location.ilike(pattern_loc, escape="\\"))

                if filters:
                    stmt = stmt.filter(and_(*filters))
                stmt = stmt.limit(1000)

                result = await session.execute(stmt)
                candidates = list(result.scalars().all())

                final_results: List[Influencer] = []
                for inf in candidates:
                    latest_metric = None
                    if inf.metrics_history:
                        inf.metrics_history.sort(
                            key=lambda x: (x.recorded_at is not None, x.recorded_at or datetime.min),
                            reverse=True,
                        )
                        latest_metric = inf.metrics_history[0]
                    followers = (
                        latest_metric.follower_count if latest_metric else 0
                    ) or 0
                    if min_followers is not None and followers < min_followers:
                        continue
                    if max_followers is not None and followers > max_followers:
                        continue
                    final_results.append(inf)
                    if len(final_results) >= num_results:
                        break

                return final_results

            except Exception as e:
                logger.exception("Local DB search error: %s", e)
                return []

    @staticmethod
    def _check_staleness_and_refresh(influencers: List[Influencer]):
        """
        Fire-and-forget check for stale data.
        Only queue BrightData refresh when last update was >= 12 hours ago.
        If last update was less than 12 hours ago, do not call BrightData.
        """
        now = datetime.now()
        ids_to_refresh = []

        for inf in influencers:
            last_scraped = inf.last_scraped_at
            if not last_scraped:
                ids_to_refresh.append(inf.id)
                continue

            # Compare as naive for elapsed time (last update >= 12 hours ago = stale)
            last_naive = last_scraped.replace(tzinfo=None) if last_scraped.tzinfo else last_scraped
            delta = now - last_naive
            if delta.total_seconds() >= STALE_THRESHOLD_HOURS * 3600:
                ids_to_refresh.append(inf.id)

        if ids_to_refresh:
            logger.info("🔄 Detected %s stale profiles (last update >= %s h). Queueing BrightData refresh.",
                        len(ids_to_refresh), STALE_THRESHOLD_HOURS)
            from app.worker.tasks import refresh_influencer_data
            refresh_task = refresh_influencer_data.delay(ids_to_refresh)
            logger.info("Task queued: %s", refresh_task.id)

    @staticmethod
    def _serialize_influencer(inf: Influencer) -> Dict[str, Any]:
        """
        Convert DB model to frontend dictionary; use latest metrics by recorded_at.
        Extracts posts, post_analysis, and hashtag_analysis from raw_data when present,
        so the frontend receives full post data for AI insights and post displays.
        """
        latest_metric = None
        if inf.metrics_history:
            inf.metrics_history.sort(
                key=lambda x: (x.recorded_at is not None, x.recorded_at or datetime.min),
                reverse=True,
            )
            latest_metric = inf.metrics_history[0]

        # Safely extract raw_data (JSON column); ensure we have a dict
        raw = (latest_metric.raw_data if latest_metric else None) or {}
        if not isinstance(raw, dict):
            logger.warning("Metrics raw_data for %s is not a dict (type=%s), using empty", inf.username, type(raw).__name__)
            raw = {}

        profile_link = raw.get("profile_link") or raw.get("PROFILE_LINK")
        if not profile_link:
            profile_link = f"https://www.instagram.com/{inf.username}/" if inf.platform == "instagram" else ""

        # Start with raw_data to preserve scraped details (posts, post_analysis, hashtags)
        out: Dict[str, Any] = dict(raw)

        # Overlay structured fields (authoritative for profile + metrics)
        out.update({
            "id": inf.id,
            "username": inf.username,
            "name": inf.name,
            "NAME": inf.name,
            "profile_pic_url": inf.profile_pic_url or out.get("profile_pic_url"),
            "profile_link": profile_link,
            "PROFILE_LINK": profile_link,
            "platform": inf.platform,
            "niche": inf.niche,
            "NICHE": inf.niche,
            "location": inf.location,
            "Location": inf.location,
            "followers": latest_metric.follower_count if latest_metric else out.get("followers", 0),
            "engagement_rate": latest_metric.engagement_rate if latest_metric else out.get("engagement_rate", 0.0),
            "following": latest_metric.following_count if latest_metric else out.get("following", 0),
            "posts_count": latest_metric.posts_count if latest_metric else out.get("posts_count", 0),
            "authenticity_score": latest_metric.auth_score if latest_metric else out.get("authenticity_score", 0),
            "influencer_quality_score": latest_metric.quality_score if latest_metric else out.get("influencer_quality_score", 0),
            "source": "database",
            "is_verified": inf.is_verified,
            "biography": inf.biography or out.get("biography"),
        })

        # Explicitly surface post data for frontend / get_prompt_dynamic_results
        # (raw_data may use different keys; ensure canonical keys exist)
        if "posts" not in out or out.get("posts") is None:
            out["posts"] = raw.get("posts") or []
        if "post_analysis" not in out or out.get("post_analysis") is None:
            out["post_analysis"] = raw.get("post_analysis") or {}
        if "hashtag_analysis" not in out or out.get("hashtag_analysis") is None:
            out["hashtag_analysis"] = raw.get("hashtag_analysis") or {}

        return out
