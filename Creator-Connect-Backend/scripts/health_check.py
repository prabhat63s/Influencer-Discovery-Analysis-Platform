"""
Health Check Script
===================
Verifies backend dependencies (DB, optional Redis, optional API).
Designed for CI/CD and pre-deployment. Exit 0 = healthy, non-zero = failure.

Usage:
    cd backend && python -m scripts.health_check
    cd backend && python -m scripts.health_check --api http://localhost:8000
    cd backend && python -m scripts.health_check --skip-redis
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

# -----------------------------------------------------------------------------
# Path setup
# -----------------------------------------------------------------------------
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Timeouts: fail fast so CI/CD and orchestrators get a clear signal
DB_CHECK_TIMEOUT_SEC = 10
REDIS_PING_TIMEOUT_SEC = 5
API_CHECK_TIMEOUT_SEC = 5


# -----------------------------------------------------------------------------
# Database: connectivity and basic schema
# -----------------------------------------------------------------------------
async def check_database() -> bool:
    """Verify DB connectivity with a simple query. Time-bounded."""
    try:
        from app.config.database import AsyncSessionLocal
        from sqlalchemy import text

        async with AsyncSessionLocal() as session:
            await asyncio.wait_for(session.execute(text("SELECT 1")), timeout=DB_CHECK_TIMEOUT_SEC)
        logger.info("Database: OK")
        return True
    except asyncio.TimeoutError:
        logger.error("Database: FAIL - timeout after %s s", DB_CHECK_TIMEOUT_SEC)
        return False
    except Exception as e:
        logger.error("Database: FAIL - %s", e)
        return False


# -----------------------------------------------------------------------------
# Redis: optional; skip if REDIS_URL not set or redis not installed
# -----------------------------------------------------------------------------
async def check_redis() -> bool:
    """Verify Redis connectivity when REDIS_URL is configured."""
    try:
        from app.config.settings import settings

        url = getattr(settings, "REDIS_URL", None) or ""
        if not url:
            logger.info("Redis: skipped (no REDIS_URL)")
            return True
        import redis

        def _ping() -> None:
            r = redis.from_url(url, socket_connect_timeout=REDIS_PING_TIMEOUT_SEC)
            r.ping()

        loop = asyncio.get_event_loop()
        await asyncio.wait_for(loop.run_in_executor(None, _ping), timeout=REDIS_PING_TIMEOUT_SEC + 2)
        logger.info("Redis: OK")
        return True
    except ImportError:
        logger.info("Redis: skipped (redis package not installed)")
        return True
    except asyncio.TimeoutError:
        logger.warning("Redis: FAIL - timeout after %s s", REDIS_PING_TIMEOUT_SEC)
        return False
    except Exception as e:
        logger.warning("Redis: FAIL - %s", e)
        return False


# -----------------------------------------------------------------------------
# API: optional GET /api/health
# -----------------------------------------------------------------------------
async def check_api(base_url: str) -> bool:
    """GET /api/health and expect 200."""
    try:
        import urllib.request

        url = f"{base_url.rstrip('/')}/api/health"
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=API_CHECK_TIMEOUT_SEC) as resp:
            if resp.status == 200:
                logger.info("API health: OK")
                return True
            logger.error("API health: unexpected status %s", resp.status)
            return False
    except Exception as e:
        logger.error("API health: FAIL - %s", e)
        return False


# -----------------------------------------------------------------------------
# Main: run checks, exit 0 only if all requested checks pass
# -----------------------------------------------------------------------------
async def main() -> int:
    parser = argparse.ArgumentParser(description="Backend health check (DB, Redis, API)")
    parser.add_argument("--api", default="", help="Base URL for API health (e.g. http://localhost:8000)")
    parser.add_argument("--skip-db", action="store_true", help="Skip database check")
    parser.add_argument("--skip-redis", action="store_true", help="Skip Redis check")
    args = parser.parse_args()

    ok = True
    if not args.skip_db:
        ok = await check_database() and ok
    if not args.skip_redis:
        ok = await check_redis() and ok
    if args.api:
        ok = await check_api(args.api) and ok
    return 0 if ok else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
