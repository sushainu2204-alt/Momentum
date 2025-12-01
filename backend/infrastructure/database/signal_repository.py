"""
Signal Repository
Database operations for trading signals using the IDatabase interface.
"""
from typing import List, Dict, Optional, Any
from datetime import datetime
import json
import logging

from .base import IDatabase
from models import Signal

logger = logging.getLogger(__name__)


class SignalRepository:
    """
    Repository for signal database operations.
    Uses the IDatabase interface for database abstraction.
    """
    
    def __init__(self, database: IDatabase):
        """
        Initialize repository with database instance.
        
        Args:
            database: Database instance implementing IDatabase
        """
        self.db = database
    
    async def save_signal(
        self,
        signal: Signal,
        strategy_name: str,
        metadata: Optional[Dict] = None
    ) -> int:
        """
        Save a trading signal to database.
        
        Args:
            signal: Signal object
            strategy_name: Name of the strategy
            metadata: Additional metadata (filters, indicators, etc.)
        
        Returns:
            Signal ID
        """
        try:
            signal_data = {
                "timestamp": signal.timestamp.isoformat() if isinstance(signal.timestamp, datetime) else signal.timestamp,
                "strategy": strategy_name,
                "symbol": signal.symbol,
                "instrument_token": getattr(signal, 'instrument_token', None),
                "signal_type": signal.signal_type,
                "price": float(signal.price),
                "stop_loss": float(signal.stop_loss) if signal.stop_loss else None,
                "target": float(signal.target) if signal.target else None,
                "quantity": signal.quantity if hasattr(signal, 'quantity') else None,
                "reason": getattr(signal, 'reason', ''),
                "metadata": json.dumps(metadata or {})
            }
            
            result = await self.db.insert("signals", signal_data)
            logger.info(f"Signal saved to DB: {strategy_name} - {signal.symbol} @ {signal.price}")
            return result
            
        except Exception as e:
            logger.error(f"Error saving signal to DB: {e}")
            raise
    
    async def get_signals_by_date(
        self,
        date: datetime,
        strategy_name: Optional[str] = None
    ) -> List[Dict]:
        """
        Retrieve signals for a specific date.
        
        Args:
            date: Date to retrieve signals for
            strategy_name: Filter by strategy (None = all)
        
        Returns:
            List of signal dictionaries
        """
        try:
            date_str = date.strftime("%Y-%m-%d")
            
            if strategy_name:
                query = """
                    SELECT * FROM signals
                    WHERE DATE(timestamp) = :date AND strategy = :strategy
                    ORDER BY timestamp DESC
                """
                params = {"date": date_str, "strategy": strategy_name}
            else:
                query = """
                    SELECT * FROM signals
                    WHERE DATE(timestamp) = :date
                    ORDER BY timestamp DESC
                """
                params = {"date": date_str}
            
            signals = await self.db.fetch_all(query, params)
            return signals
            
        except Exception as e:
            logger.error(f"Error retrieving signals from DB: {e}")
            return []
    
    async def get_signals_by_symbol(
        self,
        symbol: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[Dict]:
        """
        Retrieve signals for a specific symbol.
        
        Args:
            symbol: Symbol to filter by
            start_date: Start date (optional)
            end_date: End date (optional)
        
        Returns:
            List of signal dictionaries
        """
        try:
            if start_date and end_date:
                query = """
                    SELECT * FROM signals
                    WHERE symbol = :symbol
                    AND timestamp BETWEEN :start_date AND :end_date
                    ORDER BY timestamp DESC
                """
                params = {
                    "symbol": symbol,
                    "start_date": start_date.isoformat(),
                    "end_date": end_date.isoformat()
                }
            else:
                query = """
                    SELECT * FROM signals
                    WHERE symbol = :symbol
                    ORDER BY timestamp DESC
                """
                params = {"symbol": symbol}
            
            signals = await self.db.fetch_all(query, params)
            return signals
            
        except Exception as e:
            logger.error(f"Error retrieving signals for {symbol}: {e}")
            return []
    
    async def get_signals_by_strategy(
        self,
        strategy_name: str,
        limit: Optional[int] = None
    ) -> List[Dict]:
        """
        Retrieve signals for a specific strategy.
        
        Args:
            strategy_name: Strategy to filter by
            limit: Maximum number of signals to return
        
        Returns:
            List of signal dictionaries
        """
        try:
            query = """
                SELECT * FROM signals
                WHERE strategy = :strategy
                ORDER BY timestamp DESC
            """
            if limit:
                query += f" LIMIT {limit}"
            
            signals = await self.db.fetch_all(query, {"strategy": strategy_name})
            return signals
            
        except Exception as e:
            logger.error(f"Error retrieving signals for {strategy_name}: {e}")
            return []
    
    async def get_daily_summary(self, date: datetime) -> Dict[str, Any]:
        """
        Get summary statistics for signals on a specific date.
        
        Args:
            date: Date to summarize
        
        Returns:
            Summary statistics
        """
        try:
            date_str = date.strftime("%Y-%m-%d")
            
            query = """
                SELECT
                    strategy,
                    COUNT(*) as signal_count,
                    COUNT(DISTINCT symbol) as unique_symbols
                FROM signals
                WHERE DATE(timestamp) = :date
                GROUP BY strategy
            """
            
            results = await self.db.fetch_all(query, {"date": date_str})
            
            summary = {
                "date": date_str,
                "total_signals": sum(r["signal_count"] for r in results),
                "strategies": {
                    r["strategy"]: {
                        "count": r["signal_count"],
                        "unique_symbols": r["unique_symbols"]
                    }
                    for r in results
                }
            }
            
            return summary
            
        except Exception as e:
            logger.error(f"Error generating daily summary: {e}")
            return {"date": date_str, "total_signals": 0, "strategies": {}}


# Database schema for signals table
SIGNALS_TABLE_SCHEMA = """
CREATE TABLE IF NOT EXISTS signals (
    id SERIAL PRIMARY KEY,
    timestamp TIMESTAMP NOT NULL,
    strategy VARCHAR(50) NOT NULL,
    symbol VARCHAR(20) NOT NULL,
    instrument_token BIGINT,
    signal_type VARCHAR(10) NOT NULL,
    price DECIMAL(10, 2) NOT NULL,
    stop_loss DECIMAL(10, 2),
    target DECIMAL(10, 2),
    quantity INTEGER,
    reason TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_signals_timestamp ON signals(timestamp);
CREATE INDEX IF NOT EXISTS idx_signals_strategy ON signals(strategy);
CREATE INDEX IF NOT EXISTS idx_signals_symbol ON signals(symbol);
CREATE INDEX IF NOT EXISTS idx_signals_date ON signals(DATE(timestamp));
"""
