# backend/backtest_engine.py
"""
Backtest engine for EMA crossover strategy
"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from collections import deque
from dataclasses import dataclass
import json

@dataclass
class Trade:
    """Represents a single trade"""
    entry_time: datetime
    entry_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    signal: str = "BUY"  # BUY or SELL
    quantity: int = 1
    pnl: float = 0.0
    pnl_percent: float = 0.0
    
    def close_trade(self, exit_time: datetime, exit_price: float):
        """Close the trade and calculate P&L"""
        self.exit_time = exit_time
        self.exit_price = exit_price
        
        if self.signal == "BUY":
            self.pnl = (exit_price - self.entry_price) * self.quantity
        else:  # SELL/SHORT
            self.pnl = (self.entry_price - exit_price) * self.quantity
            
        self.pnl_percent = (self.pnl / (self.entry_price * self.quantity)) * 100
    
    def is_open(self) -> bool:
        """Check if trade is still open"""
        return self.exit_time is None


class EMAStrategy:
    """EMA Crossover Strategy for backtesting"""
    
    def __init__(self, fast_period: int = 9, slow_period: int = 21):
        self.fast_period = fast_period
        self.slow_period = slow_period
        
    def calculate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Calculate EMA crossover signals on historical data.
        
        Args:
            df: DataFrame with 'close' prices
            
        Returns:
            DataFrame with additional columns: ema9, ema21, signal
        """
        df = df.copy()
        
        # Calculate EMAs
        df['ema_fast'] = df['close'].ewm(span=self.fast_period, adjust=False).mean()
        df['ema_slow'] = df['close'].ewm(span=self.slow_period, adjust=False).mean()
        
        # Generate signals
        df['signal'] = 0
        df.loc[df['ema_fast'] > df['ema_slow'], 'signal'] = 1  # BUY
        df.loc[df['ema_fast'] < df['ema_slow'], 'signal'] = -1  # SELL
        
        # Detect crossovers (signal changes)
        df['position'] = df['signal'].diff()
        
        return df


class BacktestEngine:
    """Main backtesting engine"""
    
    def __init__(
        self,
        initial_capital: float = 100000,
        commission: float = 0.0003,  # 0.03% per trade
        slippage: float = 0.0001,  # 0.01% slippage
    ):
        self.initial_capital = initial_capital
        self.commission = commission
        self.slippage = slippage
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = []
        
    def run_backtest(
        self,
        df: pd.DataFrame,
        strategy: EMAStrategy,
        position_size_pct: float = 0.95  # Use 95% of capital per trade
    ) -> Dict:
        """
        Run backtest on historical data.
        
        Args:
            df: DataFrame with OHLC data (must have 'date' and 'close' columns)
            strategy: Strategy instance
            position_size_pct: Percentage of capital to use per trade
            
        Returns:
            Dictionary with backtest results
        """
        print(f"Running backtest on {len(df)} candles...")
        
        # Calculate signals
        df = strategy.calculate_signals(df)
        
        # Drop NaN rows (first few rows where EMA can't be calculated)
        df = df.dropna()
        
        if len(df) < strategy.slow_period + 10:
            print("⚠ Not enough data for backtest")
            return {}
        
        # Initialize
        capital = self.initial_capital
        position = None  # Current open position
        self.trades = []
        self.equity_curve = [capital]
        
        # Iterate through candles
        for idx, row in df.iterrows():
            date = row['date']
            close = row['close']
            signal_change = row['position']
            
            # Check for signal changes (crossovers)
            if signal_change == 2:  # Bullish crossover (BUY signal)
                # Close any short position
                if position and position.signal == "SELL":
                    exit_price = close * (1 + self.slippage)  # Slippage
                    position.close_trade(date, exit_price)
                    
                    # Update capital
                    capital += position.pnl
                    capital -= abs(position.pnl) * self.commission  # Commission
                    
                    self.trades.append(position)
                    self.equity_curve.append(capital)
                    position = None
                
                # Open long position
                if position is None and capital > 0:
                    entry_price = close * (1 + self.slippage)
                    quantity = int((capital * position_size_pct) / entry_price)
                    
                    if quantity > 0:
                        position = Trade(
                            entry_time=date,
                            entry_price=entry_price,
                            signal="BUY",
                            quantity=quantity
                        )
                        capital -= entry_price * quantity * self.commission  # Entry commission
                        
            elif signal_change == -2:  # Bearish crossover (SELL signal)
                # Close any long position
                if position and position.signal == "BUY":
                    exit_price = close * (1 - self.slippage)
                    position.close_trade(date, exit_price)
                    
                    capital += position.pnl
                    capital -= abs(position.pnl) * self.commission
                    
                    self.trades.append(position)
                    self.equity_curve.append(capital)
                    position = None
                
                # Open short position (optional - for now just close longs)
                # In Indian markets, shorting requires additional margin
                
            # Update equity curve with open position MTM
            if position:
                mtm_pnl = (close - position.entry_price) * position.quantity if position.signal == "BUY" else (position.entry_price - close) * position.quantity
                self.equity_curve.append(capital + mtm_pnl)
            else:
                self.equity_curve.append(capital)
        
        # Close any remaining open position at last price
        if position:
            last_row = df.iloc[-1]
            position.close_trade(last_row['date'], last_row['close'])
            capital += position.pnl
            self.trades.append(position)
        
        # Calculate metrics
        results = self._calculate_metrics(df)
        results['final_capital'] = capital
        results['total_return'] = ((capital - self.initial_capital) / self.initial_capital) * 100
        
        return results
    
    def _calculate_metrics(self, df: pd.DataFrame) -> Dict:
        """Calculate performance metrics"""
        if not self.trades:
            return {
                'total_trades': 0,
                'winning_trades': 0,
                'losing_trades': 0,
                'win_rate': 0,
                'avg_win': 0,
                'avg_loss': 0,
                'largest_win': 0,
                'largest_loss': 0,
                'profit_factor': 0,
                'sharpe_ratio': 0,
                'max_drawdown': 0,
                'max_drawdown_pct': 0,
            }
        
        winning_trades = [t for t in self.trades if t.pnl > 0]
        losing_trades = [t for t in self.trades if t.pnl < 0]
        
        total_wins = sum(t.pnl for t in winning_trades)
        total_losses = abs(sum(t.pnl for t in losing_trades))
        
        # Calculate drawdown
        equity_series = pd.Series(self.equity_curve)
        running_max = equity_series.expanding().max()
        drawdown = equity_series - running_max
        max_drawdown = drawdown.min()
        max_drawdown_pct = (max_drawdown / running_max.max()) * 100 if running_max.max() > 0 else 0
        
        # Calculate Sharpe ratio
        returns = equity_series.pct_change().dropna()
        sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0  # Annualized
        
        return {
            'total_trades': len(self.trades),
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate': (len(winning_trades) / len(self.trades)) * 100 if self.trades else 0,
            'avg_win': total_wins / len(winning_trades) if winning_trades else 0,
            'avg_loss': total_losses / len(losing_trades) if losing_trades else 0,
            'largest_win': max((t.pnl for t in winning_trades), default=0),
            'largest_loss': min((t.pnl for t in losing_trades), default=0),
            'profit_factor': total_wins / total_losses if total_losses > 0 else 0,
            'sharpe_ratio': sharpe_ratio,
            'max_drawdown': max_drawdown,
            'max_drawdown_pct': max_drawdown_pct,
            'total_pnl': sum(t.pnl for t in self.trades),
        }
    
    def print_results(self, results: Dict):
        """Pretty print backtest results"""
        print("\n" + "="*60)
        print("BACKTEST RESULTS")
        print("="*60)
        
        print(f"\n📊 PERFORMANCE METRICS:")
        print(f"  Initial Capital:     ₹{self.initial_capital:,.2f}")
        print(f"  Final Capital:       ₹{results.get('final_capital', 0):,.2f}")
        print(f"  Total Return:        {results.get('total_return', 0):.2f}%")
        print(f"  Total P&L:           ₹{results.get('total_pnl', 0):,.2f}")
        
        print(f"\n📈 TRADE STATISTICS:")
        print(f"  Total Trades:        {results.get('total_trades', 0)}")
        print(f"  Winning Trades:      {results.get('winning_trades', 0)}")
        print(f"  Losing Trades:       {results.get('losing_trades', 0)}")
        print(f"  Win Rate:            {results.get('win_rate', 0):.2f}%")
        
        print(f"\n💰 WIN/LOSS ANALYSIS:")
        print(f"  Average Win:         ₹{results.get('avg_win', 0):,.2f}")
        print(f"  Average Loss:        ₹{results.get('avg_loss', 0):,.2f}")
        print(f"  Largest Win:         ₹{results.get('largest_win', 0):,.2f}")
        print(f"  Largest Loss:        ₹{results.get('largest_loss', 0):,.2f}")
        print(f"  Profit Factor:       {results.get('profit_factor', 0):.2f}")
        
        print(f"\n📉 RISK METRICS:")
        print(f"  Sharpe Ratio:        {results.get('sharpe_ratio', 0):.2f}")
        print(f"  Max Drawdown:        ₹{results.get('max_drawdown', 0):,.2f}")
        print(f"  Max Drawdown %:      {results.get('max_drawdown_pct', 0):.2f}%")
        
        print("\n" + "="*60 + "\n")
    
    def get_trade_log(self) -> pd.DataFrame:
        """Export trades to DataFrame"""
        if not self.trades:
            return pd.DataFrame()
        
        trade_data = []
        for t in self.trades:
            trade_data.append({
                'entry_time': t.entry_time,
                'entry_price': t.entry_price,
                'exit_time': t.exit_time,
                'exit_price': t.exit_price,
                'signal': t.signal,
                'quantity': t.quantity,
                'pnl': t.pnl,
                'pnl_percent': t.pnl_percent,
            })
        
        return pd.DataFrame(trade_data)
