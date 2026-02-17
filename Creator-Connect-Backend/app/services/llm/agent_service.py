from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests
from dotenv import load_dotenv
from openai import OpenAI

from app.config.settings import settings
from app.services.llm.openai_utils import get_openai_client
from app.prompts import (
    ANALYZE_PROMPT_REQUEST_TEMPLATE,
    ANALYZE_PROMPT_SYSTEM,
    FIT_EXPLANATION_SYSTEM,
    FIT_EXPLANATION_USER_TEMPLATE,
    FOLLOWUP_QUESTIONS_SYSTEM,
    FOLLOWUP_QUESTIONS_USER_TEMPLATE,
    OPENROUTER_INSIGHTS_SYSTEM,
    OPENROUTER_INSIGHTS_USER_TEMPLATE,
    SECTION_INSIGHTS_SYSTEM,
    SECTION_INSIGHTS_USER_TEMPLATE,
    SIMILARITY_SCORE_SYSTEM,
    SIMILARITY_SCORE_USER_TEMPLATE,
)

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(_PROJECT_ROOT / ".env")

# Use settings module for consistent .env loading (Pydantic Settings handles it properly)
GEMINI_API_KEY = settings.GEMINI_API_KEY
GEMINI_MODEL = settings.GEMINI_MODEL
OPENAI_API_KEY = settings.OPENAI_API_KEY
OPENAI_MODEL = settings.OPENAI_MODEL

logger = logging.getLogger(__name__)

# Debug: Log if GEMINI_API_KEY is loaded (without exposing the key)
if GEMINI_API_KEY:
    logger.debug(f"✅ GEMINI_API_KEY loaded successfully (length: {len(GEMINI_API_KEY)} chars, model: {GEMINI_MODEL})")
else:
    logger.warning("⚠️ GEMINI_API_KEY is not set in settings")

_openai_client = None




def analyze_prompt(prompt: str) -> Dict[str, Any]:
    """
    Use Gemini API (or OpenAI fallback) to analyze the prompt and extract/validate:
    - Category (niche, industry, sector)
    - Location (geographic region, country, city)
    - Followers range (follower count range or specific numbers)

    Returns:
        dict with validation status, extracted fields, and missing fields
    """
    try:
        combined_prompt = f"{ANALYZE_PROMPT_SYSTEM}\n\n{ANALYZE_PROMPT_REQUEST_TEMPLATE.format(prompt=prompt)}"
        messages = [{"role": "user", "content": combined_prompt}]
        response = call_openai_api(
            messages=messages,
            model=None,
            temperature=0.1,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )
        
        if "choices" in response and len(response["choices"]) > 0:
            response_text = response["choices"][0]["message"]["content"]
        else:
            raise ValueError("Empty response from OpenAI")
        
        result = json.loads(response_text)

        # Determine missing fields
        missing_fields = []
        if not result.get("has_category", False):
            missing_fields.append("Category")
        if not result.get("has_location", False):
            missing_fields.append("Location")
        if not result.get("has_followers", False):
            missing_fields.append("Followers range")

        return {
            "is_valid": len(missing_fields) == 0,
            "missing_fields": missing_fields,
            "has_category": result.get("has_category", False),
            "has_location": result.get("has_location", False),
            "has_followers": result.get("has_followers", False),
            "has_fee": result.get("has_fee", False),
            "has_fee_range": result.get("has_fee_range", False),
            "extracted_category": result.get("extracted_category"),
            "extracted_location": result.get("extracted_location"),
            "extracted_followers": result.get("extracted_followers"),
            "extracted_fee": result.get("extracted_fee"),
            "extracted_fee_range": result.get("extracted_fee_range")
        }
    except json.JSONDecodeError as e:
        logger.error(f"Failed to parse response as JSON: {e}")
        # Return default values instead of raising
        return {
            "is_valid": False,
            "missing_fields": ["Category", "Location", "Followers range"],
            "has_category": False,
            "has_location": False,
            "has_followers": False,
            "has_fee": False,
            "has_fee_range": False,
            "extracted_category": None,
            "extracted_location": None,
            "extracted_followers": None,
            "extracted_fee": None,
            "extracted_fee_range": None
        }
    except Exception as e:
        logger.error(f"API error analyzing prompt: {e}")
        # Return default values instead of breaking the flow
        return {
            "is_valid": False,
            "missing_fields": ["Category", "Location", "Followers range"],
            "has_category": False,
            "has_location": False,
            "has_followers": False,
            "has_fee": False,
            "has_fee_range": False,
            "extracted_category": None,
            "extracted_location": None,
            "extracted_followers": None,
            "extracted_fee": None,
            "extracted_fee_range": None
        }


def generate_questions(prompt: str) -> List[str]:
    """Generate follow-up questions based on the prompt using Gemini API (low token task)."""
    try:
        combined_prompt = f"{FOLLOWUP_QUESTIONS_SYSTEM}\n\n{FOLLOWUP_QUESTIONS_USER_TEMPLATE.format(prompt=prompt)}"
        messages = [{"role": "user", "content": combined_prompt}]
        response = call_openai_api(
            messages=messages,
            model=None,
            temperature=0.7,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )
        
        if "choices" in response and len(response["choices"]) > 0:
            response_text = response["choices"][0]["message"]["content"]
        else:
            raise ValueError("Empty response from OpenAI")
        
        result = json.loads(response_text)
        questions = result.get("questions", [])

        # Fallback to default questions if Gemini doesn't return proper format
        if not questions or not isinstance(questions, list):
            return [
                "What is your target audience (age, region)?",
                "Which platforms are in scope (Instagram, TikTok, YouTube)?",
                "What is your monthly budget range?",
                "Do you prefer micro or macro influencers?",
                "Any industries or niches to prioritize or exclude?",
            ]

        return questions
    except Exception as e:
        logger.error(f"Failed to generate questions with Gemini: {e}")
        # Fallback to default questions
    return [
        "What is your target audience (age, region)?",
        "Which platforms are in scope (Instagram, TikTok, YouTube)?",
        "What is your monthly budget range?",
        "Do you prefer micro or macro influencers?",
        "Any industries or niches to prioritize or exclude?",
    ]


# -----------------------------------------------------------------------------
# OpenAI API: use canonical client from openai_utils (single source of truth).
# -----------------------------------------------------------------------------

def call_openai_api(
    messages: List[Dict[str, str]],
    model: Optional[str] = None,
    temperature: float = 0.2,
    max_tokens: int = 2000,
    response_format: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """
    Call OpenAI API directly (not OpenRouter) with the specified messages.
    Used for all PDF generation AI insights.
    
    Args:
        messages: List of message dicts with 'role' and 'content'
        model: Model name (defaults to OPENAI_MODEL, e.g., "gpt-4o-mini")
        temperature: Sampling temperature
        max_tokens: Maximum tokens to generate
        response_format: Optional response format (e.g., {"type": "json_object"})
    
    Returns:
        API response dictionary in standard format
    """
    client = get_openai_client()
    if not client:
        raise ValueError("OpenAI client not available; check OPENAI_API_KEY or OpenRouter config.")
    model = model or OPENAI_MODEL
    logger.debug(f"🤖 Using OpenAI API with model: {model}")
    
    kwargs = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    
    if response_format:
        kwargs["response_format"] = response_format
    
    try:
        response = client.chat.completions.create(**kwargs)
        # Return OpenAI response in standard format
        return {
            "choices": [{
                "message": {
                    "content": response.choices[0].message.content
                }
            }]
        }
    except Exception as e:
        logger.error(f"OpenAI API request failed: {e}")
        raise ValueError(f"OpenAI API call failed: {str(e)}")


def generate_openai_insights(
    detail: Dict[str, Any],
    user_prompt: Optional[str] = None,
    model: Optional[str] = None
) -> Dict[str, Any]:
    """
    Generate AI insights using OpenAI API (not OpenRouter) with ALL CSV columns.
    Used for PDF generation - ensures all insights come from OpenAI.
    
    Args:
        detail: Complete influencer detail dictionary with all columns
        user_prompt: Optional user requirements/prompt
        model: Optional model override (defaults to OPENAI_MODEL from env)
    
    Returns:
        Dictionary with comprehensive AI insights from OpenAI
    """
    # Prepare comprehensive context with ALL available data
    context_data = {
        # Basic Information
        "name": detail.get("name", "Unknown"),
        "id_name": detail.get("id_name", ""),
        "platform": detail.get("platform", "N/A"),
        "profile_link": detail.get("profile_link", ""),
        "external_url": detail.get("external_url", ""),
        "biography": detail.get("biography", ""),

        # Follower Metrics
        "followers": detail.get("followers", 0),
        "following": detail.get("following", 0),
        "posts_count": detail.get("posts_count", 0),
        "posts": detail.get("posts", 0),
        "highlights_count": detail.get("highlights_count", 0),

        # Engagement Metrics
        "engagement_rate": detail.get("engagement_rate", 0),
        "avg_engagement": detail.get("avg_engagement", 0),
        "avg_views": detail.get("avg_views", 0),
        "avg_likes": detail.get("avg_likes", 0),
        "avg_comments": detail.get("avg_comments", 0),

        # Follower Authenticity
        "suspicious_fake_followers": detail.get("suspicious_fake_followers", 0),
        "real_followers": detail.get("real_followers", 0),
        "real_percentage": detail.get("real_percentage", 0),

        # Account Type & Verification
        "is_business_account": detail.get("is_business_account", False),
        "is_professional_account": detail.get("is_professional_account", False),
        "is_verified": detail.get("is_verified", False),
        "is_joined_recently": detail.get("is_joined_recently", False),

        # Categorization
        "niche": detail.get("niche", ""),
        "business_category_name": detail.get("business_category_name", ""),
        "category_name": detail.get("category_name", ""),

        # Location & Contact
        "location": detail.get("location", ""),
        "contact": detail.get("contact", ""),
        "email_address": detail.get("email_address", ""),

        # Content & Hashtags
        "post_hashtags": detail.get("post_hashtags", ""),

        # Pricing
        "rate": detail.get("rate", 0),

        # Audience Demographics
        "age_range": detail.get("age_range", ""),
        "gender_ratio": detail.get("gender_ratio", ""),
        "professions_education": detail.get("professions_education", ""),
        "income_group": detail.get("income_group", ""),
        "geographic_distribution": detail.get("geographic_distribution", ""),
        "lifestyle_interests": detail.get("lifestyle_interests", ""),

        # 🆕 NEW: Post Analysis & Hashtag Data
        "top_hashtags": detail.get("top_hashtags", []),
        "hashtag_analysis": detail.get("hashtag_analysis", {}),
        "post_analysis": detail.get("post_analysis", {}),

        # Additional raw data
        "raw_data": detail.get("raw_data", {})
    }

    # 🆕 If we have detailed post analysis, use that instead of generic insights
    post_analysis = detail.get("post_analysis", {})
    if post_analysis.get("post_analysis_available"):
        logger.debug(f"✨ Using detailed post analysis for {detail.get('name', 'Unknown')}")
        # Replace generic insights with post analysis insights
        context_data["content_strategy"] = post_analysis.get("content_strategy_summary", "")
        context_data["key_insights"] = post_analysis.get("key_insights", [])
        context_data["recommendations"] = post_analysis.get("recommendations", [])
        context_data["brand_collaboration_readiness"] = post_analysis.get("brand_collaboration_readiness", 0)
    
    user_message = OPENROUTER_INSIGHTS_USER_TEMPLATE.format(
        context_data=json.dumps(context_data, indent=2, default=str),
        user_prompt=user_prompt if user_prompt else "General analysis for marketing collaboration",
    )
    
    messages = [
        {"role": "system", "content": OPENROUTER_INSIGHTS_SYSTEM},
        {"role": "user", "content": user_message}
    ]
    
    try:
        response = call_openai_api(
            messages=messages,
            model=model,
            temperature=0.2,
            max_tokens=3000,
            response_format={"type": "json_object"}
        )
        
        # Extract content from response
        if "choices" in response and len(response["choices"]) > 0:
            content = response["choices"][0]["message"]["content"]
            insights = json.loads(content)
            return insights
        else:
            logger.error("Unexpected OpenAI response structure: %s", response)
            raise ValueError("Invalid response from OpenAI API")
            
    except json.JSONDecodeError as e:
        logger.error("Failed to decode OpenAI insights JSON: %s", e)
        logger.error("Response content: %s", response.get("choices", [{}])[0].get("message", {}).get("content", ""))
        raise ValueError(f"Failed to decode LLM insights JSON: {str(e)}")
    except Exception as e:
        logger.exception("OpenAI insights generation failed: %s", e)
        # Re-raise to allow retry logic - NO FALLBACK
        raise


def generate_section_insights(
    detail: Dict[str, Any],
    section_name: str,
    section_data: Any,
    previous_insights: Optional[Dict[str, Any]] = None,
    model: Optional[str] = None
) -> str:
    """
    Generate crisp, clear AI insights for a specific section using OpenAI API.
    Used for PDF generation - ensures all section insights come from OpenAI.
    
    Args:
        detail: Complete influencer detail dictionary
        section_name: Name of the section (e.g., "Core Metrics", "Engagement Quality", "Audience Authenticity")
        section_data: The data/content for this section
        previous_insights: Optional previous insights for context
        model: Optional model override (defaults to OPENAI_MODEL from env)
    
    Returns:
        String with clear, crisp insights for the section from OpenAI
    """
    # Prepare key metrics for context
    key_metrics = {
        "followers": detail.get("followers", 0),
        "real_followers": detail.get("real_followers", 0),
        "real_percentage": detail.get("real_percentage", 0),
        "engagement_rate": detail.get("engagement_rate", 0),
        "avg_views": detail.get("avg_views", 0),
        "avg_likes": detail.get("avg_likes", 0),
        "avg_comments": detail.get("avg_comments", 0),
        "is_verified": detail.get("is_verified", False),
        "is_business_account": detail.get("is_business_account", False),
        "rate": detail.get("rate", 0),
    }
    
    section_data_str = (
        json.dumps(section_data, indent=2, default=str)
        if isinstance(section_data, (dict, list))
        else str(section_data)
    )
    user_message = SECTION_INSIGHTS_USER_TEMPLATE.format(
        section_name=section_name,
        section_data=section_data_str,
        key_metrics=json.dumps(key_metrics, indent=2, default=str),
        influencer_name=detail.get("name", "Unknown"),
        niche=detail.get("niche", "N/A"),
        platform=detail.get("platform", "N/A"),
    )
    
    messages = [
        {"role": "system", "content": SECTION_INSIGHTS_SYSTEM},
        {"role": "user", "content": user_message}
    ]
    
    try:
        response = call_openai_api(
            messages=messages,
            model=model,
            temperature=0.3,
            max_tokens=800,  # Increased for comprehensive 4-5 line insights
            response_format=None  # Plain text response
        )
        
        if "choices" in response and len(response["choices"]) > 0:
            insight_text = response["choices"][0]["message"]["content"].strip()
            if insight_text:
                logger.debug(f"✅ Generated LLM insights for section: {section_name[:50]}... ({len(insight_text)} chars)")
                return insight_text
            else:
                logger.warning("LLM returned empty response for section: %s", section_name)
                raise ValueError(f"Empty LLM response for {section_name}")
        else:
            logger.error("No choices in LLM response for section: %s", section_name)
            raise ValueError(f"No LLM response for {section_name}")
            
    except Exception as e:
        logger.exception("Failed to generate section insights for %s: %s", section_name, e)
        # Re-raise instead of returning empty string to force retry
        raise


def generate_influencer_fit_explanation(
    user_prompt: str,
    influencer_data: Dict[str, Any]
) -> str:
    """
    Generate a 1-2 line explanation of why/how an influencer fits the user's prompt.

    Args:
        user_prompt: The original user prompt/requirement
        influencer_data: Dictionary containing influencer data (name, niche, location, followers, etc.)

    Returns:
        A concise 1-2 sentence explanation
    """
    influencer_summary = f"""
Name: {influencer_data.get('name', 'Unknown')}
Niche: {influencer_data.get('niche', 'N/A')}
Location: {influencer_data.get('location', 'N/A')}
Followers: {influencer_data.get('followers', 0):,}
Engagement Rate: {influencer_data.get('engagement_rate', 0):.2f}%
Match Score: {influencer_data.get('match_score', 0)}
"""

    user_message = FIT_EXPLANATION_USER_TEMPLATE.format(
        user_prompt=user_prompt,
        influencer_summary=influencer_summary,
    )

    try:
        combined_prompt = f"{FIT_EXPLANATION_SYSTEM}\n\n{user_message}"
        messages = [{"role": "user", "content": combined_prompt}]
        response = call_openai_api(
            messages=messages,
            model=None,
            temperature=0.3,
            max_tokens=2000,
            response_format=None
        )
        
        if "choices" in response and len(response["choices"]) > 0:
            response_text = response["choices"][0]["message"]["content"]
        else:
            raise ValueError("Empty response from OpenAI")
        
        explanation = response_text.strip()
        # Ensure it's 1-2 sentences (limit to 2 sentences if longer)
        sentences = explanation.split('. ')
        if len(sentences) > 2:
            explanation = '. '.join(sentences[:2]) + '.'

        return explanation
    except Exception as e:
        logger.exception("Failed to generate fit explanation: %s", e)
        # Fallback explanation
        return f"This influencer matches your requirements with {influencer_data.get('followers', 0):,} followers in {influencer_data.get('niche', 'their niche')} niche, located in {influencer_data.get('location', 'their region')}."


def calculate_prompt_similarity_score(
    user_prompt: str,
    influencer_data: Dict[str, Any]
) -> float:
    """
    Calculate a similarity score (0-1) between the user prompt and influencer profile using Gemini API.

    Args:
        user_prompt: The original user prompt/requirement
        influencer_data: Dictionary containing influencer data

    Returns:
        Similarity score between 0.0 and 1.0
    """
    influencer_summary = f"""
Name: {influencer_data.get('name', 'Unknown')}
Niche: {influencer_data.get('niche', 'N/A')}
Location: {influencer_data.get('location', 'N/A')}
Followers: {influencer_data.get('followers', 0):,}
Engagement Rate: {influencer_data.get('engagement_rate', 0):.2f}%
Average Likes: {influencer_data.get('average_likes', 0):,}
Average Views: {influencer_data.get('average_views', 0):,}
Match Score: {influencer_data.get('match_score', 0)}
"""

    user_message = SIMILARITY_SCORE_USER_TEMPLATE.format(
        user_prompt=user_prompt,
        influencer_summary=influencer_summary,
    )

    try:
        # Use Gemini for low-token JSON task
        combined_prompt = f"{SIMILARITY_SCORE_SYSTEM}\n\n{user_message}"

        messages = [{"role": "user", "content": combined_prompt}]
        response = call_openai_api(
            messages=messages,
            model=None,
            temperature=0.1,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )
        
        if "choices" in response and len(response["choices"]) > 0:
            response_text = response["choices"][0]["message"]["content"]
        else:
            raise ValueError("Empty response from OpenAI")
        
        result = json.loads(response_text)
        similarity_score = float(result.get("similarity_score", 0.5))

        # Ensure score is between 0 and 1
        similarity_score = max(0.0, min(1.0, similarity_score))

        return round(similarity_score, 2)
    except json.JSONDecodeError as e:
        logger.warning("Failed to parse similarity score JSON: %s. Using fallback similarity score.", e)
        # Fallback: normalize match_score to 0-1 range
        match_score = influencer_data.get("match_score", 0)
        return round(min(match_score / 100, 1.0), 2)
    except Exception as e:
        logger.warning("Failed to calculate similarity score: %s. Using fallback similarity score.", e)
        # Fallback: normalize match_score to 0-1 range
        match_score = influencer_data.get("match_score", 0)
        return round(min(match_score / 100, 1.0), 2)