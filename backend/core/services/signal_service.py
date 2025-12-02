"""
Signal Service
Handles signal generation and publishing.
"""
from datetime import datetime
from typing import Dict, Optional
from backend.config import settings
from backend.models import Signal, SignalType
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
        symbol: str,
        instrument_token: int,
        signal_type: str,
        price: float,
        stop_loss: Optional[float] = None,
        target: Optional[float] = None,
        reason: Optional[str] = None,
        metadata: Dict = None
    ):
        """
        Publish trading signal to Redis.
        
        Args:
            symbol: Stock symbol
            instrument_token: Instrument token
            signal_type: "BUY" or "SELL"
            price: Current price
            stop_loss: Stop loss price
            target: Target price
            reason: Signal reason
            metadata: Additional metadata (EMAs, etc.)
        """
        signal = Signal(
            symbol=symbol,
            instrument_token=instrument_token,
            signal_type=SignalType(signal_type),
            price=price,
            timestamp=datetime.now(),
            stop_loss=stop_loss,
            target=target,
            reason=reason,
            metadata=metadata or {}
        )
        
        await self.message_broker.publish(self.signals_channel, signal.to_json())
        
        print(f"📢 Published {signal_type} signal for {symbol} ({instrument_token}) @ ₹{price}")
        print(f"   SL: ₹{stop_loss}, Target: ₹{target}")
        print(f"   Metadata: {metadata}")
