"""
Application logging: env-based level, production JSON when structlog available, PII/secret redaction.
Workflow-aligned: production uses structured logs; dev uses readable console.
"""
import logging
import os
import re
import sys

from app.config.settings import settings


def _is_production() -> bool:
    env_value = (os.getenv("ENV", "") or getattr(settings, "ENV", "") or "").strip().lower()
    return env_value == "production"


def _redact_message(msg: str) -> str:
    """Mask common secret patterns in log messages. Do not log raw secrets."""
    if not msg or not isinstance(msg, str):
        return msg
    # Mask API keys / tokens (long alphanumeric strings after known keys)
    for pattern in (
        r"(api[_-]?key|apikey|token|secret|password|auth)\s*[=:]\s*['\"]?([^\s'\"]{8,})['\"]?",
        r"(bearer)\s+([a-zA-Z0-9_\-\.]{20,})",
    ):
        msg = re.sub(pattern, r"\1=***REDACTED***", msg, flags=re.IGNORECASE)
    return msg


class RedactionFilter(logging.Filter):
    """Filter that redacts sensitive data in log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = _redact_message(getattr(record, "msg", "") or "")
        if record.args:
            record.args = tuple(
                _redact_message(str(a)) if isinstance(a, str) else a
                for a in record.args
            )
        return True


def configure_logging():
    """
    Configure app-wide logging. Production: JSON + redaction when structlog present; else standard.
    """
    is_prod = _is_production()
    log_level = logging.WARNING if is_prod else logging.INFO
    log_format = "[%(levelname)s] %(name)s - %(message)s"

    try:
        import structlog
        use_structlog = True
    except ImportError:
        use_structlog = False

    if use_structlog and is_prod:
        structlog.configure(
            processors=[
                structlog.stdlib.filter_by_level,
                structlog.stdlib.add_logger_name,
                structlog.stdlib.add_log_level,
                structlog.processors.TimeStamper(fmt="iso"),
                structlog.processors.StackInfoRenderer(),
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
            wrapper_class=structlog.stdlib.BoundLogger,
            context_class=dict,
            logger_factory=structlog.stdlib.LoggerFactory(),
            cache_logger_on_first_use=True,
        )

    logging.basicConfig(
        level=log_level,
        format=log_format,
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
    for handler in logging.root.handlers:
        handler.addFilter(RedactionFilter())

    logging.getLogger("uvicorn.access").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("selenium").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logger = logging.getLogger("app")
    logger.setLevel(log_level)
    return logger
