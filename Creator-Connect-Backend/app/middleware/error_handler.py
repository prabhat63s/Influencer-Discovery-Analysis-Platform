"""
Global error handling middleware.
Catches custom and system exceptions; never exposes internal details in production.
"""
import logging
import os

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.config.settings import settings
from app.models.exceptions import CreatosConnectError

logger = logging.getLogger(__name__)
_IS_PRODUCTION = (os.getenv("ENV", "") or getattr(settings, "ENV", "") or "").strip().lower() == "production"


async def global_error_handler(request: Request, call_next):
    """
    Central error handler. Custom errors return safe client messages;
    system errors never expose stack or message in production.
    """
    try:
        response = await call_next(request)
        return response
    except CreatosConnectError as e:
        # Business errors: code + message only (details may contain internal info)
        logger.warning("Business error: code=%s message=%s", e.code, e.message, extra={"details": e.details})
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "error": {
                    "code": e.code,
                    "message": e.message,
                    "details": e.details if not _IS_PRODUCTION else None,
                }
            },
        )
    except Exception as e:
        # System errors: log full context; response must not leak internals in production
        logger.exception("Unhandled error: %s", type(e).__name__)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "error": {
                    "code": "INTERNAL_SERVER_ERROR",
                    "message": "An unexpected error occurred. Please contact support.",
                    "details": None if _IS_PRODUCTION else (str(e) if logger.isEnabledFor(logging.DEBUG) else None),
                }
            },
        )
