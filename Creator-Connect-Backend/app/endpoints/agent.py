from fastapi import APIRouter
from app.config.api_routes import PREFIX_AGENT, AGENT_CHAT, AGENT_HEALTH
from app.controllers import agent_controller as agent_router

router = APIRouter(prefix=PREFIX_AGENT, tags=["8. Agent Assistant"])

router.add_api_route(
    path=AGENT_CHAT,
    endpoint=agent_router.agent_chat,
    methods=["POST"],
    response_model=agent_router.ChatResponse,
    summary="Agent chat endpoint"
)

router.add_api_route(
    path=AGENT_HEALTH,
    endpoint=agent_router.health,
    methods=["GET"],
    summary="Agent health check"
)
