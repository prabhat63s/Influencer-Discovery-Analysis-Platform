"""
Internal Comparison Router
==========================
Compares top 3/5 search results against each other (not against external industry peers).
"""

import logging
import re
from typing import Dict, List, Any
from fastapi import APIRouter, HTTPException, Body
from pydantic import BaseModel

from app.services.llm.agent_service import call_openai_api
from app.utils.safe_response import client_safe_500_message

logger = logging.getLogger(__name__)

# router = APIRouter(prefix=PREFIX_SEARCH)


class InternalComparisonRequest(BaseModel):
    influencers: List[Dict[str, Any]]


async def generate_internal_comparison_insights(
    request: InternalComparisonRequest = Body(...)
) -> Dict[str, Any]:
    """
    Generate professional AI insights comparing the top 3/5 search results against each other.
    This is different from industry standards - it compares the results from the search query itself.
    """
    try:
        influencers = request.influencers
        
        if len(influencers) < 2:
            return {
                "insights": [
                    "Insufficient influencers for comparison. Need at least 2 influencers to compare."
                ],
                "summary": "Comparison requires at least 2 influencers."
            }
        
        # Build detailed prompt for Gemini
        influencers_data = []
        for idx, inf in enumerate(influencers, 1):
            name = inf.get("NAME") or inf.get("name") or inf.get("Id") or "Unknown"
            username = inf.get("Id") or inf.get("username") or "unknown"
            followers = inf.get("followers") or "N/A"
            engagement_rate = inf.get("engagement_rate") or inf.get("engagement") or "N/A"
            avg_likes = inf.get("average_likes") or inf.get("avg_likes") or "N/A"
            avg_comments = inf.get("average_comments") or inf.get("avg_comments") or "N/A"
            niche = inf.get("NICHE") or inf.get("niche") or "N/A"
            location = inf.get("Location") or inf.get("location") or "N/A"
            
            influencers_data.append({
                "rank": idx,
                "name": name,
                "username": username,
                "followers": followers,
                "engagement_rate": engagement_rate,
                "average_likes": avg_likes,
                "average_comments": avg_comments,
                "niche": niche,
                "location": location
            })
        
        prompt = f"""You are an expert influencer marketing analyst. Analyze and compare these {len(influencers)} influencers that came from the same search query.

INFLUENCERS TO COMPARE:
"""
        for inf_data in influencers_data:
            prompt += f"""
Rank {inf_data['rank']}: {inf_data['name']} (@{inf_data['username']})
  - Followers: {inf_data['followers']}
  - Engagement Rate: {inf_data['engagement_rate']}
  - Average Likes: {inf_data['average_likes']}
  - Average Comments: {inf_data['average_comments']}
  - Niche: {inf_data['niche']}
  - Location: {inf_data['location']}
"""
        
        prompt += f"""

TASK: Generate professional, actionable insights comparing these influencers DIRECTLY against each other.

Focus on:
1. Relative strengths and weaknesses between them
2. Which influencer performs best in which metric
3. Competitive positioning within this group
4. Strategic recommendations for brand partnerships
5. Unique value propositions of each influencer
6. Direct comparisons (e.g., "Influencer A has X% higher engagement than Influencer B")

Return a JSON object with:
- "insights": Array of 4-6 professional, qualitative insights (each 1-2 sentences)
- "summary": A 2-3 sentence overall summary comparing the group

IMPORTANT:
- Compare them ONLY against each other, not against industry standards
- Be specific about relative performance differences
- Focus on actionable insights for brand partnerships
- Use professional, business-focused language

Return ONLY valid JSON, no markdown formatting."""

        logger.info(f"🤖 Generating OpenAI insights for internal comparison: {len(influencers)} influencers")
        
        messages = [{"role": "user", "content": prompt}]
        response = call_openai_api(
            messages=messages,
            model=None,
            temperature=0.3,
            max_tokens=2000,
            response_format={"type": "json_object"}
        )
        
        if "choices" in response and len(response["choices"]) > 0:
            response_text = response["choices"][0]["message"]["content"]
        else:
            raise ValueError("Empty response from OpenAI")
        
        # Attempt to parse JSON, handle cases where OpenAI might wrap JSON in markdown
        import json
        try:
            result = json.loads(response_text)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown
            match = re.search(r"```json\n(.*?)\n```", response_text, re.DOTALL)
            if match:
                result = json.loads(match.group(1))
            else:
                # Try to find JSON object in the text
                match = re.search(r"\{.*\}", response_text, re.DOTALL)
                if match:
                    result = json.loads(match.group(0))
                else:
                    raise ValueError("OpenAI response is not valid JSON")
        
        raw_insights = result.get("insights", [])
        raw_summary = result.get("summary", "")
        
        # Normalize insights to ensure they're always strings
        insights = []
        for item in raw_insights:
            if isinstance(item, str):
                insights.append(item)
            elif isinstance(item, dict):
                # Handle object format like {"insight": "text"} or {"text": "..."}
                if "insight" in item:
                    insights.append(str(item["insight"]))
                elif "text" in item:
                    insights.append(str(item["text"]))
                else:
                    # Try to get first string value
                    for key, value in item.items():
                        if isinstance(value, str):
                            insights.append(value)
                            break
            else:
                insights.append(str(item))
        
        # Normalize summary to string
        summary = str(raw_summary) if raw_summary else ""
        
        if not insights or len(insights) < 3:
            logger.warning("OpenAI returned insufficient insights, using fallback")
            insights = [
                f"Comparative analysis of {len(influencers)} influencers reveals distinct positioning within the search results.",
                "Performance metrics show varying strengths across engagement, reach, and content quality.",
                "Strategic brand partnership opportunities differ based on target audience and campaign objectives."
            ]
        
        logger.info(f"✅ Generated {len(insights)} internal comparison insights")
        
        return {
            "insights": insights[:6],  # Max 6 insights
            "summary": summary
        }
        
    except Exception as e:
        logger.exception("Failed to generate internal comparison insights: %s", e)
        raise HTTPException(
            status_code=500,
            detail=client_safe_500_message(e),
        )

