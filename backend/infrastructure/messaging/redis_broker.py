"""
Redis implementation of message broker.
"""
import json
import redis
import redis.asyncio as aioredis
from typing import AsyncIterator
from .base import IMessageBroker, IMessageBrokerSync


class RedisMessageBroker(IMessageBroker):
    """Async Redis message broker implementation"""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis = None
        self.pubsub = None
    
    async def _ensure_connected(self):
        """Lazy connection initialization"""
        if self.redis is None:
            self.redis = aioredis.from_url(self.redis_url)
    
    async def publish(self, channel: str, message: str):
        """Publish message to Redis channel"""
        await self._ensure_connected()
        await self.redis.publish(channel, message)
    
    async def subscribe(self, pattern: str) -> AsyncIterator[dict]:
        """Subscribe to Redis channel pattern"""
        await self._ensure_connected()
        
        if self.pubsub is None:
            self.pubsub = self.redis.pubsub()
            await self.pubsub.psubscribe(pattern)
        
        async for message in self.pubsub.listen():
            if message.get("type") == "pmessage":
                data = message.get("data")
                if data:
                    try:
                        # Try to parse as JSON
                        parsed = json.loads(data)
                        yield {
                            "channel": message.get("channel", b"").decode() if isinstance(message.get("channel"), bytes) else message.get("channel"),
                            "data": parsed
                        }
                    except (json.JSONDecodeError, AttributeError):
                        # If not JSON, yield raw data
                        yield {
                            "channel": message.get("channel", b"").decode() if isinstance(message.get("channel"), bytes) else message.get("channel"),
                            "data": data.decode() if isinstance(data, bytes) else data
                        }
    
    async def close(self):
        """Close Redis connections"""
        if self.pubsub:
            await self.pubsub.close()
        if self.redis:
            await self.redis.close()


class RedisMessageBrokerSync(IMessageBrokerSync):
    """Sync Redis message broker implementation (for threaded contexts)"""
    
    def __init__(self, redis_url: str):
        self.redis_url = redis_url
        self.redis = redis.Redis.from_url(redis_url)
    
    def publish(self, channel: str, message: str):
        """Publish message to Redis channel"""
        self.redis.publish(channel, message)
    
    def close(self):
        """Close Redis connection"""
        self.redis.close()
