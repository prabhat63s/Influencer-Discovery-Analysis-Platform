"""
Agent Router - OpenAI Function Calling for Monitoring & Knowledge
Uses centralized settings and prompts
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional
import json
import logging
from openai import OpenAI

from app.config.settings import settings
from app.prompts import AGENT_SYSTEM_PROMPT
from app.services.reporting.monitoring_service import monitoring
from app.utils.safe_response import client_safe_500_message

# router = APIRouter(prefix=PREFIX_AGENT)
logger = logging.getLogger(__name__)

# Initialize client lazily to handle missing API keys gracefully
_client: Optional[OpenAI] = None

def _get_openai_client() -> Optional[OpenAI]:
    """
    Get or create OpenAI client using centralized settings.
    """
    global _client
    if _client is None:
        if not settings.OPENAI_API_KEY:
            logger.warning("OPENAI_API_KEY not configured. Agent endpoints will return error.")
            return None
        _client = OpenAI(api_key=settings.OPENAI_API_KEY)
        logger.info("Using OpenAI API for agent")
    return _client

def _get_agent_model() -> str:
    """Get model name from settings"""
    return settings.OPENAI_MODEL if settings.OPENAI_MODEL else "gpt-4o-mini"

# ============================================================================
# OPENAI FUNCTION CALLING TOOLS
# ============================================================================
# These tools enable the agent to access monitoring data and system knowledge
# All tools execute synchronously and return JSON responses

TOOLS = [
    # ------------------------------------------------------------------
    # MONITORING TOOLS - Track usage, costs, and quotas
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "get_usage_statistics",
            "description": "Get current usage statistics including web searches, profile enrichments, AI tokens used, and costs",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_search_history",
            "description": "Get recent search history with metrics and costs",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Number of recent searches to retrieve (default 10)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_cost_breakdown",
            "description": "Get detailed cost breakdown by service (Web Discovery, Profile Enrichment, AI Processing)",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "check_rate_limits",
            "description": "Check if user can perform more searches and how many searches are remaining",
            "parameters": {"type": "object", "properties": {}, "required": []}
        }
    },

    # ------------------------------------------------------------------
    # KNOWLEDGE TOOLS - Explain system processes and metrics
    # ------------------------------------------------------------------
    {
        "type": "function",
        "function": {
            "name": "explain_process",
            "description": "Explain how a major system process works (discovery, enrichment, filtering, ranking, pdf_generation, slot_filling)",
            "parameters": {
                "type": "object",
                "properties": {
                    "process_name": {
                        "type": "string",
                        "enum": [
                            "discovery",
                            "enrichment",
                            "filtering",
                            "ranking",
                            "pdf_generation",
                            "slot_filling",
                            "static_search",
                            "dynamic_search"
                        ],
                        "description": "The process to explain"
                    }
                },
                "required": ["process_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "explain_metric",
            "description": "Explain how a specific metric is calculated and what it means",
            "parameters": {
                "type": "object",
                "properties": {
                    "metric_name": {
                        "type": "string",
                        "enum": [
                            "authenticity_score",
                            "quality_score",
                            "engagement_rate",
                            "relevance_score",
                            "niche_matching",
                            "location_matching",
                            "follower_matching",
                            "cost_per_post",
                            "estimated_reach",
                            "audience_overlap",
                            "growth_rate",
                            "content_quality",
                            "brand_safety"
                        ],
                        "description": "The metric to explain"
                    }
                },
                "required": ["metric_name"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "explain_feature",
            "description": "Explain how a system feature works (web_discovery, profile_enrichment, ai_processing, authenticity_checking)",
            "parameters": {
                "type": "object",
                "properties": {
                    "feature_name": {
                        "type": "string",
                        "enum": [
                            "web_discovery",
                            "profile_enrichment",
                            "ai_processing",
                            "authenticity_checking",
                            "time_breakdown",
                            "cost_calculation"
                        ],
                        "description": "The feature to explain"
                    }
                },
                "required": ["feature_name"]
            }
        }
    }
]

# ============================================================================
# SYSTEM PROMPT - Agent personality and capabilities
# ============================================================================
# Using centralized prompt from app.prompts
SYSTEM_PROMPT = AGENT_SYSTEM_PROMPT

class ChatRequest(BaseModel):
    messages: List[Dict[str, str]]

class ChatResponse(BaseModel):
    message: str

# ============================================================================
# TOOL EXECUTION HANDLER
# ============================================================================
# Routes tool calls to appropriate monitoring service methods
# Returns JSON-serialized results for OpenAI function calling

def execute_tool(tool_name: str, arguments: Dict) -> str:
    """Execute a tool and return results as JSON string"""
    try:
        # ------------------------------------------------------------------
        # MONITORING TOOLS
        # ------------------------------------------------------------------
        if tool_name == "get_usage_statistics":
            result = monitoring.get_usage_stats()

        elif tool_name == "get_search_history":
            limit = arguments.get("limit", 10)
            result = monitoring.get_search_history(limit)

        elif tool_name == "get_cost_breakdown":
            result = monitoring.get_cost_breakdown()

        elif tool_name == "check_rate_limits":
            result = monitoring.get_rate_limit_status()

        # ------------------------------------------------------------------
        # KNOWLEDGE TOOLS
        # ------------------------------------------------------------------
        elif tool_name == "explain_process":
            process = arguments.get("process_name")
            result = {"explanation": monitoring.explain_process(process)}

        elif tool_name == "explain_metric":
            metric = arguments.get("metric_name")
            result = {"explanation": monitoring.explain_metric(metric)}

        elif tool_name == "explain_feature":
            feature = arguments.get("feature_name")
            result = {"explanation": monitoring.explain_feature(feature)}

        else:
            result = {"error": "Unknown tool"}

        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})

async def agent_chat(request: ChatRequest):
    """
    Main agent endpoint with OpenAI function calling
    """
    try:
        client = _get_openai_client()
        if not client:
            raise HTTPException(
                status_code=503,
                detail="API key not configured. Set OPENAI_API_KEY in environment variables."
            )
        
        # Get model from settings
        model = _get_agent_model()
        
        # First API call with tools
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "system", "content": SYSTEM_PROMPT}] + request.messages,
            tools=TOOLS,
            tool_choice="auto"
        )

        assistant_message = response.choices[0].message

        # If no tool calls, return response
        if not assistant_message.tool_calls:
            return ChatResponse(message=assistant_message.content or "I'm here to help!")

        # Execute tool calls
        tool_messages = []
        for tool_call in assistant_message.tool_calls:
            function_name = tool_call.function.name
            function_args = json.loads(tool_call.function.arguments)

            # Execute the tool
            function_response = execute_tool(function_name, function_args)

            tool_messages.append({
                "tool_call_id": tool_call.id,
                "role": "tool",
                "name": function_name,
                "content": function_response
            })

        # Second API call with tool results
        final_messages = (
            [{"role": "system", "content": SYSTEM_PROMPT}] +
            request.messages +
            [assistant_message.model_dump()] +
            tool_messages
        )

        final_response = client.chat.completions.create(
            model=model,
            messages=final_messages
        )

        return ChatResponse(message=final_response.choices[0].message.content or "Done!")

    except Exception as e:
        raise HTTPException(status_code=500, detail=client_safe_500_message(e))

async def health():
    """Health check endpoint"""
    return {"status": "healthy", "service": "agent"}
