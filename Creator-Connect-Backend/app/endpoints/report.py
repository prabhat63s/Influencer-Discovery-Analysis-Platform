from fastapi import APIRouter
from app.config.api_routes import (
    PREFIX_REPORTING,
    REPORT_GENERATE_DYNAMIC,
    REPORT_DOWNLOAD
)
from app.controllers import report_controller as report

router = APIRouter(prefix=PREFIX_REPORTING, tags=["4. Reports"])

router.add_api_route(
    path=REPORT_GENERATE_DYNAMIC,
    endpoint=report.generate_dynamic_report,
    methods=["POST"],
    response_model=report.ReportResponse,
    summary="Step 7: Generate PDF report for influencer"
)

router.add_api_route(
    path=REPORT_DOWNLOAD,
    endpoint=report.download_report,
    methods=["GET"],
    summary="Step 8: Download generated PDF report"
)
