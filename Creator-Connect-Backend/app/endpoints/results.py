from fastapi import APIRouter
from app.config.api_routes import (
    PREFIX_SEARCH,
    SEARCH_RESULTS_DYNAMIC,
    SEARCH_RESULTS_ALL,
    SEARCH_ANALYSIS,
    SEARCH_PEERS_STATUS,
    SEARCH_INDUSTRY_INSIGHTS,
    SEARCH_AI_INSIGHT_TEST,
    SEARCH_AI_INSIGHT
)
from app.controllers import results_controller as results

router = APIRouter(prefix=PREFIX_SEARCH, tags=["3. Analysis"])

router.add_api_route(
    path=SEARCH_RESULTS_DYNAMIC,
    endpoint=results.get_prompt_dynamic_results,
    methods=["GET"],
    summary="Step 4: Get detailed analysis for DYNAMIC search influencer"
)

router.add_api_route(
    path=SEARCH_RESULTS_ALL,
    endpoint=results.get_all_prompt_results,
    methods=["GET"],
    summary="Get all results from a conversation (anchor + peers)"
)

router.add_api_route(
    path=SEARCH_ANALYSIS,
    endpoint=results.get_industry_standards_analysis,
    methods=["GET"],
    summary="Get industry standards analysis status and results"
)

router.add_api_route(
    path=SEARCH_PEERS_STATUS,
    endpoint=results.get_profession_peers_status_endpoint,
    methods=["GET"],
    summary="Get profession peers discovery status (for top influencer searches)"
)

router.add_api_route(
    path=SEARCH_INDUSTRY_INSIGHTS,
    endpoint=results.generate_industry_comparison_insights,
    methods=["POST"],
    summary="Generate AI insights for industry standard comparison"
)

router.add_api_route(
    path=SEARCH_AI_INSIGHT_TEST,
    endpoint=results.test_ai_insight,
    methods=["GET"],
    summary="Step 5: Test AI insight configuration (optional)"
)

router.add_api_route(
    path=SEARCH_AI_INSIGHT,
    endpoint=results.generate_ai_insight,
    methods=["POST"],
    summary="Step 6: Generate AI-powered insights for influencer"
)
