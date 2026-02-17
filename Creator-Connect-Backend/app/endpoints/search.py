from fastapi import APIRouter
from app.config.api_routes import PREFIX_SEARCH, SEARCH_DEFAULTS, SEARCH_DYNAMIC_PROMPT
from app.controllers import search_controller as dynamic_router

router = APIRouter(prefix=PREFIX_SEARCH, tags=["2. Search"])

# Register endpoints explicitly
router.add_api_route(
    path=SEARCH_DEFAULTS,
    endpoint=dynamic_router.get_default_filter_values,
    methods=["GET"],
    status_code=200,
    summary="Get default search values"
)

router.add_api_route(
    path=SEARCH_DYNAMIC_PROMPT,
    endpoint=dynamic_router.dynamic_search_prompt_only,
    methods=["POST"],
    status_code=200,
    summary="Dynamic search with Q&A flow"
)

from app.config.api_routes import SEARCH_INTERNAL_WEBHOOK

router.add_api_route(
    path=SEARCH_INTERNAL_WEBHOOK,
    endpoint=dynamic_router.receive_influencers_webhook,
    methods=["POST"],
    status_code=200,
    summary="INTERNAL ONLY - Auto-triggered webhook",
    tags=["Internal"],
    include_in_schema=True
)
