"""
AI Processing Module
====================
Optimized parallel AI processing for top N influencers only.
Processes location search, identity resolution, and post analysis in parallel.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)


async def process_ai_tasks_parallel(
    influencers: List[Dict],
    parsed_query: Optional[Dict] = None,
    skip_post_analysis: bool = True  # OPTIMIZED: Skip post analysis by default for speed
) -> List[Dict]:
    """
    Process AI tasks (location search, identity resolution, post analysis) in parallel
    for top N influencers only. This significantly speeds up the pipeline.
    
    Args:
        influencers: List of top N selected influencers (ranked)
        parsed_query: Optional parsed query for fallback values
    
    Returns:
        List of influencers with AI processing completed
    """
    if not influencers:
        return []
    
    logger.info(f"🚀 Starting parallel AI processing for {len(influencers)} top influencers...")
    start_time = time.time()
    
    # Process all influencers in parallel
    tasks = []
    for inf in influencers:
        task = _process_single_influencer_ai(inf, parsed_query, skip_post_analysis)
        tasks.append(task)
    
    # Wait for all tasks to complete in parallel
    processed = await asyncio.gather(*tasks, return_exceptions=True)
    
    # Skip exceptions and log them
    results = []
    for i, result in enumerate(processed):
        if isinstance(result, Exception):
            logger.warning(f"⚠️ AI processing failed for influencer {i}: {result}")
            # Return original influencer if processing failed
            results.append(influencers[i])
        else:
            results.append(result)
    
    elapsed = time.time() - start_time
    logger.info(f"✅ Parallel AI processing completed in {elapsed:.2f}s for {len(results)} influencers")
    
    return results


async def _process_single_influencer_ai(
    influencer: Dict,
    parsed_query: Optional[Dict] = None,
    skip_post_analysis: bool = False
) -> Dict:
    """
    Process all AI tasks for a single influencer in parallel.
    OPTIMIZED: Post analysis can be skipped for faster processing.
    """
    username = influencer.get("Id") or influencer.get("username", "unknown")
    profile_link = influencer.get("PROFILE_LINK") or influencer.get("profile_link", "")
    name = influencer.get("NAME") or influencer.get("name", username)
    
    # Create tasks for parallel execution
    location_task = _process_location_search(influencer, parsed_query)
    identity_task = _process_identity_resolution(influencer)
    
    # OPTIMIZED: Skip post analysis if requested (saves significant time)
    if skip_post_analysis:
        post_analysis_task = asyncio.create_task(asyncio.sleep(0))  # Dummy task
        post_analysis_result = None
    else:
        post_analysis_task = _process_post_analysis(influencer)
    
    # Execute critical tasks in parallel (location and identity are critical)
    location_result, identity_result = await asyncio.gather(
        location_task,
        identity_task,
        return_exceptions=True
    )
    
    # Only wait for post analysis if not skipped
    if not skip_post_analysis:
        post_analysis_result = await post_analysis_task
    
    # Update influencer with results
    if not isinstance(location_result, Exception) and location_result:
        influencer["Location"] = location_result
        influencer["location"] = location_result
    
    if not isinstance(identity_result, Exception) and identity_result:
        influencer["NICHE"] = identity_result.get("profession", influencer.get("NICHE", "Digital Creator"))
        influencer["identity_confidence"] = identity_result.get("confidence", 0.0)
        influencer["identity_source"] = identity_result.get("source", "ai_processing")
        influencer["identity_reason"] = identity_result.get("reason", "")
    
    if not isinstance(post_analysis_result, Exception) and post_analysis_result:
        influencer.update(post_analysis_result)
    
    return influencer


async def _process_location_search(
    influencer: Dict,
    parsed_query: Optional[Dict] = None
) -> Optional[str]:
    """Search for location using OpenAI if missing."""
    location_value = influencer.get("Location") or influencer.get("location")
    
    # OPTIMIZED: Skip if we already have a valid location (not N/A, Unknown, empty, or just "India")
    if location_value and location_value not in ['N/A', 'Unknown', '', 'India', 'india']:
        # Check if it's more specific than just country
        if ',' in location_value or len(location_value.split()) > 1:
            return location_value  # Already have good location, skip API call
    
    # Only search if location is missing or default
    if not location_value or location_value in ['India', 'N/A', 'Unknown', '']:
        try:
            from app.services.scrapers.brightdata_scraper import _search_location_with_openai
            
            username = influencer.get("Id") or influencer.get("username", "")
            name = influencer.get("NAME") or influencer.get("name", username)
            profile_link = influencer.get("PROFILE_LINK") or influencer.get("profile_link", "")
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            location = await loop.run_in_executor(
                None,
                _search_location_with_openai,
                name or username,
                username,
                profile_link
            )
            
            if location:
                logger.debug(f"   ✅ Location found for @{username}: {location}")
                return location
            else:
                # Fallback to parsed_query location
                return parsed_query.get('location', 'Unknown') if parsed_query else 'Unknown'
        except Exception as e:
            logger.warning(f"   ⚠️ Location search failed for @{username}: {e}")
            return parsed_query.get('location', 'Unknown') if parsed_query else 'Unknown'
    
    return location_value


async def _process_identity_resolution(influencer: Dict) -> Optional[Dict]:
    """Resolve influencer identity using OpenAI."""
    try:
        from app.services.analysis.industry_standards import resolve_influencer_identity_with_openai
        
        profile_url = influencer.get("PROFILE_LINK") or influencer.get("profile_link", "")
        username = influencer.get("Id") or influencer.get("username", "")
        full_name = influencer.get("NAME") or influencer.get("name", "")
        biography = influencer.get("biography") or influencer.get("bio", "")
        external_url = influencer.get("external_url", "")
        
        # Call the async function directly (it's already async)
        identity = await resolve_influencer_identity_with_openai(
            profile_url=profile_url,
            username=username,
            full_name=full_name,
            biography=biography,
            external_url=external_url
        )
        
        logger.debug(f"   ✅ Identity resolved for @{username}: {identity.get('profession', 'N/A')}")
        return identity
    except Exception as e:
        logger.warning(f"   ⚠️ Identity resolution failed for @{influencer.get('Id', 'unknown')}: {e}")
        return None


async def _process_post_analysis(influencer: Dict) -> Optional[Dict]:
    """Process post analysis using Gemini."""
    try:
        from app.services.analysis.post_analysis import add_post_metrics_to_result
        from app.config.settings import settings
        from google import genai
        
        # Get Gemini client
        gemini_client = None
        if settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip():
            try:
                gemini_client = genai.Client(api_key=settings.GEMINI_API_KEY.strip())
            except Exception as e:
                logger.debug(f"   ⚠️ Could not initialize Gemini client: {e}")
        
        # Run in thread pool to avoid blocking
        loop = asyncio.get_event_loop()
        updated_influencer = await loop.run_in_executor(
            None,
            add_post_metrics_to_result,
            influencer,
            gemini_client
        )
        
        username = influencer.get("Id") or influencer.get("username", "unknown")
        post_analysis = updated_influencer.get("post_analysis", {})
        if post_analysis.get("post_analysis_available") is True:
            logger.debug(f"   ✅ Post analysis completed for @{username}")
        else:
            logger.debug(f"   ℹ️ Post analysis not available for @{username}")
        
        # Return only the new fields to update
        return {
            "post_analysis": updated_influencer.get("post_analysis", {}),
            "top_hashtags": updated_influencer.get("top_hashtags", []),
            "hashtag_analysis": updated_influencer.get("hashtag_analysis", {})
        }
    except Exception as e:
        logger.warning(f"   ⚠️ Post analysis failed for @{influencer.get('Id', 'unknown')}: {e}")
        return None

