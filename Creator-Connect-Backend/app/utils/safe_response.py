"""
Safe response helpers for production.
Never expose stack traces or internal exception messages to clients in production.
"""
import os

from app.config.settings import settings

# Generic message returned for 500 errors when ENV=production
DEFAULT_CLIENT_500_MESSAGE = "An unexpected error occurred. Please try again or contact support."


def is_production() -> bool:
    """True when ENV is production; used to decide whether to hide internal details."""
    env_value = (os.getenv("ENV", "") or getattr(settings, "ENV", "") or "").strip().lower()
    return env_value == "production"


def client_safe_500_message(exc: Exception, fallback: str = DEFAULT_CLIENT_500_MESSAGE) -> str:
    """
    Return a client-safe message for 500 responses.
    In production returns fallback; in development returns str(exc) for debugging.
    """
    if is_production():
        return fallback
    return str(exc) if exc else fallback
