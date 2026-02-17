from fastapi import APIRouter
from app.config.api_routes import PREFIX_SEARCH, METRICS_INTERNAL_INSIGHTS
from app.controllers import internal_comparison_controller as internal_comparison

router = APIRouter(prefix=PREFIX_SEARCH, tags=["3. Analysis"])

router.add_api_route(
    path=METRICS_INTERNAL_INSIGHTS,
    endpoint=internal_comparison.generate_internal_comparison_insights,
    methods=["POST"],
    summary="Generate AI insights for internal comparison between top search results"
)
