from __future__ import annotations

import copy
import json
import logging
import os
from pathlib import Path
from typing import Optional

from dotenv import load_dotenv
from fastapi import APIRouter, Header, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.models.schema import ReportRequest, ReportResponse
from app.services.reporting.dynamic_pdf_generator import generate_dynamic_pdf
from app.utils.auth_utils import validate_token
from app.utils.parsing import parse_number, parse_percentage
from app.utils.safe_response import client_safe_500_message

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(_PROJECT_ROOT / ".env")

# from app.config.api_routes import PREFIX_REPORTING
# router = APIRouter(prefix=PREFIX_REPORTING, tags=["4. Reports"])
logger = logging.getLogger(__name__)


class DynamicReportRequest(ReportRequest):
    """Extended report request for dynamic (prompt-only) searches."""
    conversation_id: Optional[str] = None  # e.g., "prompt_b749dce7..."


def _extract_token(authorization: str | None) -> str | None:
    """Extract token from Authorization header."""
    if not authorization:
        return None
    if authorization.lower().startswith("bearer "):
        return authorization.split(" ", 1)[1].strip()
    return authorization


def _load_results_json(file_hash: str) -> Optional[dict]:
    """Load results from JSON file."""
    results_path = _PROJECT_ROOT / "storage" / "results" / f"{file_hash}.json"
    if not results_path.exists():
        return None
    try:
        return json.loads(results_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning("Failed to read results JSON for %s: %s", file_hash, e)
        return None


def _transform_dynamic_data(data: dict) -> dict:
    """
    Transform raw scraped data to include calculated fields for metrics.
    Converts real_followers_percentage and suspicious_followers_percentage
    to real_percentage, real_followers, and suspicious_fake_followers.
    
    IMPORTANT: This function preserves ALL original fields and adds calculated ones.
    """
    # Helpers removed (parse_number, parse_percentage) - imported from utils.parsing

    # Make a DEEP copy to avoid mutating the original - preserves ALL fields
    # Use copy.deepcopy() to properly copy nested structures (lists, dicts, etc.)
    transformed = copy.deepcopy(data)

    # Get follower count
    followers = parse_number(data.get("followers", 0))

    # Parse percentages
    real_followers_pct = parse_percentage(data.get("real_followers_percentage", 0))
    suspicious_followers_pct = parse_percentage(data.get("suspicious_followers_percentage", 0))
    
    # Fallback: If suspicious is missing but real exists, calculate it
    if suspicious_followers_pct <= 0 and real_followers_pct > 0:
        suspicious_followers_pct = 100.0 - real_followers_pct

    # Calculate actual counts
    real_followers = int(followers * (real_followers_pct / 100.0)) if followers > 0 else 0
    suspicious_fake_followers = int(followers * (suspicious_followers_pct / 100.0)) if followers > 0 else 0

    # Add calculated fields
    transformed["real_percentage"] = real_followers_pct
    transformed["real_followers"] = real_followers
    transformed["suspicious_fake_followers"] = suspicious_fake_followers

    # Ensure authenticity_score is calculated if missing
    if not transformed.get("authenticity_score"):
        fake_follower_ratio = suspicious_followers_pct
        transformed["authenticity_score"] = (real_followers_pct * 0.7) - (fake_follower_ratio * 0.3)

    # ========================================================================
    # CRITICAL: Ensure commonly needed fields are passed through and normalized
    # ========================================================================
    
    # Average likes/comments - ensure both naming conventions work
    if data.get("average_likes"):
        transformed["avg_likes"] = parse_number(data.get("average_likes"))
        transformed["average_likes"] = transformed["avg_likes"]
    elif data.get("avg_likes"):
        transformed["avg_likes"] = parse_number(data.get("avg_likes"))
        transformed["average_likes"] = transformed["avg_likes"]
        
    if data.get("average_comments"):
        transformed["avg_comments"] = parse_number(data.get("average_comments"))
        transformed["average_comments"] = transformed["avg_comments"]
    elif data.get("avg_comments"):
        transformed["avg_comments"] = parse_number(data.get("avg_comments"))
        transformed["average_comments"] = transformed["avg_comments"]
    
    # Posts - ensure posts_count is always set
    # CRITICAL: If posts_count already exists, use it (it's the actual total)
    # Only use len(posts) if posts_count doesn't exist and posts is a list
    # Note: Nested structures like posts list are already deep copied by copy.deepcopy()
    # Only need to reassign if transforming or if missing from original data
    posts_raw = data.get("posts")
    # Use "in" check to distinguish between missing fields and zero/None values
    if "posts_count" in data:
        # posts_count exists in data - use it (even if it's 0 or None, it's the authoritative value)
        posts_count_val = data.get("posts_count")
        if posts_count_val is not None and posts_count_val != "N/A":
            transformed["posts_count"] = parse_number(posts_count_val)
        else:
            # posts_count exists but is None or "N/A" - set to 0 as default
            transformed["posts_count"] = 0
        # posts list is already deep copied, but ensure it's present if it exists in source
        if isinstance(posts_raw, list) and "posts" not in transformed:
            transformed["posts"] = copy.deepcopy(posts_raw)
    elif isinstance(posts_raw, list):
        # posts is a list but no posts_count field - this is sample posts
        # Only use length as fallback if posts_count truly doesn't exist
        # Ensure posts is deep copied (already deep copied by copy.deepcopy() if it existed in data)
        # Only need to add it if it wasn't in the original data, otherwise it's already a deep copy
        if "posts" not in transformed:
            transformed["posts"] = copy.deepcopy(posts_raw)
        transformed["posts_count"] = len(transformed.get("posts", []))  # Use deep copied list
    elif posts_raw and not isinstance(posts_raw, list):
        # posts is a number, use it as posts_count
        # CRITICAL: Don't set transformed["posts"] to a number - downstream code expects a list
        # Remove posts field if it exists (from deep copy) since it's not a list
        transformed["posts_count"] = parse_number(posts_raw)
        if "posts" in transformed:
            # Remove the non-list posts field to maintain type consistency
            # Downstream code in dynamic_pdf_generator.py checks isinstance(posts, list)
            del transformed["posts"]
    else:
        # Neither posts_count nor posts field exists in data - set default
        # This ensures posts_count is always set as promised by the function contract
        transformed["posts_count"] = 0
    
    # Post analysis - already deep copied by copy.deepcopy(), only reassign if transforming
    # Note: copy.deepcopy() already handled this nested dict, so no need to reassign
    
    # Biography - already deep copied by copy.deepcopy()
    # External URL - already deep copied by copy.deepcopy()
    # Both are already in transformed if they existed in the original data

    return transformed


def _find_file_hash_from_dynamic_influencer(
    influencer_id: str,
    conversation_id: Optional[str] = None
) -> Optional[tuple[str, str]]:
    """
    Find file_hash and analysis influencer_id for a dynamic (prompt-only) influencer.

    Args:
        influencer_id: The dynamic influencer ID
        conversation_id: Optional conversation ID (if None, will try to resolve latest)

    Returns:
        Tuple of (file_hash, analysis_influencer_id) or None if not found
    """
    logger.debug("🔍 Searching for file_hash from dynamic influencer_id: %s", influencer_id)

    # Import here to avoid circular imports
    from app.controllers.results_controller import (
        _resolve_prompt_conversation_id,
        _load_dynamic_results_for_conversation,
        _analyze_dynamic_influencer
    )

    # Resolve conversation_id if needed
    try:
        resolved_conversation_id = _resolve_prompt_conversation_id(conversation_id)
    except HTTPException:
        logger.warning("Could not resolve conversation_id for dynamic influencer")
        return None

    logger.debug("  Resolved conversation_id: %s", resolved_conversation_id)

    # Load dynamic results
    dynamic_results = _load_dynamic_results_for_conversation(resolved_conversation_id)
    if not dynamic_results:
        logger.warning("No dynamic results found for conversation %s", resolved_conversation_id)
        return None

    # Find the influencer in dynamic results
    found_influencer = None
    for result in dynamic_results:
        result_id = result.get("id")
        if not result_id:
            # Compute ID if not present
            import hashlib
            profile_link = result.get("profile_link") or result.get("PROFILE_LINK")
            if profile_link:
                result_id = hashlib.md5(str(profile_link).encode()).hexdigest()[:12]
            else:
                name = result.get("name") or result.get("NAME", "Unknown")
                niche = result.get("niche") or result.get("NICHE", "Unknown")
                location = result.get("location") or result.get("Location", "Unknown")
                unique_string = f"{name}_{location}_{niche}"
                result_id = hashlib.md5(unique_string.encode()).hexdigest()[:12]

        if result_id == influencer_id:
            found_influencer = result
            logger.debug("✓ Found influencer in dynamic results: %s", result.get("name"))
            break

    if not found_influencer:
        logger.warning("Influencer %s not found in dynamic results", influencer_id)
        return None

    # Check if there's a cached analysis_file_hash
    analysis_file_hash = found_influencer.get("analysis_file_hash")

    if analysis_file_hash:
        # Load the results JSON and find the analysis influencer ID
        results = _load_results_json(analysis_file_hash)
        if results and results.get("influencers"):
            # Usually will be the first (and only) influencer
            analysis_influencer = results["influencers"][0]
            analysis_influencer_id = analysis_influencer.get("id")
            logger.debug("✓ Found cached analysis: file_hash=%s, analysis_id=%s",
                       analysis_file_hash, analysis_influencer_id)
            return (analysis_file_hash, analysis_influencer_id)

    # No cached analysis - trigger on-demand analysis
    logger.debug("No cached analysis found, triggering on-demand analysis...")
    analysis_result = _analyze_dynamic_influencer(
        influencer_id,
        resolved_conversation_id,
        found_influencer
    )

    if not analysis_result:
        logger.warning("❌ Strategy 4: Analysis failed for dynamic influencer_id=%s in conversation_id=%s. Record: %s", 
                     influencer_id, resolved_conversation_id, found_influencer.get('name'))
        return None

    # Extract file_hash from analysis metadata
    # The analysis saves results to storage/results/<file_hash>.json
    # We need to find that file_hash
    import hashlib
    file_hash = hashlib.md5(f"dynamic_{resolved_conversation_id}_{influencer_id}".encode()).hexdigest()[:12]

    # Load the results JSON and find the analysis influencer ID
    results = _load_results_json(file_hash)
    if results and results.get("influencers"):
        analysis_influencer = results["influencers"][0]
        analysis_influencer_id = analysis_influencer.get("id")
        logger.debug("✓ Analysis completed: file_hash=%s, analysis_id=%s",
                   file_hash, analysis_influencer_id)
        return (file_hash, analysis_influencer_id)

    logger.warning("Analysis completed but results not found for %s", influencer_id)
    return None


def generate_dynamic_report(
    payload: DynamicReportRequest,
    authorization: str | None = Header(default=None)
):
    """
    **Step 7: Generate professional PDF report for an influencer**

    After getting analysis results, use this endpoint to generate a downloadable PDF report.
    Works for both static CSV and dynamic search results.

    **Requires Authentication:** Include Bearer token in Authorization header

    **Request Body:**
    ```json
    {
      "influencer_id": "abc123",
      "conversation_id": "prompt_b749dce7...",  // Optional, auto-resolves
      "file_hash": "optional_hash"  // Optional
    }
    ```

    **What the PDF includes:**
    - Influencer profile summary
    - Detailed metrics and charts
    - Engagement rate analysis
    - Follower demographics
    - Authenticity assessment
    - Performance insights
    - Contact information

    **Returns:**
    ```json
    {
      "report_name": "report_abc123.pdf",
      "download_url": "/api/report/download/report_abc123.pdf"
    }
    ```

    **Next step:** Use the download_url to retrieve your PDF with GET request.
    """
    if not validate_token(_extract_token(authorization)):
        raise HTTPException(status_code=401, detail="Unauthorized")

    influencer_id = payload.influencer_id
    conversation_id = payload.conversation_id or "default"
    file_hash = payload.file_hash

    logger.debug("=" * 60)
    logger.debug("📄 POST /api/report/generate/dynamic called")
    logger.debug(f"   influencer_id: {influencer_id}")
    logger.debug(f"   conversation_id: {conversation_id}")
    logger.debug(f"   file_hash: {file_hash}")
    logger.debug("=" * 60)

    found_influencer = None
    influencer_data = None
    data_source = None  # Track where data came from for debugging

    # Strategy 1: If file_hash is provided and valid, try loading from analyzed results
    if file_hash and file_hash.strip() and file_hash.lower() != "string":
        logger.debug("file_hash provided: %s, checking analyzed results...", file_hash)
        results = _load_results_json(file_hash)
        if results and results.get("influencers"):
            # Find the influencer in analyzed results
            influencers = results.get("influencers", [])
            influencer = next((inf for inf in influencers if inf.get("id") == influencer_id), None)
            if influencer:
                influencer_data = influencer.copy()
                data_source = f"Strategy 1: Analyzed results (file_hash={file_hash})"
                logger.debug("✓ Found influencer in analyzed results for file_hash %s", file_hash)
                logger.debug("   Name: %s", influencer_data.get("name") or influencer_data.get("NAME"))

    # Strategy 2: Check in-memory cache (fresh dynamic search results)
    if not influencer_data:
        logger.debug("Checking in-memory dynamic search results...")
        try:
            from app.services.core import prompt_service

            all_results = prompt_service.get_dynamic_results_store()

            for conv_id, results in all_results.items():
                if conv_id == conversation_id and isinstance(results, list):
                    for result in results:
                        result_id = result.get("id") or result.get("influencer_id")
                        if result_id == influencer_id:
                            found_influencer = result
                            # Transform the data to include calculated fields
                            influencer_data = _transform_dynamic_data(found_influencer.copy())
                            data_source = f"Strategy 2: In-memory cache (conv_id={conv_id})"
                            logger.debug("✓ Found influencer in in-memory cache")
                            logger.debug("   Name: %s", influencer_data.get("name") or influencer_data.get("NAME"))
                            logger.debug("   Matched by ID: %s", result_id)
                            break
                if found_influencer:
                    break
        except Exception as e:
            logger.debug("Could not check in-memory cache: %s", e)

    # Strategy 3: Check disk storage (persisted dynamic results)
    if not influencer_data:
        logger.debug("Checking disk storage for dynamic results...")
        storage_path = _PROJECT_ROOT / "storage" / "dynamic_results" / f"{conversation_id}.json"
        if storage_path.exists():
            try:
                import json
                with open(storage_path, 'r') as f:
                    stored_results = json.load(f)
                if isinstance(stored_results, list):
                    for result in stored_results:
                        result_id = result.get("id") or result.get("influencer_id")
                        if result_id == influencer_id:
                            found_influencer = result
                            # Transform the data to include calculated fields
                            influencer_data = _transform_dynamic_data(found_influencer.copy())
                            data_source = f"Strategy 3: Disk storage ({storage_path.name})"
                            logger.debug("✓ Found influencer in disk storage")
                            logger.debug("   Name: %s", influencer_data.get("name") or influencer_data.get("NAME"))
                            logger.debug("   Matched by ID: %s", result_id)
                            break
            except Exception as e:
                logger.warning("Failed to load from disk storage: %s", e)

    # Strategy 4: Try to find from analyzed results using file_hash resolution
    if not influencer_data:
        logger.debug("Attempting to resolve from analyzed results...")
        found = _find_file_hash_from_dynamic_influencer(influencer_id, conversation_id)
        if found:
            resolved_file_hash, analysis_influencer_id = found
            results = _load_results_json(resolved_file_hash)
            if results and results.get("influencers"):
                influencer = next((inf for inf in results["influencers"] if inf.get("id") == analysis_influencer_id), None)
                if influencer:
                    influencer_data = influencer.copy()
                    logger.debug("✓ Found influencer in analyzed results via resolution")

    # If still not found, raise error
    if not influencer_data:
        raise HTTPException(
            status_code=404,
            detail={
                "error": f"Influencer {influencer_id} not found in dynamic search results",
                "message": "Please ensure the influencer exists in your dynamic search results.",
                "conversation_id": conversation_id,
                "suggestions": [
                    "Verify the influencer_id is correct",
                    "Check that the conversation_id matches your search session",
                    "Ensure the dynamic search was completed successfully"
                ]
            }
        )

    try:
        # Resolve conversation_id for temp_store lifecycle tracking
        # This enables automatic cleanup when sessions expire
        resolved_conversation_id = None
        if conversation_id and conversation_id != "default":
            resolved_conversation_id = conversation_id
        else:
            # Try to resolve the latest prompt conversation
            try:
                from app.controllers.results_controller import _resolve_prompt_conversation_id
                resolved_conversation_id = _resolve_prompt_conversation_id(conversation_id)
            except Exception as e:
                logger.debug(f"Could not resolve conversation_id: {e}")

        if not influencer_data.get("post_analysis") or \
           not influencer_data.get("post_analysis", {}).get("post_analysis_available"):
            logger.debug("⚡ Post analysis missing for PDF, running on-demand analysis...")
            try:
                from app.services.analysis.post_analysis import add_post_metrics_to_result
                
                # Try to get gemini client, but continue without it if not available
                gemini_client = None
                try:
                    from app.services.gemini_client import get_gemini_client
                    gemini_client = get_gemini_client()
                except (ImportError, ModuleNotFoundError, Exception) as gemini_err:
                    logger.debug(f"Gemini client not available, continuing without it: {gemini_err}")
                
                influencer_data = add_post_metrics_to_result(influencer_data, gemini_client)
                logger.debug("✅ On-demand post analysis completed successfully")
            except Exception as e:
                logger.debug(f"⚠️ Post analysis skipped: {e}")
                # Continue without post analysis rather than failing completely

        # Log critical data being passed to PDF generator
        logger.debug("=" * 60)
        logger.debug("GENERATING PDF WITH DATA:")
        logger.debug(f"   Data Source: {data_source}")
        logger.debug(f"   Influencer ID: {influencer_id}")
        logger.debug(f"   Name: {influencer_data.get('name') or influencer_data.get('NAME')}")
        logger.debug(f"   Followers: {influencer_data.get('followers')}")
        logger.debug(f"   Engagement Rate: {influencer_data.get('engagement_rate')}")
        logger.debug(f"   Location: {influencer_data.get('Location') or influencer_data.get('location')}")
        logger.debug(f"   Niche: {influencer_data.get('NICHE') or influencer_data.get('niche')}")
        logger.debug(f"   Post Analysis Available: {bool(influencer_data.get('post_analysis'))}")
        logger.debug("=" * 60)

        # Generate PDF using the dynamic PDF generator
        logger.debug("→ Generating dynamic PDF for influencer_id=%s, conversation_id=%s",
                   influencer_id, resolved_conversation_id)
        result = generate_dynamic_pdf(
            influencer_id=influencer_id,
            influencer_data=influencer_data,
            conversation_id=resolved_conversation_id,
            max_retries=1,
            retry_delay=1.0
        )
        
        # Check if PDF generation failed due to insufficient data
        if "error" in result:
            error_message = result.get("message", result.get("error", "Unknown error"))
            logger.error("PDF generation failed: %s", error_message)
            raise HTTPException(
                status_code=400,
                detail=f"Failed to generate report: {error_message}"
            )
        
        report_name = result.get("name")
        if not report_name:
            logger.error("PDF generation returned no report name")
            raise HTTPException(
                status_code=500,
                detail="PDF generation succeeded but no report name was returned"
            )

        logger.debug("✓ Dynamic PDF generated successfully: %s", report_name)
        logger.debug("=" * 60)

        return ReportResponse(
            report_name=report_name,
            download_url=f"/api/report/download/{report_name}"
        )
    except HTTPException:
        # Re-raise HTTPException as-is (e.g., 400 for insufficient data)
        raise
    except Exception as e:
        logger.exception("Error generating dynamic report for %s", influencer_id)
        raise HTTPException(
            status_code=500,
            detail=client_safe_500_message(e),
        )


def download_report(
    report_name: str,
    authorization: str | None = Header(default=None)
):
    """
    **Step 8: Download the generated PDF report**

    After generating a report with `/api/report/generate/dynamic`, use this endpoint to download the PDF file.

    **Requires Authentication:** Include Bearer token in Authorization header

    **Parameters:**
    - **report_name**: The filename returned from generate endpoint (e.g., "report_abc123.pdf")

    **Example:**
    ```
    GET /api/report/download/report_abc123.pdf
    Authorization: Bearer your_token_here
    ```

    **Returns:**
    - PDF file with proper Content-Type and Content-Disposition headers
    - Ready to be saved or displayed in browser

    **Error:** 404 if report doesn't exist (generate it first)
    """
    if not validate_token(_extract_token(authorization)):
        raise HTTPException(status_code=401, detail="Unauthorized")

    report_path = _PROJECT_ROOT / "storage" / "reports" / report_name

    if not report_path.exists():
        logger.error(f"❌ PDF not found: {report_path}")
        logger.error(f"   Report name: {report_name}")
        logger.error(f"   Directory contents: {list(report_path.parent.glob('*.pdf'))[:5] if report_path.parent.exists() else 'Dir does not exist'}")
        raise HTTPException(
            status_code=404,
            detail=f"Report {report_name} not found. Please generate the report first by calling POST /api/report/generate/dynamic"
        )

    return FileResponse(
        path=report_path,
        media_type="application/pdf",
        filename=report_name
    )


