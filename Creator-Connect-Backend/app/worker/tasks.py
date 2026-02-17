"""
Celery Tasks
===========
Background jobs executed by the Celery worker process.
Includes:
1. Refreshing stale influencer data
2. Sending reports (future)
3. Batch scraping (future)
"""
import asyncio
import logging
from typing import List

from asgiref.sync import async_to_sync
from app.config.celery_app import celery_app
from app.services.core.persistence_service import InfluencerPersistenceService
from app.models.db_models import Influencer
from app.config.database import AsyncSessionLocal

# Configure Logger for Worker
logger = logging.getLogger(__name__)

# ============================================================================
# TASK: REFRESH INFLUENCER DATA
# ============================================================================

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def refresh_influencer_data(self, influencer_ids: List[str]):
    """
    Background Task: Refresh metrics for a list of influencer IDs.

    Runs BrightData only (no Spreadd). Data update stops after BrightData
    enrichment; then results are persisted. Spreadd is not used in this path.
    """
    logger.info(f"🔄 [Task] Starting refresh for {len(influencer_ids)} influencers")
    
    # Celery runs in a synchronous loop, but our DB service is async.
    # We use asgiref.sync.async_to_sync wrapper to bridge the gap.
    
    try:
        # Run the async logic synchronously
        result = async_to_sync(_refresh_logic)(influencer_ids)
        return result
    except Exception as e:
        logger.error(f"❌ [Task] Refresh failed: {e}")
        # Retry logic
        raise self.retry(exc=e)


def _build_profile_link(username: str, platform: str) -> str:
    """Build profile URL for BrightData (workflow: BrightData pipeline for refresh)."""
    if platform and platform.lower() != "instagram":
        return ""
    return f"https://www.instagram.com/{username}/"


async def _refresh_logic(influencer_ids: List[str]):
    """
    Refresh stale influencers: BrightData only, then persist.
    Does not run Spreadd; only BrightData enrichment and DB update.
    """
    # 1. Fetch influencers and build list with profile_link for BrightData
    profiles_to_refresh = []

    async with AsyncSessionLocal() as session:
        for inf_id in influencer_ids:
            inf = await session.get(Influencer, inf_id)
            if inf:
                profile_link = _build_profile_link(inf.username, inf.platform)
                if not profile_link:
                    logger.warning("Skipping non-Instagram profile %s", inf.username)
                    continue
                profiles_to_refresh.append({
                    "username": inf.username,
                    "name": inf.name,
                    "platform": inf.platform or "instagram",
                    "niche": inf.niche,
                    "profile_link": profile_link,
                    "profile_url": profile_link,
                })

    if not profiles_to_refresh:
        logger.warning("No valid profiles found to refresh")
        return {"status": "skipped", "count": 0}

    logger.info("Enriching %s profiles via BrightData only (no Spreadd)...", len(profiles_to_refresh))

    # 2. BrightData only — no Spreadd. Sync scraper, run in executor.
    from app.services.scrapers.brightdata_scraper import scraper_b_csv_brightdata

    parsed_query = {
        "niche": profiles_to_refresh[0].get("niche") or "Refresh",
        "location": "Global",
        "num_results": len(profiles_to_refresh),
    }
    loop = asyncio.get_event_loop()
    try:
        enriched_profiles = await loop.run_in_executor(
            None,
            lambda: scraper_b_csv_brightdata(profiles_to_refresh, parsed_query, skip_ai_processing=True),
        )
    except Exception as e:
        logger.exception("BrightData refresh failed: %s", e)
        return {"status": "failed", "error": str(e)}

    if not enriched_profiles:
        logger.warning("BrightData returned no enriched profiles")
        return {"status": "no_results", "count": 0}

    # 3. Persist updated data (source=background_refresh for audit)
    logger.info("Saving %s updated profiles...", len(enriched_profiles))
    success_count = 0
    async with AsyncSessionLocal() as session:
        for profile in enriched_profiles:
            try:
                await InfluencerPersistenceService.save_influencer_discovery(
                    session, profile, source="background_refresh"
                )
                success_count += 1
            except Exception as e:
                logger.error("Failed to save %s: %s", profile.get("username"), e)
        await session.commit()

    logger.info("Refresh complete. Updated %s/%s profiles.", success_count, len(profiles_to_refresh))
    return {"status": "success", "count": success_count}
