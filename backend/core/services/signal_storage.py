"""
Signal Storage Service

Handles saving and retrieving trading signals to/from files or database.
Designed for easy migration from file storage to database storage.

File Structure:
- signals/
  - YYYY-MM-DD/
    - vwap_breakout_signals.json       (all signals generated)
    - bullish_flag_signals.json
    - vwap_ema_breakout_signals.json
- orders/
  - YYYY-MM-DD/
    - vwap_breakout_orders.json        (only executed orders)
    - bullish_flag_orders.json
    - vwap_ema_breakout_orders.json

Each signal is stored with:
- timestamp
- symbol
- strategy
- signal_type (BUY/SELL)
- price
- stop_loss
- target
- quantity
- reason
- metadata (additional context)
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional, Any
import logging
import aiofiles

from backend.models import Signal
from backend.infrastructure.database.base import IDatabase
from backend.infrastructure.database.signal_repository import SignalRepository

logger = logging.getLogger(__name__)


class SignalStorage:
    """
    Storage interface for trading signals.
    
    Supports both file-based and database storage.
    Default: file-based (easy to migrate to DB later)
    """
    
    def __init__(self, storage_type: str = "file", base_path: str = "./signals", orders_path: str = "./orders", database: Optional[IDatabase] = None):
        """
        Initialize signal storage.
        
        Args:
            storage_type: 'file' or 'database'
            base_path: Base directory for file storage
            orders_path: Base directory for orders storage
            database: Database instance (required if storage_type='database')
        """
        self.storage_type = storage_type
        self.base_path = Path(base_path)
        self.orders_path = Path(orders_path)
        self.database = database
        self.repository = SignalRepository(database) if database else None
        
        if storage_type == "file":
            self.base_path.mkdir(parents=True, exist_ok=True)
            self.orders_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"Signal storage initialized: {self.base_path}")
            logger.info(f"Orders storage initialized: {self.orders_path}")
        elif storage_type == "database":
            if not database:
                raise ValueError("Database instance required when storage_type='database'")
            logger.info("Signal storage initialized with database")
    
    async def save_signal(
        self,
        signal: Signal,
        strategy_name: str,
        metadata: Optional[Dict] = None
    ):
        """
        Save a trading signal.
        
        Args:
            signal: Signal object
            strategy_name: Strategy identifier
            metadata: Additional context (filters, indicators, etc.)
        """
        if self.storage_type == "file":
            await self._save_to_file(signal, strategy_name, metadata)
        elif self.storage_type == "database":
            await self._save_to_db(signal, strategy_name, metadata)
    
    async def get_signals(
        self,
        date: datetime,
        strategy_name: Optional[str] = None
    ) -> List[Dict]:
        """
        Retrieve signals for a date.
        
        Args:
            date: Date to retrieve signals for
            strategy_name: Filter by strategy (None = all strategies)
        
        Returns:
            List of signal dictionaries
        """
        if self.storage_type == "file":
            return self._get_from_file(date, strategy_name)
        elif self.storage_type == "database":
            return await self._get_from_db(date, strategy_name)
        return []
    
    async def _save_to_file(
        self,
        signal: Signal,
        strategy_name: str,
        metadata: Optional[Dict]
    ):
        """Save signal to JSON file (async)"""
        # Create date directory
        date_str = signal.timestamp.strftime("%Y-%m-%d")
        date_dir = self.base_path / date_str
        date_dir.mkdir(parents=True, exist_ok=True)
        
        # File path
        filename = f"{strategy_name}_signals.json"
        filepath = date_dir / filename
        
        # Load existing signals
        signals = []
        if filepath.exists():
            async with aiofiles.open(filepath, 'r') as f:
                content = await f.read()
                signals = json.loads(content)
        
        # Prepare signal data
        signal_data = {
            "timestamp": signal.timestamp.isoformat(),
            "symbol": signal.symbol,
            "instrument_token": signal.instrument_token,
            "signal_type": signal.signal_type.value,
            "price": signal.price,
            "stop_loss": signal.stop_loss,
            "target": signal.target,
            "quantity": signal.quantity,
            "reason": signal.reason,
            "metadata": metadata or {}
        }
        
        # Append and save
        signals.append(signal_data)
        
        async with aiofiles.open(filepath, 'w') as f:
            await f.write(json.dumps(signals, indent=2))
        
        logger.info(f"✅ Signal saved: {strategy_name} - {signal.symbol} @ {signal.price:.2f}")
    
    def _get_from_file(
        self,
        date: datetime,
        strategy_name: Optional[str]
    ) -> List[Dict]:
        """Retrieve signals from JSON file"""
        date_str = date.strftime("%Y-%m-%d")
        date_dir = self.base_path / date_str
        
        if not date_dir.exists():
            return []
        
        signals = []
        
        # Get all strategy files or specific strategy
        if strategy_name:
            files = [date_dir / f"{strategy_name}_signals.json"]
        else:
            files = list(date_dir.glob("*_signals.json"))
        
        for filepath in files:
            if filepath.exists():
                with open(filepath, 'r') as f:
                    data = json.load(f)
                    signals.extend(data)
        
        return signals
    
    async def _save_to_db(
        self,
        signal: Signal,
        strategy_name: str,
        metadata: Optional[Dict]
    ):
        """
        Save signal to database using SignalRepository.
        
        Schema defined in: backend/infrastructure/database/signal_repository.py
        """
        if not self.repository:
            raise RuntimeError("Database repository not initialized")
        
        await self.repository.save_signal(signal, strategy_name, metadata)
    
    async def _get_from_db(
        self,
        date: datetime,
        strategy_name: Optional[str]
    ) -> List[Dict]:
        """
        Retrieve signals from database using SignalRepository.
        """
        if not self.repository:
            raise RuntimeError("Database repository not initialized")
        
        return await self.repository.get_signals_by_date(date, strategy_name)
    
    def export_daily_report(self, date: datetime) -> str:
        """
        Export daily signals report.
        
        Args:
            date: Date to export
        
        Returns:
            Path to exported CSV file
        """
        import pandas as pd
        
        signals = self.get_signals(date)
        
        if not signals:
            logger.info(f"No signals found for {date.strftime('%Y-%m-%d')}")
            return ""
        
        # Convert to DataFrame
        df = pd.DataFrame(signals)
        
        # Export to CSV
        filename = f"signals_report_{date.strftime('%Y%m%d')}.csv"
        df.to_csv(filename, index=False)
        
        logger.info(f"📄 Daily report exported: {filename}")
        return filename
    
    async def save_executed_order(
        self,
        signal: Signal,
        strategy_name: str,
        order_id: Optional[str],
        quantity: int,
        execution_result: Dict[str, Any]
    ):
        """
        Save executed order to separate orders file (async).
        
        Args:
            signal: Original signal
            strategy_name: Strategy identifier
            order_id: Kite order ID (None in dry run)
            quantity: Executed quantity
            execution_result: Result from signal executor (status, reason, etc.)
        """
        # Create date directory
        date_str = signal.timestamp.strftime("%Y-%m-%d")
        date_dir = self.orders_path / date_str
        date_dir.mkdir(parents=True, exist_ok=True)
        
        # File path
        filename = f"{strategy_name}_orders.json"
        filepath = date_dir / filename
        
        # Load existing orders
        orders = []
        if filepath.exists():
            async with aiofiles.open(filepath, 'r') as f:
                content = await f.read()
                orders = json.loads(content)
        
        # Prepare order data
        order_data = {
            "timestamp": signal.timestamp.isoformat(),
            "symbol": signal.symbol,
            "instrument_token": signal.instrument_token,
            "signal_type": signal.signal_type.value,
            "price": signal.price,
            "stop_loss": signal.stop_loss,
            "target": signal.target,
            "quantity": quantity,
            "order_id": order_id,
            "execution_status": execution_result.get("status"),
            "execution_reason": execution_result.get("reason"),
            "signal_reason": signal.reason,
            "metadata": execution_result.get("metadata", {})
        }
        
        # Append and save
        orders.append(order_data)
        
        async with aiofiles.open(filepath, 'w') as f:
            await f.write(json.dumps(orders, indent=2))
        
        logger.info(f"✅ Order saved: {strategy_name} - {signal.symbol} @ {signal.price:.2f} (Order ID: {order_id})")
