from __future__ import annotations

from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    token: str


class MetricsRecord(BaseModel):
    Name: Optional[str] = None
    PROFILE_LINK: Optional[str] = None
    followers: float
    following: float
    posts: float
    average_likes: float
    average_comments: float
    suspicious_fake_followers: float
    real_followers: float
    real_percentage: float
    RATE: float
    NICHE: Optional[str] = None
    CITY__STATE__BASE: Optional[str] = Field(default=None, alias="CITY / STATE / BASE")
    engagement_rate: float
    authenticity_score: float
    health_score: float
    influencer_quality_score: float
    true_influence_index: float
    campaign_roi_score: float

    class Config:
        populate_by_name = True


class MetricsListResponse(BaseModel):
    count: int
    results: List[Dict[str, Any]]


class MetricsSummaryResponse(BaseModel):
    total_influencers: int
    avg_engagement_rate: float
    avg_authenticity_score: float
    avg_health_score: float
    avg_fake_follower_ratio: float
    avg_cost_per_engagement: float
    top_niche_by_engagement: str
    top_niche_by_quality: str


class InfluencerSummary(BaseModel):
    id: str
    name: str
    platform: str
    followers: int
    profile_link: str
    engagement_rate: float


class ChartData(BaseModel):
    labels: List[str]
    data: List[float]
    title: Optional[str] = None


class InfluencerDetail(BaseModel):
    id: str
    name: str
    platform: str
    followers: int
    engagement_rate: float
    demographics_pie: ChartData
    engagement_bar: ChartData
    notes: Optional[str] = None


class ReportRequest(BaseModel):
    file_hash: Optional[str] = None
    influencer_id: str  # Can be search ID or analysis ID


class ReportResponse(BaseModel):
    report_name: str
    download_url: str


class ChatPromptResponse(BaseModel):
    """Response model for chat-based prompt completion."""
    complete: bool = Field(..., description="Whether all required slots are filled")
    message: Optional[str] = Field(default=None, description="Response message from assistant")
    next_question: Optional[str] = Field(default=None, description="Next question to ask if incomplete")
    asking_for: Optional[str] = Field(default=None, description="Which slot is being asked about")
    missing_count: Optional[int] = Field(default=None, description="Number of missing slots")
    filled_slots: Dict[str, Any] = Field(default_factory=dict, description="Current filled slots")
    final_prompt: Optional[str] = Field(default=None, description="Complete prompt when all slots are filled")
    search_results: Optional[List[Dict[str, Any]]] = Field(default=None, description="Search results if complete (Active pipeline uses Dict for flexibility, will migrate to strict InfluencerProfile)")
    conversation_id: Optional[str] = Field(default=None, description="Conversation ID for retrieving results later")


class SearchResult(BaseModel):
    """
    Standardized influencer profile model.
    Replaces loose Dict[str, Any] in pipeline.
    """
    id: Optional[str] = None
    username: str
    name: Optional[str] = None
    profile_link: str
    platform: str = "instagram"
    
    # Metrics
    followers: int = 0
    following: int = 0
    posts_count: int = 0
    engagement_rate: float = 0.0
    average_likes: int = 0
    average_comments: int = 0
    average_views: int = 0
    
    # Discovery Metadata
    niche: Optional[str] = None
    location: Optional[str] = None
    profile_pic_url: Optional[str] = None
    
    # Custom Scores
    authenticity_score: float = 0.0
    health_score: float = 0.0
    influencer_quality_score: float = 0.0
    
    # Fees (Optional)
    rate: Optional[int] = None
    min_rate: Optional[int] = None
    max_rate: Optional[int] = None

    class Config:
        extra = "ignore"  # Allow extra fields temporarily but don't expose them indiscriminately