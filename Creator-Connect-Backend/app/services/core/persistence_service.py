"""
Influencer Persistence Service
=============================
Living DB persistence: upsert by (platform, username), append metrics history.
Uses custom exceptions and input validation for production safety.
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.config.database import AsyncSessionLocal
from app.models.db_models import Influencer, MetricsHistory, RefreshLog, DiscoverySource
from app.models.exceptions import ValidationError, PipelineError
from app.utils.parsing import parse_percentage, parse_number

logger = logging.getLogger(__name__)

# Input bounds to prevent abuse and bad data
MAX_USERNAME_LENGTH = 100
MAX_PLATFORM_LENGTH = 20
MAX_SOURCE_LENGTH = 50


class InfluencerPersistenceService:
    """
    Persists influencer discoveries: upsert influencer, append metrics row, log refresh.
    """

    @staticmethod
    async def save_influencer_discovery(
        session: AsyncSession,
        profile_data: Dict[str, Any],
        source: str = "discovery",
    ) -> Optional[Influencer]:
        """
        Save or update one influencer; append metrics snapshot. Raises on invalid input.
        """
        username = profile_data.get("username") or profile_data.get("Id") or profile_data.get("name")
        platform = (profile_data.get("platform") or "instagram").strip()[:MAX_PLATFORM_LENGTH]

        if not username or not str(username).strip():
            raise ValidationError(
                "Influencer username is required",
                details={"profile_keys": list(profile_data.keys())},
            )
        username = str(username).lower().strip()[:MAX_USERNAME_LENGTH]
        source = (source or "discovery").strip()[:MAX_SOURCE_LENGTH]
        
        try:
            stmt = select(Influencer).filter_by(username=username, platform=platform)
            result = await session.execute(stmt)
            influencer = result.scalars().first()

            update_data = {
                "name": profile_data.get("name") or profile_data.get("NAME"),
                "profile_pic_url": profile_data.get("profile_pic_url"),
                "biography": profile_data.get("biography"),
                "niche": profile_data.get("niche") or profile_data.get("NICHE"),
                "location": profile_data.get("location") or profile_data.get("Location"),
                "email": profile_data.get("email"),
                "is_email_public": bool(profile_data.get("email")),
                "last_scraped_at": datetime.now(),
            }
            update_data = {k: v for k, v in update_data.items() if v is not None}

            if influencer:
                for key, value in update_data.items():
                    setattr(influencer, key, value)
                logger.debug("Updated existing influencer: %s", username)
            else:
                influencer = Influencer(
                    username=username,
                    platform=platform,
                    **update_data,
                )
                session.add(influencer)
                logger.debug("Created new influencer: %s", username)

            await session.flush()

            # Parse counts/percentages safely (handles '94.0K', '0.00%', 'N/A', etc.)
            from app.services.core.search_filters import parse_followers_to_int

            followers = profile_data.get("followers")
            engagement = profile_data.get("engagement_rate")
            if followers is not None or engagement is not None:
                metrics_entry = MetricsHistory(
                    influencer_id=influencer.id,
                    follower_count=parse_followers_to_int(followers) if followers else 0,
                    following_count=parse_number(profile_data.get("following", 0)),
                    posts_count=parse_number(profile_data.get("posts_count", 0)),
                    engagement_rate=parse_percentage(engagement),
                    auth_score=parse_percentage(profile_data.get("authenticity_score", 0)),
                    quality_score=parse_percentage(profile_data.get("influencer_quality_score", 0)),
                    raw_data=profile_data,
                )
                session.add(metrics_entry)

            log_entry = RefreshLog(
                influencer_id=influencer.id,
                operation_type=source.upper(),
                status="SUCCESS",
                details=f"Updated via {source}",
            )
            session.add(log_entry)

            # Audit: discovery_sources (workflow: how/when this influencer was discovered)
            search_query = profile_data.get("search_query") or profile_data.get("original_query")
            if isinstance(search_query, str):
                search_query = search_query.strip()[:2000]
            discovery_entry = DiscoverySource(
                influencer_id=influencer.id,
                source_type=source.lower(),
                search_query=search_query,
                serp_rank=profile_data.get("serp_rank"),
            )
            session.add(discovery_entry)
            return influencer

        except IntegrityError as e:
            await session.rollback()
            raise PipelineError(
                "Database constraint violation while saving influencer",
                details={"username": username, "platform": platform, "orig": str(e)},
            ) from e
        except ValidationError:
            await session.rollback()
            raise
        except Exception as e:
            logger.exception("Failed to persist influencer %s", username)
            await session.rollback()
            raise PipelineError(
                "Failed to persist influencer",
                details={"username": username, "error": str(e)},
            ) from e

    @staticmethod
    async def bulk_save_influencers(profiles: List[Dict[str, Any]]) -> int:
        """
        Batch upsert profiles in one transaction. On failure rolls back and re-raises.
        """
        if not profiles:
            return 0
        count = 0
        async with AsyncSessionLocal() as session:
            try:
                for profile in profiles:
                    await InfluencerPersistenceService.save_influencer_discovery(
                        session, profile, source="bulk_import"
                    )
                    count += 1
                await session.commit()
                logger.info("Bulk saved %s influencers", count)
            except (ValidationError, PipelineError):
                await session.rollback()
                raise
            except Exception as e:
                logger.exception("Bulk save failed after %s records", count)
                await session.rollback()
                raise PipelineError(
                    "Bulk influencer save failed",
                    details={"saved_count": count, "error": str(e)},
                ) from e
        return count
