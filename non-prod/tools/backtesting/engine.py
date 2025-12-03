"""
Backtest Engine
Simulates trading strategy on historical data.
"""
import pandas as pd
import numpy as np
import sys
from pathlib import Path
from typing import Dict, List

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from backend.config import settings
from backend.core.models import Trade
from backend.core.strategies import EMACrossoverStrategy


class BacktestEngine:
    """
    Engine for backtesting trading strategies.
    Simulates realistic trading with commission and slippage.
    """
    
    def __init__(
        self,
        initial_capital: float = None,
        commission: float = None,
        slippage: float = None,
    ):
        self.initial_capital = initial_capital or settings.DEFAULT_INITIAL_CAPITAL
        self.commission = commission or settings.DEFAULT_COMMISSION
        self.slippage = slippage or settings.DEFAULT_SLIPPAGE
        self.trades: List[Trade] = []
        self.equity_curve: List[float] = []
    
    def run_backtest(
        self,
        df: pd.DataFrame,
        strategy: EMACrossoverStrategy,
        position_size_pct: float = None
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
        position_size_pct = position_size_pct or settings.DEFAULT_POSITION_SIZE
        
        print(f"\n{'='*60}")
        print(f"STARTING BACKTEST")
        print(f"{'='*60}")
        print(f"Strategy: {strategy.name}")
        print(f"Data points: {len(df)}")
        print(f"Initial capital: ₹{self.initial_capital:,.2f}")
        print(f"Commission: {self.commission*100:.3f}%")
        print(f"Slippage: {self.slippage*100:.3f}%")
        print(f"Position size: {position_size_pct*100:.1f}%")
        print(f"{'='*60}\n")
        
        # Calculate signals
        df = strategy.calculate_signals_dataframe(df)
        
        # Drop NaN rows
        df = df.dropna()
        
        if len(df) < strategy.min_data_points:
            print("⚠ Not enough data for backtest")
            return {}
        
        # Initialize
        capital = self.initial_capital
        position = None
        self.trades = []
        self.equity_curve = [capital]
        
        # Iterate through candles
        for idx, row in df.iterrows():
            date = row['date']
            close = row['close']
            signal_change = row['position']
            
            # Bullish crossover (BUY signal)
            if signal_change == 2:
                # Close any short position
                if position and position.signal == "SELL":
                    exit_price = close * (1 + self.slippage)
                    position.close_trade(date, exit_price)
                    
                    capital += position.pnl
                    capital -= abs(position.pnl) * self.commission
                    
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
                        capital -= entry_price * quantity * self.commission
                        
            # Bearish crossover (SELL signal)
            elif signal_change == -2:
                # Close any long position
                if position and position.signal == "BUY":
                    exit_price = close * (1 - self.slippage)
                    position.close_trade(date, exit_price)
                    
                    capital += position.pnl
                    capital -= abs(position.pnl) * self.commission
                    
                    self.trades.append(position)
                    self.equity_curve.append(capital)
                    position = None
                
            # Update equity curve with MTM
            if position:
                mtm_pnl = (close - position.entry_price) * position.quantity if position.signal == "BUY" else (position.entry_price - close) * position.quantity
                self.equity_curve.append(capital + mtm_pnl)
            else:
                self.equity_curve.append(capital)
        
        # Close remaining position
        if position:
            last_row = df.iloc[-1]
            position.close_trade(last_row['date'], last_row['close'])
            capital += position.pnl
            self.trades.append(position)
        
        # Calculate metrics
        results = self._calculate_metrics()
        results['final_capital'] = capital
        results['total_return'] = ((capital - self.initial_capital) / self.initial_capital) * 100
        results['period_start'] = df['date'].iloc[0]
        results['period_end'] = df['date'].iloc[-1]
        
        return results
    
    def _calculate_metrics(self) -> Dict:
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
                'total_pnl': 0,
            }
        
        winning_trades = [t for t in self.trades if t.pnl > 0]
        losing_trades = [t for t in self.trades if t.pnl < 0]
        
        total_wins = sum(t.pnl for t in winning_trades)
        total_losses = abs(sum(t.pnl for t in losing_trades))
        
        # Drawdown
        equity_series = pd.Series(self.equity_curve)
        running_max = equity_series.expanding().max()
        drawdown = equity_series - running_max
        max_drawdown = drawdown.min()
        max_drawdown_pct = (max_drawdown / running_max.max()) * 100 if running_max.max() > 0 else 0
        
        # Sharpe ratio
        returns = equity_series.pct_change().dropna()
        sharpe_ratio = (returns.mean() / returns.std()) * np.sqrt(252) if returns.std() > 0 else 0
        
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
        
        print(f"\n📅 PERIOD:")
        print(f"  From: {results.get('period_start')}")
        print(f"  To:   {results.get('period_end')}")
        
        print(f"\n📊 PERFORMANCE:")
        print(f"  Initial Capital:     ₹{self.initial_capital:,.2f}")
        print(f"  Final Capital:       ₹{results.get('final_capital', 0):,.2f}")
        print(f"  Total Return:        {results.get('total_return', 0):.2f}%")
        print(f"  Total P&L:           ₹{results.get('total_pnl', 0):,.2f}")
        
        print(f"\n📈 TRADES:")
        print(f"  Total Trades:        {results.get('total_trades', 0)}")
        print(f"  Winning Trades:      {results.get('winning_trades', 0)}")
        print(f"  Losing Trades:       {results.get('losing_trades', 0)}")
        print(f"  Win Rate:            {results.get('win_rate', 0):.2f}%")
        
        print(f"\n💰 WIN/LOSS:")
        print(f"  Average Win:         ₹{results.get('avg_win', 0):,.2f}")
        print(f"  Average Loss:        ₹{results.get('avg_loss', 0):,.2f}")
        print(f"  Largest Win:         ₹{results.get('largest_win', 0):,.2f}")
        print(f"  Largest Loss:        ₹{results.get('largest_loss', 0):,.2f}")
        print(f"  Profit Factor:       {results.get('profit_factor', 0):.2f}")
        
        print(f"\n📉 RISK:")
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
