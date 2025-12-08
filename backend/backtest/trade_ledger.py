"""
Trade Ledger Module

Records all trades, positions, and portfolio history.
Provides comprehensive trade tracking and reporting.

Features:
    - Trade recording with full details
    - Position history tracking
    - Daily P&L tracking
    - Strategy-wise breakdown
    - Export to various formats
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field, asdict
from datetime import datetime, date, time, timedelta
from typing import Dict, List, Optional, Tuple, Any
from enum import Enum
import json
import csv
from pathlib import Path
import logging

from .order_simulator import BacktestPosition, PositionStatus
from .events import FillEvent, ExitSignalEvent

logger = logging.getLogger(__name__)


@dataclass
class Trade:
    """
    Completed trade record.
    
    Represents a round-trip trade from entry to exit.
    """
    trade_id: str
    symbol: str
    instrument_token: int
    strategy_id: str
    strategy_name: str
    
    # Entry
    entry_time: datetime
    entry_price: float
    quantity: int
    
    # Exit
    exit_time: datetime
    exit_price: float
    exit_reason: str
    
    # P&L
    gross_pnl: float
    commission: float
    net_pnl: float
    pnl_pct: float
    
    # Risk metrics
    initial_sl: float
    final_sl: float
    target: float
    sl_trail_count: int
    risk_taken: float  # Entry - SL
    reward_achieved: float  # Exit - Entry
    rr_ratio: float  # Reward / Risk
    
    # Duration
    holding_minutes: int
    holding_candles: int
    
    # Additional metadata
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        d = asdict(self)
        # Convert datetime to string
        d['entry_time'] = self.entry_time.isoformat()
        d['exit_time'] = self.exit_time.isoformat()
        return d
    
    @classmethod
    def from_position(
        cls,
        position: BacktestPosition,
        commission: float = 0.0,
        strategy_name: str = ""
    ) -> 'Trade':
        """Create trade from closed position."""
        
        gross_pnl = position.realized_pnl
        net_pnl = gross_pnl - commission
        pnl_pct = (position.exit_price - position.entry_price) / position.entry_price * 100
        
        risk_taken = position.entry_price - position.initial_sl
        reward_achieved = position.exit_price - position.entry_price
        rr_ratio = reward_achieved / risk_taken if risk_taken > 0 else 0
        
        holding_time = position.exit_time - position.entry_time
        holding_minutes = int(holding_time.total_seconds() / 60)
        
        return cls(
            trade_id=position.position_id,
            symbol=position.symbol,
            instrument_token=position.instrument_token,
            strategy_id=position.strategy_id,
            strategy_name=strategy_name,
            entry_time=position.entry_time,
            entry_price=position.entry_price,
            quantity=position.quantity,
            exit_time=position.exit_time,
            exit_price=position.exit_price,
            exit_reason=position.exit_reason,
            gross_pnl=gross_pnl,
            commission=commission,
            net_pnl=net_pnl,
            pnl_pct=pnl_pct,
            initial_sl=position.initial_sl,
            final_sl=position.current_sl,
            target=position.target,
            sl_trail_count=position.sl_trail_count,
            risk_taken=risk_taken,
            reward_achieved=reward_achieved,
            rr_ratio=rr_ratio,
            holding_minutes=holding_minutes,
            holding_candles=holding_minutes  # Assuming 1-min candles
        )


@dataclass
class DailyRecord:
    """Daily trading record."""
    date: date
    starting_capital: float
    ending_capital: float
    
    # Trades
    total_trades: int
    winning_trades: int
    losing_trades: int
    
    # P&L
    gross_pnl: float
    commission: float
    net_pnl: float
    
    # Returns
    daily_return_pct: float
    cumulative_return_pct: float
    
    # Drawdown
    peak_capital: float
    drawdown_pct: float
    
    # By strategy
    trades_by_strategy: Dict[str, int] = field(default_factory=dict)
    pnl_by_strategy: Dict[str, float] = field(default_factory=dict)


@dataclass
class EquityPoint:
    """Single point in equity curve."""
    timestamp: datetime
    equity: float
    cash: float
    invested: float
    unrealized_pnl: float
    realized_pnl: float
    drawdown_pct: float


class TradeLedger:
    """
    Trade ledger for recording and analyzing trades.
    
    Provides:
    - Complete trade history
    - Daily P&L tracking
    - Equity curve generation
    - Strategy-wise analysis
    - Export capabilities
    
    Usage:
        ledger = TradeLedger(initial_capital=100000)
        
        # Record a trade
        ledger.record_trade(trade)
        
        # Get analysis
        trades_df = ledger.get_trades_dataframe()
        daily_df = ledger.get_daily_summary()
        equity_df = ledger.get_equity_curve()
    """
    
    def __init__(
        self,
        initial_capital: float,
        output_path: Optional[str] = None
    ):
        """
        Initialize trade ledger.
        
        Args:
            initial_capital: Starting capital
            output_path: Path for saving reports
        """
        self.initial_capital = initial_capital
        self.output_path = Path(output_path) if output_path else None
        
        # Trade records
        self._trades: List[Trade] = []
        
        # Daily records
        self._daily_records: Dict[date, DailyRecord] = {}
        
        # Equity curve
        self._equity_curve: List[EquityPoint] = []
        
        # Current state
        self._current_equity = initial_capital
        self._peak_equity = initial_capital
        self._total_commission = 0.0
    
    def record_trade(self, trade: Trade) -> None:
        """
        Record a completed trade.
        
        Args:
            trade: Trade to record
        """
        self._trades.append(trade)
        self._total_commission += trade.commission
        
        # Update daily record
        trade_date = trade.exit_time.date()
        self._update_daily_record(trade_date, trade)
        
        logger.debug(
            f"Trade recorded: {trade.symbol} | "
            f"PnL: ₹{trade.net_pnl:.0f} ({trade.pnl_pct:+.2f}%)"
        )
    
    def _update_daily_record(self, trade_date: date, trade: Trade) -> None:
        """Update daily record with trade."""
        
        if trade_date not in self._daily_records:
            # Get previous day's ending capital
            prev_capital = self._get_previous_day_capital(trade_date)
            
            self._daily_records[trade_date] = DailyRecord(
                date=trade_date,
                starting_capital=prev_capital,
                ending_capital=prev_capital,
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                gross_pnl=0.0,
                commission=0.0,
                net_pnl=0.0,
                daily_return_pct=0.0,
                cumulative_return_pct=0.0,
                peak_capital=prev_capital,
                drawdown_pct=0.0
            )
        
        record = self._daily_records[trade_date]
        
        # Update trade counts
        record.total_trades += 1
        if trade.net_pnl >= 0:
            record.winning_trades += 1
        else:
            record.losing_trades += 1
        
        # Update P&L
        record.gross_pnl += trade.gross_pnl
        record.commission += trade.commission
        record.net_pnl += trade.net_pnl
        record.ending_capital = record.starting_capital + record.net_pnl
        
        # Update returns
        if record.starting_capital > 0:
            record.daily_return_pct = (record.net_pnl / record.starting_capital) * 100
        
        cumulative_pnl = sum(t.net_pnl for t in self._trades)
        record.cumulative_return_pct = (cumulative_pnl / self.initial_capital) * 100
        
        # Update peak and drawdown
        if record.ending_capital > record.peak_capital:
            record.peak_capital = record.ending_capital
        
        if record.peak_capital > 0:
            record.drawdown_pct = (
                (record.peak_capital - record.ending_capital) / record.peak_capital
            ) * 100
        
        # Update strategy breakdown
        strategy = trade.strategy_id
        record.trades_by_strategy[strategy] = record.trades_by_strategy.get(strategy, 0) + 1
        record.pnl_by_strategy[strategy] = record.pnl_by_strategy.get(strategy, 0) + trade.net_pnl
    
    def _get_previous_day_capital(self, trade_date: date) -> float:
        """Get capital at end of previous day."""
        
        prev_dates = [d for d in self._daily_records.keys() if d < trade_date]
        
        if prev_dates:
            prev_date = max(prev_dates)
            return self._daily_records[prev_date].ending_capital
        
        return self.initial_capital
    
    def record_equity_point(
        self,
        timestamp: datetime,
        equity: float,
        cash: float,
        invested: float,
        unrealized_pnl: float,
        realized_pnl: float
    ) -> None:
        """
        Record a point in the equity curve.
        
        Called periodically during backtest (e.g., every candle or daily).
        """
        # Update peak
        if equity > self._peak_equity:
            self._peak_equity = equity
        
        # Calculate drawdown
        drawdown_pct = 0.0
        if self._peak_equity > 0:
            drawdown_pct = ((self._peak_equity - equity) / self._peak_equity) * 100
        
        point = EquityPoint(
            timestamp=timestamp,
            equity=equity,
            cash=cash,
            invested=invested,
            unrealized_pnl=unrealized_pnl,
            realized_pnl=realized_pnl,
            drawdown_pct=drawdown_pct
        )
        
        self._equity_curve.append(point)
        self._current_equity = equity
    
    def get_trades(self) -> List[Trade]:
        """Get all trades."""
        return self._trades
    
    def get_trades_dataframe(self) -> pd.DataFrame:
        """Get trades as DataFrame."""
        if not self._trades:
            return pd.DataFrame()
        
        records = [t.to_dict() for t in self._trades]
        df = pd.DataFrame(records)
        
        # Parse datetime columns
        df['entry_time'] = pd.to_datetime(df['entry_time'])
        df['exit_time'] = pd.to_datetime(df['exit_time'])
        
        return df
    
    def get_trades_by_strategy(self, strategy_id: str) -> List[Trade]:
        """Get trades for a specific strategy."""
        return [t for t in self._trades if t.strategy_id == strategy_id]
    
    def get_trades_by_symbol(self, symbol: str) -> List[Trade]:
        """Get trades for a specific symbol."""
        return [t for t in self._trades if t.symbol == symbol]
    
    def get_trades_by_date(self, trade_date: date) -> List[Trade]:
        """Get trades for a specific date."""
        return [t for t in self._trades if t.exit_time.date() == trade_date]
    
    def get_daily_summary(self) -> pd.DataFrame:
        """Get daily summary as DataFrame."""
        if not self._daily_records:
            return pd.DataFrame()
        
        records = []
        for d, record in sorted(self._daily_records.items()):
            records.append({
                'date': d,
                'starting_capital': record.starting_capital,
                'ending_capital': record.ending_capital,
                'total_trades': record.total_trades,
                'winning_trades': record.winning_trades,
                'losing_trades': record.losing_trades,
                'win_rate': (record.winning_trades / record.total_trades * 100) 
                           if record.total_trades > 0 else 0,
                'gross_pnl': record.gross_pnl,
                'commission': record.commission,
                'net_pnl': record.net_pnl,
                'daily_return_pct': record.daily_return_pct,
                'cumulative_return_pct': record.cumulative_return_pct,
                'drawdown_pct': record.drawdown_pct
            })
        
        return pd.DataFrame(records)
    
    def get_equity_curve(self) -> pd.DataFrame:
        """Get equity curve as DataFrame."""
        if not self._equity_curve:
            return pd.DataFrame()
        
        records = []
        for point in self._equity_curve:
            records.append({
                'timestamp': point.timestamp,
                'equity': point.equity,
                'cash': point.cash,
                'invested': point.invested,
                'unrealized_pnl': point.unrealized_pnl,
                'realized_pnl': point.realized_pnl,
                'drawdown_pct': point.drawdown_pct
            })
        
        return pd.DataFrame(records)
    
    def get_strategy_summary(self) -> pd.DataFrame:
        """Get summary by strategy."""
        strategy_stats = {}
        
        for trade in self._trades:
            sid = trade.strategy_id
            if sid not in strategy_stats:
                strategy_stats[sid] = {
                    'strategy': sid,
                    'total_trades': 0,
                    'winning_trades': 0,
                    'losing_trades': 0,
                    'gross_pnl': 0,
                    'net_pnl': 0,
                    'total_commission': 0,
                    'avg_winner': [],
                    'avg_loser': [],
                    'max_winner': 0,
                    'max_loser': 0,
                    'avg_holding_mins': []
                }
            
            stats = strategy_stats[sid]
            stats['total_trades'] += 1
            stats['gross_pnl'] += trade.gross_pnl
            stats['net_pnl'] += trade.net_pnl
            stats['total_commission'] += trade.commission
            stats['avg_holding_mins'].append(trade.holding_minutes)
            
            if trade.net_pnl >= 0:
                stats['winning_trades'] += 1
                stats['avg_winner'].append(trade.net_pnl)
                stats['max_winner'] = max(stats['max_winner'], trade.net_pnl)
            else:
                stats['losing_trades'] += 1
                stats['avg_loser'].append(abs(trade.net_pnl))
                stats['max_loser'] = max(stats['max_loser'], abs(trade.net_pnl))
        
        # Calculate averages
        records = []
        for sid, stats in strategy_stats.items():
            records.append({
                'strategy': sid,
                'total_trades': stats['total_trades'],
                'winning_trades': stats['winning_trades'],
                'losing_trades': stats['losing_trades'],
                'win_rate': (stats['winning_trades'] / stats['total_trades'] * 100)
                           if stats['total_trades'] > 0 else 0,
                'gross_pnl': stats['gross_pnl'],
                'net_pnl': stats['net_pnl'],
                'total_commission': stats['total_commission'],
                'avg_winner': np.mean(stats['avg_winner']) if stats['avg_winner'] else 0,
                'avg_loser': np.mean(stats['avg_loser']) if stats['avg_loser'] else 0,
                'max_winner': stats['max_winner'],
                'max_loser': stats['max_loser'],
                'avg_holding_mins': np.mean(stats['avg_holding_mins']) if stats['avg_holding_mins'] else 0,
                'profit_factor': (sum(stats['avg_winner']) / sum(stats['avg_loser']))
                                if stats['avg_loser'] and sum(stats['avg_loser']) > 0 else 0
            })
        
        return pd.DataFrame(records)
    
    def get_symbol_summary(self) -> pd.DataFrame:
        """Get summary by symbol."""
        symbol_stats = {}
        
        for trade in self._trades:
            sym = trade.symbol
            if sym not in symbol_stats:
                symbol_stats[sym] = {
                    'symbol': sym,
                    'total_trades': 0,
                    'winning_trades': 0,
                    'net_pnl': 0
                }
            
            stats = symbol_stats[sym]
            stats['total_trades'] += 1
            stats['net_pnl'] += trade.net_pnl
            if trade.net_pnl >= 0:
                stats['winning_trades'] += 1
        
        records = []
        for sym, stats in symbol_stats.items():
            records.append({
                'symbol': sym,
                'total_trades': stats['total_trades'],
                'winning_trades': stats['winning_trades'],
                'win_rate': (stats['winning_trades'] / stats['total_trades'] * 100)
                           if stats['total_trades'] > 0 else 0,
                'net_pnl': stats['net_pnl']
            })
        
        df = pd.DataFrame(records)
        return df.sort_values('net_pnl', ascending=False)
    
    def export_trades_csv(self, filepath: Optional[str] = None) -> str:
        """Export trades to CSV."""
        if filepath is None:
            filepath = self.output_path / "trades.csv" if self.output_path else "trades.csv"
        
        df = self.get_trades_dataframe()
        df.to_csv(filepath, index=False)
        
        logger.info(f"Trades exported to {filepath}")
        return str(filepath)
    
    def export_trades_json(self, filepath: Optional[str] = None) -> str:
        """Export trades to JSON."""
        if filepath is None:
            filepath = self.output_path / "trades.json" if self.output_path else "trades.json"
        
        trades_data = [t.to_dict() for t in self._trades]
        
        with open(filepath, 'w') as f:
            json.dump(trades_data, f, indent=2, default=str)
        
        logger.info(f"Trades exported to {filepath}")
        return str(filepath)
    
    def get_summary_stats(self) -> Dict[str, Any]:
        """Get summary statistics."""
        if not self._trades:
            return {
                'total_trades': 0,
                'net_pnl': 0,
                'win_rate': 0
            }
        
        winners = [t for t in self._trades if t.net_pnl >= 0]
        losers = [t for t in self._trades if t.net_pnl < 0]
        
        total_pnl = sum(t.net_pnl for t in self._trades)
        total_gross = sum(t.gross_pnl for t in self._trades)
        
        return {
            'total_trades': len(self._trades),
            'winning_trades': len(winners),
            'losing_trades': len(losers),
            'win_rate': len(winners) / len(self._trades) * 100 if self._trades else 0,
            'gross_pnl': total_gross,
            'total_commission': self._total_commission,
            'net_pnl': total_pnl,
            'total_return_pct': (total_pnl / self.initial_capital) * 100,
            'avg_winner': np.mean([t.net_pnl for t in winners]) if winners else 0,
            'avg_loser': np.mean([abs(t.net_pnl) for t in losers]) if losers else 0,
            'largest_winner': max([t.net_pnl for t in winners]) if winners else 0,
            'largest_loser': max([abs(t.net_pnl) for t in losers]) if losers else 0,
            'avg_holding_minutes': np.mean([t.holding_minutes for t in self._trades]),
            'trading_days': len(self._daily_records),
            'final_equity': self._current_equity,
            'peak_equity': self._peak_equity
        }
    
    def reset(self) -> None:
        """Reset ledger."""
        self._trades.clear()
        self._daily_records.clear()
        self._equity_curve.clear()
        self._current_equity = self.initial_capital
        self._peak_equity = self.initial_capital
        self._total_commission = 0.0
