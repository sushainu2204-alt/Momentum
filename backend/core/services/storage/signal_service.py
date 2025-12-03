"""
Signal Service
Handles signal generation and publishing.
"""
import logging
from datetime import datetime
from typing import Dict, Optional

from backend.config import settings
from backend.core.models import Signal, SignalType
from backend.infrastructure.messaging import IMessageBroker

logger = logging.getLogger(__name__)


class SignalService:
    """
    Service for managing trading signals.
    Publishes signals via message broker for downstream consumers.
    
    Usage:
        # With dependency injection (preferred)
        broker = RedisMessageBroker(redis_url)
        service = SignalService(message_broker=broker)
        
        # With default Redis broker
        service = SignalService()
        
        # Publish a signal
        await service.publish_signal(
            symbol="RELIANCE",
            instrument_token=738561,
            signal_type="BUY",
            price=2450.50,
            stop_loss=2400.00,
            target=2550.00
        )
    """
    
    def __init__(self, message_broker: Optional[IMessageBroker] = None):
        """
        Initialize SignalService.
        
        Args:
            message_broker: Message broker for publishing signals.
                           If None, creates a RedisMessageBroker.
        """
        if message_broker is None:
            from backend.infrastructure.messaging import RedisMessageBroker
            message_broker = RedisMessageBroker(settings.REDIS_URL)
            logger.debug("Initialized with default RedisMessageBroker")
        
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
        metadata: Optional[Dict] = None
    ) -> None:
        """
        Publish trading signal to message broker.
        
        Args:
            symbol: Stock symbol (e.g., "RELIANCE")
            instrument_token: Kite instrument token
            signal_type: "BUY" or "SELL"
            price: Current/entry price
            stop_loss: Stop loss price (optional)
            target: Target price (optional)
            reason: Signal generation reason (optional)
            metadata: Additional metadata like EMAs, volume, etc. (optional)
        
        Raises:
            Exception: If message broker publish fails
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
        
        logger.info(
            f"Published {signal_type} signal: {symbol} @ ₹{price:.2f} "
            f"(SL: ₹{stop_loss}, Target: ₹{target})"
        )
        logger.debug(f"Signal metadata: {metadata}")
