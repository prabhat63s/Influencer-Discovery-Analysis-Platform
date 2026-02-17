"""
Database Models
==============
SQLAlchemy models for the Living Influencer Database.
Uses UUIDs for primary keys to ensure scalability and independence.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from sqlalchemy import Column, String, Integer, Float, Boolean, DateTime, ForeignKey, JSON, Text, Index, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from app.config.database import Base


# ============================================================================
# TRAITS / LOOKUP TABLES
# ============================================================================

class Niche(Base):
    """Normalized list of niches/categories."""
    __tablename__ = "niches"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Niche(name='{self.name}')>"


class Location(Base):
    """Normalized list of locations (Cities/Countries)."""
    __tablename__ = "locations"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    country_code = Column(String(2), index=True, nullable=True)  # ISO 3166-1 alpha-2
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Location(name='{self.name}')>"


# ============================================================================
# CORE INFLUENCER MODEL
# ============================================================================

class Influencer(Base):
    """
    Core Influencer Profile.
    Stores stable, slowly-changing data about an influencer.
    """
    __tablename__ = "influencers"

    # UUID for scalability/merging
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Discovery Fields
    platform = Column(String, index=True, nullable=False, default="instagram")
    username = Column(String, index=True, nullable=False)
    
    # Metadata
    name = Column(String, nullable=True)
    profile_pic_url = Column(String, nullable=True)
    biography = Column(Text, nullable=True)
    is_verified = Column(Boolean, default=False)
    
    # Core Categorization (Foreign Keys optional, often strings are faster for search)
    # Using simple strings for now to avoid strict FK constraints during scraping
    niche = Column(String, index=True, nullable=True)
    location = Column(String, index=True, nullable=True)
    
    # Contact Info (PII)
    email = Column(String, nullable=True)
    is_email_public = Column(Boolean, default=False)
    
    # Lifecycle & Staleness
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    # Crucial for Staleness Logic: used to determine if > 12h old (needs refresh)
    last_scraped_at = Column(DateTime(timezone=True), nullable=True, index=True)
    
    # Relationships
    # One-to-Many: Each influencer has multiple snapshots of metrics over time
    metrics_history = relationship("MetricsHistory", back_populates="influencer", cascade="all, delete-orphan")
    
    # Constraints
    # Ensure unique platform+username combination
    __table_args__ = (
        UniqueConstraint('platform', 'username', name='uq_platform_username'),
    )

    def __repr__(self):
        return f"<Influencer(username='{self.username}', platform='{self.platform}')>"


# ============================================================================
# METRICS & ANALYTICS
# ============================================================================

class MetricsHistory(Base):
    """
    Time-series record of influencer metrics.
    A new row is added every time we deeply analyze/scrape an influencer.
    """
    __tablename__ = "metrics_history"

    id = Column(Integer, primary_key=True, index=True)
    influencer_id = Column(String, ForeignKey("influencers.id"), nullable=False, index=True)
    
    # Snapshot Timestamp
    recorded_at = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # Quantitative Metrics
    follower_count = Column(Integer, nullable=True)
    following_count = Column(Integer, nullable=True)
    posts_count = Column(Integer, nullable=True)
    engagement_rate = Column(Float, nullable=True)
    
    # Quality Scores (0-100)
    auth_score = Column(Float, nullable=True)  # Authenticity
    health_score = Column(Float, nullable=True)
    quality_score = Column(Float, nullable=True)
    
    # Fees (Estimated)
    avg_rate = Column(Integer, nullable=True)
    
    # Detailed JSON Data (Stores the full scrape raw data)
    # Compatible with both SQLite (JSON types as Text) and Postgres (JSONB)
    raw_data = Column(JSON, nullable=True)
    
    # Relationships
    influencer = relationship("Influencer", back_populates="metrics_history")

    def __repr__(self):
        return f"<MetricsHistory(influencer='{self.influencer_id}', date='{self.recorded_at}')>"


# ============================================================================
# DISCOVERY AUDIT (workflow: who found this influencer, when, how)
# ============================================================================

class DiscoverySource(Base):
    """
    Audit trail: how and when each influencer was discovered.
    source_type: 'serp', 'brightdata', 'manual', 'bulk_import', 'background_refresh'.
    """
    __tablename__ = "discovery_sources"

    id = Column(Integer, primary_key=True, index=True)
    influencer_id = Column(String, ForeignKey("influencers.id"), nullable=False, index=True)
    source_type = Column(String(50), nullable=False)  # serp, brightdata, manual, bulk_import, background_refresh
    search_query = Column(Text, nullable=True)
    serp_rank = Column(Float, nullable=True)
    discovered_at = Column(DateTime(timezone=True), server_default=func.now())


# ============================================================================
# OPERATIONAL LOGS
# ============================================================================

class RefreshLog(Base):
    """
    Audit log for data refresh operations.
    Tracks when and why an influencer was updated.
    """
    __tablename__ = "refresh_logs"
    
    id = Column(Integer, primary_key=True, index=True)
    influencer_id = Column(String, ForeignKey("influencers.id"), nullable=True)
    
    operation_type = Column(String, nullable=False) # e.g., "DISCOVERY", "REFRESH", "MANUAL_UPDATE"
    status = Column(String, nullable=False) # "SUCCESS", "FAILED"
    details = Column(Text, nullable=True) # Error message or summary
    
    duration_ms = Column(Integer, nullable=True)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<RefreshLog(op='{self.operation_type}', status='{self.status}')>"
