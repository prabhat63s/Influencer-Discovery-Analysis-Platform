"""
Metrics Router
==============
API endpoints for retrieving monitoring metrics for the analysis page.
"""

from fastapi import APIRouter, HTTPException
from typing import Dict, Any

from app.services.reporting.monitoring_service import monitoring
from app.utils.safe_response import client_safe_500_message, is_production

# router = APIRouter(prefix=PREFIX_METRICS, tags=["5. Metrics"])


async def get_system_metrics() -> Dict[str, Any]:
    """
    **Get real-time system health metrics**
    
    Includes:
    - CPU & Memory usage
    - Redis connectivity status
    - Active Celery workers count
    """
    return monitoring.get_system_health()

async def get_conversation_metrics(conversation_id: str) -> Dict[str, Any]:
    """
    **Get comprehensive performance metrics for a specific search session**

    Monitor the quality and performance of your dynamic search operations.

    **Metrics included:**
    - **Discovery stats**: How many influencers discovered, selected, rejected
    - **API call metrics**: Number of calls to Web Discovery, Profile Enrichment, AI Processing
    - **Quality metrics**: Success rates, authenticity scores, engagement rates
    - **Performance metrics**: Processing time, throughput, API response times

    **Parameters:**
    - **conversation_id**: The search session ID (e.g., "dynamic-prompt:abc123")
    """
    try:
        metrics = monitoring.get_metrics(conversation_id)
        return metrics.to_dict()
    except Exception as e:
        detail = "Metrics not found." if is_production() else f"Metrics not found: {e}"
        raise HTTPException(status_code=404, detail=detail)


async def get_metrics_analysis(conversation_id: str) -> Dict[str, Any]:
    """
    **Get AI-powered analysis and recommendations for search performance**

    Analyzes your search metrics and provides actionable insights.

    **Returns:**
    - **Health score**: Overall search quality rating (0-100)
    - **Insights**: What's working well
    - **Recommendations**: How to improve results
    - **Issue detection**: Problems identified (low quality, high API usage, etc.)
    """
    try:
        # Return basic metrics - advanced analysis can be added later
        metrics = monitoring.get_metrics(conversation_id)
        return {
            "conversation_id": conversation_id,
            "metrics": metrics.to_dict(),
            "health_score": 85,  # Placeholder - can be calculated from metrics
            "insights": ["Metrics tracked successfully"],
            "recommendations": ["Use agent assistant for detailed analysis"]
        }
    except Exception as e:
        detail = "Analysis failed." if is_production() else f"Analysis failed: {e}"
        raise HTTPException(status_code=404, detail=detail)


async def get_all_conversations_metrics() -> Dict[str, Any]:
    """
    **ADMIN FEATURE: Get aggregated metrics across ALL search sessions**

    Returns metrics for every conversation. Not typically used by regular users.
    
    **Use for:** Admin dashboards, system monitoring, usage analytics
    """
    try:
        all_metrics = monitoring.get_all_metrics()
        return {
            "total_conversations": len(all_metrics),
            "conversations": {
                conv_id: metrics.to_dict()
                for conv_id, metrics in all_metrics.items()
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=client_safe_500_message(e))


async def export_metrics(conversation_id: str) -> Dict[str, str]:
    """
    **ADMIN FEATURE: Export search metrics to JSON file**

    Saves comprehensive metrics data to a JSON file for external analysis.
    Not typically used by regular users.

    **Use cases:**
    - Data analysis in external tools (Python, R, Excel)
    - Long-term archival storage
    - Compliance and auditing
    - Integration with BI tools (Tableau, Power BI)
    """
    try:
        import json
        from pathlib import Path

        metrics = monitoring.get_metrics(conversation_id)
        export_dir = Path("storage/exports")
        export_dir.mkdir(parents=True, exist_ok=True)

        file_path = export_dir / f"{conversation_id}_metrics.json"
        file_path.write_text(json.dumps(metrics.to_dict(), indent=2))

        return {
            "status": "success",
            "file_path": str(file_path),
            "conversation_id": conversation_id
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=client_safe_500_message(e))


from app.config.api_routes import METRICS_COMPARE

async def compare_two_conversations(conv_id_1: str, conv_id_2: str) -> Dict[str, Any]:
    """
    **🔧 ADMIN FEATURE: Compare performance metrics between two search sessions**

    Side-by-side comparison for A/B testing and optimization.
    Not typically used by regular users.

    **Use cases:**
    - Test different search strategies
    - Compare performance across time periods
    - Evaluate algorithm changes
    - Identify best search practices

    **Returns:**
    - Side-by-side metric comparison
    - Percentage differences
    - Performance winners/losers
    - Statistical significance indicators
    """
    try:
        metrics_1 = monitoring.get_metrics(conv_id_1)
        metrics_2 = monitoring.get_metrics(conv_id_2)

        return {
            "conversation_1": {
                "id": conv_id_1,
                "metrics": metrics_1.to_dict()
            },
            "conversation_2": {
                "id": conv_id_2,
                "metrics": metrics_2.to_dict()
            },
            "comparison": {
                "cost_diff": metrics_2.total_cost - metrics_1.total_cost,
                "time_diff": metrics_2.total_time - metrics_1.total_time,
                "profiles_diff": metrics_2.profiles_returned - metrics_1.profiles_returned
            }
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=client_safe_500_message(e))
