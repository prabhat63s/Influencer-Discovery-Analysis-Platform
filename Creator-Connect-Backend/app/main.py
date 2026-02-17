from __future__ import annotations

import logging
import os
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()  # Load environment variables before importing settings

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.config.settings import settings
from app.models.schema import LoginRequest, LoginResponse
from app.endpoints import (
    agent as agent_endpoints,
    search as search_endpoints,
    metrics as metrics_endpoints,
    report as report_endpoints,
    results as results_endpoints,
    internal_comparison as internal_comparison_endpoints
)
from app.services.data import temp_store
from app.utils.auth_utils import check_credentials
from app.utils.logging_config import configure_logging
from app.middleware.error_handler import global_error_handler
from app.middleware.request_logger import request_logger
from app.middleware.rate_limiter import rate_limiter_middleware

_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# Configure Logging
logger = configure_logging()

from contextlib import asynccontextmanager

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Life span context manager for startup and shutdown events.
    Handles resource initialization (storage, DB) and cleanup.
    """
    # [STARTUP]
    # Ensure storage directories exist
    STORAGE_PATH = _PROJECT_ROOT / "storage"
    UPLOADS_PATH = STORAGE_PATH / "uploads"
    RESULTS_PATH = STORAGE_PATH / "results"
    REPORTS_PATH = STORAGE_PATH / "reports"

    UPLOADS_PATH.mkdir(parents=True, exist_ok=True)
    RESULTS_PATH.mkdir(parents=True, exist_ok=True)
    REPORTS_PATH.mkdir(parents=True, exist_ok=True)
    logger.info("Storage directories initialized.")

    # Clean up expired sessions (>24 hours old)
    logger.info("Running startup cleanup of expired sessions...")
    try:
        stats = temp_store.cleanup_expired(threshold_hours=24)
        logger.info(f"Startup cleanup complete: {stats['sessions']} sessions, {stats['reports']} reports deleted")
    except Exception as e:
        logger.warning(f"Startup cleanup failed (non-critical): {e}")

    # Ensure database tables exist (Living Database)
    from app.config.database import init_db
    try:
        logger.info("Initializing database tables...")
        await init_db()
        logger.info("Database initialized successfully.")
    except Exception as e:
        logger.error(f"Database initialization failed: {e}")

    yield

    # [SHUTDOWN]
    logger.info("Shutdown complete.")

app = FastAPI(
    title="CreatosConnect API",
    version="0.1.0",
    description="""
    CreatosConnect - Influencer Discovery & Analysis Platform

    This API provides endpoints for discovering, analyzing, and generating reports on social media influencers.
    
    ### Recommended Workflow:

    1. **Authentication**: Login to obtain access token.
    2. **Search**: Discover influencers using natural language (Dynamic Search).
    3. **Analysis**: View detailed metrics and AI insights.
    4. **Reports**: Generate PDF reports for stakeholders.
    5. **Metrics**: Monitor system performance and usage.
    """,
    lifespan=lifespan,  # Use modern lifespan handler
    tags_metadata=[
        {
            "name": "1. Authentication",
            "description": "Login and authentication endpoints.",
        },
        {
            "name": "2. Search",
            "description": "Dynamic influencer discovery using AI and web scraping.",
        },
        {
            "name": "3. Analysis",
            "description": "Detailed metrics, insights, and influencer data retrieval.",
        },
        {
            "name": "4. Reports",
            "description": "PDF report generation and downloads.",
        },
        {
            "name": "5. Metrics",
            "description": "System performance monitoring and operational metrics.",
        },
        {
            "name": "Internal",
            "description": "Internal webhooks and callbacks. Not for public use.",
        },
    ],

)


# ==============================================================================
# MIDDLEWARE (CORS, etc.)
# ==============================================================================
# Configure CORS
origins = settings.CORS_ORIGINS
if settings.CORS_ALLOW_ALL_ORIGINS:
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)


from app.config.api_routes import AUTH_LOGIN, SYSTEM_HEALTH

@app.post(AUTH_LOGIN, tags=["1. Authentication"])
def login(payload: LoginRequest):
    """
    **Login to the CreatosConnect API**

    Authenticate with your username and password to access protected endpoints.

    **Request Body:**
    ```json
    {
      "username": "your_username",
      "password": "your_password"
    }
    ```

    **Returns:** Success message if credentials are valid

    **Note:** Save the authentication token for use with report generation and download endpoints.
    """
    if not check_credentials(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    # Login success is logged by uvicorn access log, no need to log here in production
    logger.info("Login successful for user %s", payload.username)
    return {"message": "Login successful", "token": "valid_token"}


@app.get(SYSTEM_HEALTH, tags=["7. System & Health"])
def health() -> dict[str, str]:
    """
    **Health check endpoint**

    Simple endpoint to verify the API is running and responsive.

    **Returns:** `{"status": "ok"}` when the API is healthy

    **Use for:**
    - Monitoring and uptime checks
    - Load balancer health probes
    - CI/CD pipeline validation
    - Quick API availability test
    """
    return {"status": "ok"}


# Include API routers in logical workflow order
# 1. Authentication - handled by @app.post above
# 2. Dynamic Search (Web Discovery)
app.include_router(search_endpoints.router)
# 4. Results & Analysis
app.include_router(results_endpoints.router)
app.include_router(internal_comparison_endpoints.router)
# 5. Reports
app.include_router(report_endpoints.router)
# 6. Metrics & Monitoring
app.include_router(metrics_endpoints.router)
# 7. Agent (Monitoring & Knowledge Assistant)
app.include_router(agent_endpoints.router)
# 8. System Health - handled by @app.get above

# 9. Utilities
from app.endpoints import proxy
app.include_router(proxy.router)