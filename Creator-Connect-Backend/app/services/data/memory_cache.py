
import time
import threading
import logging
from typing import Any, Dict, Optional, Tuple

logger = logging.getLogger(__name__)

class MemoryCache:
    """
    Simple thread-safe in-memory cache with Time-To-Live (TTL).
    Designed to replace Redis for basic caching needs.
    """
    
    def __init__(self):
        self._cache: Dict[str, Tuple[Any, float]] = {}
        self._lock = threading.RLock()
    
    def get(self, key: str) -> Optional[Any]:
        """Get value from cache if it exists and hasn't expired."""
        with self._lock:
            if key not in self._cache:
                return None
            
            value, expiry = self._cache[key]
            if time.time() > expiry:
                del self._cache[key]
                return None
            
            return value
    
    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        """Set value in cache with TTL (default 1 hour)."""
        with self._lock:
            expiry = time.time() + ttl_seconds
            self._cache[key] = (value, expiry)
            
            # Lazy cleanup check: if cache grows too large, clear expired
            if len(self._cache) > 1000:
                self._cleanup_expired()
    
    def delete(self, key: str) -> None:
        """Delete specific key."""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
    
    def clear(self) -> None:
        """Clear entire cache."""
        with self._lock:
            self._cache.clear()
            logger.info("Memory cache cleared")
            
    def _cleanup_expired(self) -> None:
        """Remove all expired entries."""
        now = time.time()
        keys_to_remove = [k for k, (_, exp) in self._cache.items() if now > exp]
        for k in keys_to_remove:
            del self._cache[k]
        if keys_to_remove:
            logger.debug(f"Cleaned up {len(keys_to_remove)} expired cache keys")

# Global singleton instance
cache = MemoryCache()
