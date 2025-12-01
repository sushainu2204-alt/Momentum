"""
Cache Abstraction
Defines interface for caching systems.
"""
from abc import ABC, abstractmethod
from typing import Optional, Any
from datetime import timedelta


class ICache(ABC):
    """Interface for cache operations"""
    
    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        """Get value from cache"""
        pass
    
    @abstractmethod
    def set(self, key: str, value: str, ttl: Optional[int] = None):
        """Set value in cache with optional TTL (seconds)"""
        pass
    
    @abstractmethod
    def delete(self, key: str):
        """Delete key from cache"""
        pass
    
    @abstractmethod
    def keys(self, pattern: str) -> list:
        """Get keys matching pattern"""
        pass
    
    @abstractmethod
    def close(self):
        """Close cache connection"""
        pass
