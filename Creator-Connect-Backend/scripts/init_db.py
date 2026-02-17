"""
Initialize Database Script
=========================
Creates all database tables from SQLAlchemy models (Living Database workflow).
Use for first-time setup or dev; in production prefer Alembic migrations.

Usage:
    cd backend && python -m scripts.init_db

Exit: 0 on success, 1 on failure. Ensures engine disposal to avoid connection leaks.
"""
import asyncio
import logging
import sys
from pathlib import Path

# -----------------------------------------------------------------------------
# Path setup: ensure backend/app is importable
# -----------------------------------------------------------------------------
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

# Import Base from db_models so all models are registered before create_all
from app.config.database import init_db, engine
from app.models.db_models import Base

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# Timeout for DB init (avoids hanging on unreachable DB)
INIT_DB_TIMEOUT_SEC = 30


async def main() -> None:
    logger.info("Starting database initialization...")
    try:
        await asyncio.wait_for(init_db(), timeout=INIT_DB_TIMEOUT_SEC)
        logger.info("Database tables created successfully.")
    except asyncio.TimeoutError:
        logger.error("Database initialization timed out after %s seconds.", INIT_DB_TIMEOUT_SEC)
        sys.exit(1)
    except Exception as e:
        logger.exception("Database initialization failed.")
        logger.error("Error: %s", e)
        sys.exit(1)
    finally:
        await engine.dispose()
        logger.debug("Engine disposed.")


if __name__ == "__main__":
    asyncio.run(main())
