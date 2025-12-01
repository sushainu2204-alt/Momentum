"""
Redis implementation of cache.
"""
import redis
from typing import Optional
from .base import ICache


class RedisCache(ICache):
    """Redis cache implementation"""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis = redis.Redis.from_url(redis_url)
    
    def get(self, key: str) -> Optional[str]:
        """Get value from Redis"""
        value = self.redis.get(key)
        return value.decode() if value else None
    
    def set(self, key: str, value: str, ttl: Optional[int] = None):
        """Set value in Redis with optional TTL"""
        if ttl:
            self.redis.setex(key, ttl, value)
        else:
            self.redis.set(key, value)
    
    def delete(self, key: str):
        """Delete key from Redis"""
        self.redis.delete(key)
    
    def keys(self, pattern: str) -> list:
        """Get keys matching pattern"""
        keys = self.redis.keys(pattern)
        return [k.decode() for k in keys]
    
    def close(self):
        """Close Redis connection"""
        self.redis.close()


class InMemoryCache(ICache):
    """In-memory cache implementation (for testing)"""
    
    def __init__(self):
        self._cache = {}
    
    def get(self, key: str) -> Optional[str]:
        return self._cache.get(key)
    
    def set(self, key: str, value: str, ttl: Optional[int] = None):
        self._cache[key] = value
        # Note: TTL not implemented for in-memory (would need background task)
    
    def delete(self, key: str):
        self._cache.pop(key, None)
    
    def keys(self, pattern: str) -> list:
        # Simple pattern matching (not full Redis pattern support)
        if pattern.endswith("*"):
            prefix = pattern[:-1]
            return [k for k in self._cache.keys() if k.startswith(prefix)]
        return [k for k in self._cache.keys() if k == pattern]
    
    def close(self):
        pass
