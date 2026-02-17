from fastapi import APIRouter
from app.config.api_routes import (
    PREFIX_METRICS,
    METRICS_SESSION,
    METRICS_SESSION_ANALYSIS,
    METRICS_ALL_SESSIONS,
    METRICS_EXPORT,
    METRICS_COMPARE,
    METRICS_INTERNAL_INSIGHTS,
    METRICS_SYSTEM
)
from app.controllers import metrics_controller as metrics_router, internal_comparison_controller as internal_comparison

router = APIRouter(prefix=PREFIX_METRICS, tags=["5. Metrics"])

router.add_api_route(
    path=METRICS_SYSTEM,
    endpoint=metrics_router.get_system_metrics,
    methods=["GET"],
    summary="Get System Health & Worker Status"
)

router.add_api_route(
    path=METRICS_SESSION,
    endpoint=metrics_router.get_conversation_metrics,
    methods=["GET"],
    summary="Get performance metrics for a search session"
)

router.add_api_route(
    path=METRICS_SESSION_ANALYSIS,
    endpoint=metrics_router.get_metrics_analysis,
    methods=["GET"],
    summary="Get AI-powered analysis of search performance"
)

router.add_api_route(
    path=METRICS_ALL_SESSIONS,
    endpoint=metrics_router.get_all_conversations_metrics,
    methods=["GET"],
    summary="Admin: Get all sessions metrics",
    tags=["Admin"]
)

router.add_api_route(
    path=METRICS_EXPORT,
    endpoint=metrics_router.export_metrics,
    methods=["POST"],
    summary="Admin: Export metrics to JSON",
    tags=["Admin"]
)

router.add_api_route(
    path=METRICS_COMPARE,
    endpoint=metrics_router.compare_two_conversations,
    methods=["GET"],
    summary="Admin: A/B test comparison",
    tags=["Admin"]
)

# Internal comparison is part of metrics/analysis conceptually, but mounted under PREFIX_SEARCH in original code.
# The user wants "dedicated scripts".
# Let's create a separate endpoint file for internal comparison if it has a different prefix.
# In previous step, I set internal_comparison to use PREFIX_SEARCH (/api).
# So it should probably go into endpoints/internal_comparison.py or similar.
