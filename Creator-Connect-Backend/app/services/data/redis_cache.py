"""
Redis Caching Service
=====================
Wrapper around redis-py (async) for caching hot data.
Includes robust error handling (fails safe if Redis is down) and a decorator for easy usage.
"""
import json
import logging
import pickle
from functools import wraps
from typing import Any, Optional, Union, Callable
import hashlib

import redis.asyncio as redis
from app.config.settings import settings

logger = logging.getLogger(__name__)

class RedisService:
    _instance = None
    _pool = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RedisService, cls).__new__(cls)
            cls._instance.redis_url = settings.REDIS_URL
            cls._instance._client = None
        return cls._instance

    async def get_client(self) -> redis.Redis:
        """Get or create Redis client with connection pooling."""
        if self._client is None:
            try:
                # Use from_url which handles connection pool automatically
                self._client = redis.from_url(
                    self.redis_url, 
                    encoding="utf-8", 
                    decode_responses=False, # We store bytes (pickle) or strings
                    socket_connect_timeout=5,
                    socket_timeout=5
                )
                await self._client.ping()
                logger.info("✅ Redis connection established")
            except Exception as e:
                logger.warning(f"⚠️ Redis connection failed: {e}. Caching will be disabled.")
                self._client = None
        return self._client

    async def get(self, key: str) -> Optional[Any]:
        """Get value from Redis. Returns None if key missing or Redis down."""
        client = await self.get_client()
        if not client:
            return None
        
        try:
            val = await client.get(key)
            if val:
                try:
                    return pickle.loads(val)
                except Exception:
                    # Fallback for plain strings/bytes that aren't pickled
                    return val
            return None
        except Exception as e:
            logger.warning(f"Redis GET failed for {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> bool:
        """Set value in Redis with TTL (seconds). Returns success bool."""
        client = await self.get_client()
        if not client:
            return False
        
        try:
            # Pickle allows storing complex Python objects (lists, dicts, models)
            pickled_val = pickle.dumps(value)
            await client.setex(key, ttl, pickled_val)
            return True
        except Exception as e:
            logger.warning(f"Redis SET failed for {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from Redis."""
        client = await self.get_client()
        if not client:
            return False
        try:
            await client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Redis DELETE failed for {key}: {e}")
            return False
            
    async def close(self):
        """Close connection."""
        if self._client:
            await self._client.close()
            self._client = None

# Singleton instance
redis_cache = RedisService()


def cache_response(ttl_seconds: int = 300, key_prefix: str = ""):
    """
    Decorator to cache function result in Redis.
    Key is generated from function name + args + kwargs.
    
    Usage:
        @cache_response(ttl_seconds=60, key_prefix="search")
        async def my_expensive_func(q: str): ...
    """
    def decorator(func: Callable):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Skip caching if disabled or simple unit test env
            if settings.ENV == "test":
                return await func(*args, **kwargs)

            # Generate Cache Key
            try:
                # Create unique signature from args
                arg_str = f"{args}-{kwargs}"
                arg_hash = hashlib.md5(arg_str.encode()).hexdigest()
                cache_key = f"{key_prefix}:{func.__name__}:{arg_hash}"
                
                # Try Cache
                cached_val = await redis_cache.get(cache_key)
                if cached_val is not None:
                    logger.debug(f"⚡ Cache HIT: {cache_key}")
                    return cached_val
            except Exception as e:
                 logger.debug(f"Cache key generation failed: {e}")
            
            # Run Function
            result = await func(*args, **kwargs)
            
            # Cache Result (fire and forget-ish)
            try:
                if result is not None:
                    await redis_cache.set(cache_key, result, ttl=ttl_seconds)
                    logger.debug(f"💾 Cache SET: {cache_key}")
            except Exception as e:
                logger.warning(f"Result caching failed: {e}")

            return result
        return wrapper
    return decorator
