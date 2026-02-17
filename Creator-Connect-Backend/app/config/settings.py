from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, field_validator
from pathlib import Path
import json
import os

# Calculate project root (3 levels up from this file: backend/app/config/settings.py)
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Default SQLite path for development (workflow: SQLite dev, PostgreSQL prod via DATABASE_URL)
_DEFAULT_SQLITE_PATH = f"sqlite+aiosqlite:///{(_PROJECT_ROOT / 'creatos_connect.db').as_posix()}"


class Settings(BaseSettings):
    """
    Application settings. All secrets from environment; never log or expose.
    Production: set DATABASE_URL (PostgreSQL), ENV=production, CORS_ORIGINS.
    """
    model_config = SettingsConfigDict(
        env_file=str(_PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )

    # Environment
    ENV: str = Field(default="development", description="Environment: 'production' or 'development'")
    
    # Paths
    PROJECT_ROOT: Path = _PROJECT_ROOT
    BASE_DIR: Path = PROJECT_ROOT

    # Auth (single-user portal credentials) — never log or expose
    HARD_CODED_USERNAME: str = Field(..., description="Username for password-protected endpoints")
    HARD_CODED_PASSWORD: str = Field(..., description="Password for password-protected endpoints")
    STORAGE_PATH: Path = PROJECT_ROOT / "storage"
    UPLOADS_PATH: Path = STORAGE_PATH / "uploads"
    RESULTS_PATH: Path = STORAGE_PATH / "results"
    REPORTS_PATH: Path = STORAGE_PATH / "reports"
    DYNAMIC_RESULTS_PATH: Path = STORAGE_PATH / "dynamic_results"

    # Database: workflow — SQLite (dev) / PostgreSQL (prod via DATABASE_URL)
    DATABASE_FILE: Path = PROJECT_ROOT / "influencer.db"
    DATABASE_URL: str = Field(
        default="",
        description="Database URL. Empty => SQLite. Production: set to PostgreSQL (e.g. Neon)."
    )
    
    # Production Connection Pool Defaults
    DB_POOL_SIZE: int = Field(default=5, description="SQLAlchemy pool size")
    DB_MAX_OVERFLOW: int = Field(default=10, description="SQLAlchemy max overflow")
    DB_POOL_TIMEOUT: int = Field(default=30, description="SQLAlchemy pool timeout")
    
    # Redis (Task Queue & Cache)
    REDIS_URL: str = Field(default="redis://localhost:6379/0", description="Redis connection URL")

    # Rate limiting (industry practice: protect API from abuse)
    RATE_LIMIT_REQUESTS: int = Field(default=60, description="Max requests per window per client")
    RATE_LIMIT_WINDOW_SEC: int = Field(default=60, description="Rate limit window in seconds")
    MAX_QUERY_LENGTH: int = Field(default=2000, description="Max length for search query input")

    # External APIs / Data sources
    GEMINI_API_KEY: str = Field(..., description="Google Gemini API Key from .env file")
    GEMINI_MODEL: str = Field(default="gemini-2.5-flash-lite", description="Gemini model name (e.g. 'gemini-1.5-flash', 'gemini-1.5-pro', 'gemini-2.0-flash-exp')")
    OPENAI_API_KEY: str = Field(..., description="OpenAI API Key from .env file")
    OPENAI_MODEL: str = Field(default="gpt-4o-mini", description="OpenAI model name")
    
    # Dynamic Search API Keys
    SERP_API_KEY: str = Field(..., description="SerpAPI Key for Google search enrichment")
    BRIGHTDATA_API_KEY: str = Field(..., description="BrightData API Key for Instagram scraping")
    BRIGHTDATA_DATASET_ID: str = Field(..., description="BrightData Dataset ID for Instagram scraping")
    
    # Dynamic Search URLs and Configuration
    SPREADD_URL: str = Field(..., description="Spreadd.io URL for fake follower detection")
    INFLUENCER_DATABASE: str = Field(..., description="Default influencer database CSV filename")
    ENDPOINT_URL: str = Field(..., description="Webhook endpoint URL for sending results")
    BRIGHTDATA_TIMEOUT_SECONDS: int = Field(default=120, description="Timeout for BrightData snapshot GET (polling). Trigger POST uses BRIGHTDATA_TRIGGER_TIMEOUT_SECONDS.")
    BRIGHTDATA_TRIGGER_TIMEOUT_SECONDS: int = Field(default=45, description="Timeout for BrightData trigger POST (should return immediately with snapshot_id).")
    BRIGHTDATA_API_BASE: str = Field(default="https://api.brightdata.com", description="BrightData API base URL")
    BRIGHTDATA_SCRAPE_PATH: str = Field(default="/datasets/v3/scrape", description="BrightData sync scrape endpoint (1-min server limit; prefer trigger for large batches).")
    BRIGHTDATA_TRIGGER_PATH: str = Field(default="/datasets/v3/trigger", description="BrightData async trigger endpoint (returns snapshot_id immediately, then poll snapshot).")
    SERPAPI_SEARCH_URL: str = Field(default="https://serpapi.com/search", description="SerpAPI search endpoint")
    SERPAPI_TIMEOUT: int = Field(default=20, description="Timeout in seconds for SerpAPI requests")
    INSTAGRAM_BASE_URL: str = Field(default="https://www.instagram.com", description="Instagram base URL for normalization")

    INFLUENCER_DATA_PATH: str | None = Field(
        default=None,
        description="Optional path to influencer dataset (legacy dynamic data source)."
    )


    # Internal webhook protection (set WEBHOOK_SECRET in production to require X-Webhook-Secret header)
    WEBHOOK_SECRET: str = Field(default="", description="Optional secret for /influencers/webhook; if set, request must send X-Webhook-Secret header")

    # CORS
    CORS_ORIGINS: list[str] = Field(default=["https://creators-connect.vercel.app", "http://localhost:3000"], description="Allowed origins for CORS", validation_alias="CORS_ORIGINS")
    CORS_ALLOW_ALL_ORIGINS: bool = Field(default=False, description="Allow all origins for CORS")
    CORS_ALLOW_CREDENTIALS: bool = Field(default=True, description="Allow credentials for CORS")
    CORS_ALLOW_METHODS: list[str] = Field(default=["*"], description="Allowed methods for CORS")
    CORS_ALLOW_HEADERS: list[str] = Field(default=["*"], description="Allowed headers for CORS")

    @field_validator('CORS_ORIGINS', 'CORS_ALLOW_METHODS', 'CORS_ALLOW_HEADERS', mode='before')
    @classmethod
    def parse_cors_list(cls, v):
        """Parse CORS lists from various formats (JSON array string, comma-separated, or list)."""
        if isinstance(v, list):
            return v
        if isinstance(v, str):
            # Try to parse as JSON first
            if v.startswith('[') and v.endswith(']'):
                try:
                    parsed = json.loads(v)
                    if isinstance(parsed, list):
                        return parsed
                except json.JSONDecodeError:
                    pass
            # Fall back to comma-separated
            return [origin.strip() for origin in v.split(',') if origin.strip()]
        return v

    def __init__(self, **values):
        super().__init__(**values)
        # Workflow: DATABASE_URL from env in prod; empty => SQLite for dev
        url = (self.DATABASE_URL or "").strip()
        if not url:
            self.DATABASE_URL = _DEFAULT_SQLITE_PATH


settings = Settings()