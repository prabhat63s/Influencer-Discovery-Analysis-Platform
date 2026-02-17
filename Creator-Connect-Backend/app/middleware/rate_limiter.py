"""
Rate limiter middleware.
Limits requests per client (by IP or X-Forwarded-For) to protect API from abuse.
Configurable via settings (RATE_LIMIT_REQUESTS, RATE_LIMIT_WINDOW_SEC).
For multi-worker production, use Redis-backed rate limiting (e.g. slowapi + Redis).
"""
import logging
import time
from collections import defaultdict
from typing import Dict, List, Tuple

from fastapi import Request, status
from fastapi.responses import JSONResponse

from app.config.settings import settings

logger = logging.getLogger(__name__)

RATE_LIMIT_REQUESTS = getattr(settings, "RATE_LIMIT_REQUESTS", 60)
RATE_LIMIT_WINDOW_SEC = getattr(settings, "RATE_LIMIT_WINDOW_SEC", 60)


def _get_client_ip(request: Request) -> str:
    """Prefer X-Forwarded-For when behind proxy; else client host."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class InMemoryRateLimiter:
    """
    Sliding-window style in-memory limiter. Thread-safe for single process.
    Not shared across workers; for multi-worker use Redis.
    """

    def __init__(
        self,
        requests_per_window: int = RATE_LIMIT_REQUESTS,
        window_sec: float = RATE_LIMIT_WINDOW_SEC,
    ):
        self.requests_per_window = requests_per_window
        self.window_sec = window_sec
        self._timestamps: Dict[str, List[float]] = defaultdict(list)

    def _prune(self, key: str, now: float) -> None:
        cutoff = now - self.window_sec
        self._timestamps[key] = [t for t in self._timestamps[key] if t > cutoff]

    def is_allowed(self, key: str) -> Tuple[bool, int]:
        """
        Returns (allowed, retry_after_sec). Retry_after_sec is 0 if allowed.
        """
        now = time.time()
        self._prune(key, now)
        timestamps = self._timestamps[key]
        if len(timestamps) >= self.requests_per_window:
            oldest = min(timestamps)
            retry_after = max(0, int(self.window_sec - (now - oldest)) + 1)
            return False, retry_after
        timestamps.append(now)
        return True, 0


# Module-level instance (single process)
_limiter = InMemoryRateLimiter(
    requests_per_window=RATE_LIMIT_REQUESTS,
    window_sec=RATE_LIMIT_WINDOW_SEC,
)


async def rate_limiter_middleware(request: Request, call_next):
    """Reject request if client exceeds rate limit; return 429 with Retry-After."""
    client_ip = _get_client_ip(request)
    allowed, retry_after = _limiter.is_allowed(client_ip)
    if not allowed:
        logger.warning("Rate limit exceeded for client %s", client_ip)
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "error": {
                    "code": "RATE_LIMIT_EXCEEDED",
                    "message": "Too many requests. Please try again later.",
                }
            },
            headers={"Retry-After": str(retry_after)},
        )
    response = await call_next(request)
    if retry_after and response.status_code < 400:
        response.headers["X-RateLimit-Retry-After"] = str(retry_after)
    return response
