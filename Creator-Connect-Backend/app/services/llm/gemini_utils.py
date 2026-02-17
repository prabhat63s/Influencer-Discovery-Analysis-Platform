"""
Shared Gemini API utilities for production use.

Single source of truth for:
- Gemini client singleton (thread-safe, lazy init)
- Query parsing with metrics support and smart defaults

Used by: pipeline_orchestrator, pipeline_orchestrator_streaming, dynamic_search,
         industry_standards, agent_service.
"""

from __future__ import annotations

import json
import logging
import re
from typing import TYPE_CHECKING, Dict, Optional

from app.config.settings import settings
from google import genai

if TYPE_CHECKING:
    from app.services.reporting.monitoring_service import SearchMetrics

logger = logging.getLogger(__name__)

GEMINI_API_KEY = settings.GEMINI_API_KEY
GEMINI_MODEL = settings.GEMINI_MODEL

# Module-level singleton; init once per process
_gemini_client: Optional[genai.Client] = None


def get_gemini_client() -> Optional[genai.Client]:
    """
    Get or create Gemini client singleton. Safe for concurrent use.
    Returns None if API key is not set or init fails.
    """
    global _gemini_client
    if _gemini_client is None:
        if not GEMINI_API_KEY:
            logger.warning("GEMINI_API_KEY is not set - Gemini features will be unavailable")
            return None
        try:
            _gemini_client = genai.Client(api_key=GEMINI_API_KEY)
            logger.debug("Gemini client initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize Gemini client: %s", e)
            return None
    return _gemini_client


def parse_query_with_gemini(
    user_query: str,
    metrics: Optional["SearchMetrics"] = None,
) -> Dict:
    """
    Parse user query using Gemini with optional metrics tracking.

    Smart defaults: India location, 1k–900k followers, fallback search_queries.
    Used by pipeline orchestrator and streaming; dynamic_search uses its own
    validation layer on top of get_gemini_client().
    """
    from app.prompts import GEMINI_QUERY_PARSER_PROMPT_TEMPLATE

    user_query = (user_query or "").strip()
    prompt = GEMINI_QUERY_PARSER_PROMPT_TEMPLATE.format(user_query=user_query)
    full_prompt = f"You are an expert query parser. Return only valid JSON.\n\n{prompt}"

    try:
        if metrics:
            metrics.gemini_calls += 1

        client = get_gemini_client()
        if client is None:
            raise ValueError("Gemini API key not set")

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=full_prompt,
            config={"temperature": 0.0, "response_mime_type": "application/json"},
        )
        response_text = response.text.strip()

        if response_text.startswith("```"):
            response_text = response_text.split("```")[1]
            if response_text.startswith("json"):
                response_text = response_text[4:]
        response_text = response_text.strip()

        parsed = json.loads(response_text)

        if "search_queries" not in parsed or not parsed["search_queries"]:
            niche = parsed.get("niche", "influencer")
            location = parsed.get("location", "India")
            parsed["search_queries"] = [
                f"{niche} influencer {location} site:instagram.com",
                f"{niche} creator {location} site:instagram.com",
                f"{niche} blogger {location} instagram",
            ]

        if "num_results" not in parsed or parsed["num_results"] is None or parsed["num_results"] == 0:
            num_match = re.search(
                r"(?:top|find|get|show|list|give\s+me)\s*(\d+)|(\d+)\s*(?:influencers?|results?|creators?)",
                user_query.lower(),
            )
            if num_match:
                num_value = num_match.group(1) or num_match.group(2)
                parsed["num_results"] = int(num_value)
            else:
                parsed["num_results"] = 10
        else:
            parsed["num_results"] = int(parsed["num_results"])

        parsed["num_results"] = min(parsed["num_results"], 1000)
        parsed["original_query"] = user_query

        if not parsed.get("location") or parsed["location"] in ("", "any", "anywhere"):
            parsed["location"] = "India"
        if not parsed.get("min_followers"):
            parsed["min_followers"] = 1000
        if not parsed.get("max_followers"):
            parsed["max_followers"] = 900000
        elif parsed["max_followers"] > 900000:
            logger.info("User requested max_followers above 900k: %s", parsed["max_followers"])

        min_followers = parsed.get("min_followers")
        max_followers = parsed.get("max_followers")
        has_custom_range = (min_followers and min_followers != 1000) or (
            max_followers and max_followers != 900000
        )
        if has_custom_range and parsed.get("search_queries"):
            enhanced = []
            follower_hint = None
            if min_followers and max_followers:
                min_k, max_k = min_followers // 1000, max_followers // 1000
                if max_k >= 1000:
                    follower_hint = f"{min_k}k-{max_k // 1000}M followers"
                else:
                    follower_hint = f"{min_k}k-{max_k}k followers"
            elif max_followers:
                max_k = max_followers // 1000
                follower_hint = f"under {max_k // 1000}M followers" if max_k >= 1000 else f"under {max_k}k followers"
            elif min_followers:
                min_k = min_followers // 1000
                follower_hint = f"over {min_k // 1000}M followers" if min_k >= 1000 else f"over {min_k}k followers"
            if follower_hint:
                for q in parsed["search_queries"]:
                    if "site:instagram.com" in q and follower_hint not in q:
                        enhanced.append(q.replace(" site:instagram.com", f" {follower_hint} site:instagram.com"))
                    else:
                        enhanced.append(q)
                parsed["search_queries"] = enhanced

        if metrics:
            metrics.parsed_query = parsed
            metrics.estimated_tokens_used += len(prompt) // 4 + len(response_text) // 4

        logger.info(
            "Query parsed: %s results | %s | %s | %s-%s followers",
            parsed["num_results"],
            parsed.get("niche", "Any"),
            parsed["location"],
            parsed.get("min_followers", 0),
            parsed.get("max_followers", 0),
        )
        return parsed

    except Exception as e:
        logger.warning("Gemini parsing error: %s", e)
        if metrics:
            metrics.gemini_failures += 1
            metrics.add_warning(f"Gemini parsing failed: {e}")
        return {
            "num_results": 3,
            "niche": "General",
            "location": "India",
            "min_followers": 1000,
            "max_followers": 900000,
            "search_queries": [f"{user_query} instagram influencer"],
            "original_query": user_query,
        }
