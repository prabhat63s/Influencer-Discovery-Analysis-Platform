"""
Database Configuration
=====================
Handles asynchronous database connections using SQLAlchemy.
Supports PostgreSQL (Production) and SQLite (Development).
"""
import os
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.config.settings import settings

# Determine Database URL (workflow: SQLite dev, PostgreSQL prod)
# Priority: env DATABASE_URL > settings.DATABASE_URL (settings applies default SQLite if empty)
_env_url = (os.getenv("DATABASE_URL") or "").strip()
DATABASE_URL = _env_url or (getattr(settings, "DATABASE_URL", None) or "").strip()
if not DATABASE_URL:
    DATABASE_URL = "sqlite+aiosqlite:///./creatos_connect.db"
    
# Debug logging
import logging
logger = logging.getLogger(__name__)

if "sqlite" in DATABASE_URL:
    logger.info(f"Using SQLite Database: {DATABASE_URL}")
    # SQLite specific connection args
    connect_args = {"check_same_thread": False}
else:
    logger.info("Using PostgreSQL Database")
    connect_args = {}

# Create Async Engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False, # Set to True to see raw SQL queries in logs
    future=True,
    connect_args=connect_args
)

# Create Session Factory
AsyncSessionLocal = sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# Declarative Base for Models
Base = declarative_base()


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for getting an async database session.
    Yields the session and ensures it closes after use.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    """
    Initialize database tables (used for dev/testing).
    In production, use Alembic migrations instead.
    Ensures all models are registered with Base before create_all (avoids empty schema).
    """
    from app.models import db_models  # noqa: F401 - register all tables with Base.metadata
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
