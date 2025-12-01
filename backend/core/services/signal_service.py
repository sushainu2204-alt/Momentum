"""
Signal Service
Handles signal generation and publishing.
"""
from datetime import datetime
from typing import Dict
from backend.config import settings
from backend.core.models import Signal
from backend.infrastructure.messaging import IMessageBroker


class SignalService:
    """
    Service for managing trading signals.
    Publishes signals via message broker for downstream consumers.
    """
    
    def __init__(self, message_broker: IMessageBroker = None):
        # Dependency injection - use provided broker or default to Redis
        if message_broker is None:
            from backend.infrastructure.messaging import RedisMessageBroker
            message_broker = RedisMessageBroker(settings.REDIS_URL)
        
        self.message_broker = message_broker
        self.signals_channel = settings.SIGNALS_CHANNEL
    
    async def publish_signal(
        self,
        instrument_token: int,
        signal_type: str,
        price: float,
        strategy_name: str = "EMA_CROSSOVER",
        metadata: Dict = None
    ):
        """
        Publish trading signal to Redis.
        
        Args:
            instrument_token: Instrument token
            signal_type: "BUY" or "SELL"
            price: Current price
            strategy_name: Name of strategy
            metadata: Additional metadata (EMAs, etc.)
        """
        signal = Signal(
            instrument_token=instrument_token,
            signal_type=signal_type,
            price=price,
            timestamp=datetime.utcnow(),
            strategy_name=strategy_name,
            metadata=metadata or {}
        )
        
        await self.message_broker.publish(self.signals_channel, signal.to_json())
        
        print(f"📢 Published {signal_type} signal for {instrument_token} @ ₹{price}")
        print(f"   Metadata: {metadata}")
