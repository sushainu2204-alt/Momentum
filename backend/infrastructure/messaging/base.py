"""
Message Broker Abstraction
Defines interface for pub/sub messaging systems.
"""
from abc import ABC, abstractmethod
from typing import Callable, AsyncIterator, Any


class IMessageBroker(ABC):
    """Interface for message broker (pub/sub system)"""
    
    @abstractmethod
    async def publish(self, channel: str, message: str):
        """Publish message to a channel"""
        pass
    
    @abstractmethod
    async def subscribe(self, pattern: str) -> AsyncIterator[dict]:
        """Subscribe to channel pattern and yield messages"""
        pass
    
    @abstractmethod
    async def close(self):
        """Close connections"""
        pass


class IMessageBrokerSync(ABC):
    """Synchronous interface for message broker (for threaded contexts)"""
    
    @abstractmethod
    def publish(self, channel: str, message: str):
        """Publish message to a channel"""
        pass
    
    @abstractmethod
    def close(self):
        """Close connections"""
        pass
