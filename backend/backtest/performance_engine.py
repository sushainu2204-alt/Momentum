"""
Performance Engine Module

Calculates comprehensive performance metrics for backtest results.
Implements industry-standard metrics used by professional traders.

Metrics Computed:
    - Returns (CAGR, Total Return, Daily Returns)
    - Risk (Max Drawdown, Volatility, VaR)
    - Risk-Adjusted (Sharpe, Sortino, Calmar)
    - Trade Statistics (Win Rate, Profit Factor, Expectancy)
    - Advanced (SQN, Recovery Factor, Ulcer Index)
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from datetime import datetime, date, timedelta
from typing import Dict, List, Optional, Tuple, Any
import logging
from scipy import stats

from .trade_ledger import TradeLedger, Trade

logger = logging.getLogger(__name__)


@dataclass
class PerformanceMetrics:
    """
    Comprehensive performance metrics.
    
    Contains all calculated metrics from backtest.
    """
    
    # Basic Info
    start_date: date = None
    end_date: date = None
    trading_days: int = 0
    total_trades: int = 0
    
    # Capital
    initial_capital: float = 0.0
    final_capital: float = 0.0
    peak_capital: float = 0.0
    
    # Returns
    total_return: float = 0.0
    total_return_pct: float = 0.0
    cagr: float = 0.0
    avg_daily_return: float = 0.0
    best_day: float = 0.0
    worst_day: float = 0.0
    
    # Risk Metrics
    max_drawdown_pct: float = 0.0
    max_drawdown_amount: float = 0.0
    max_drawdown_duration_days: int = 0
    volatility_annual: float = 0.0
    downside_deviation: float = 0.0
    var_95: float = 0.0  # Value at Risk 95%
    
    # Risk-Adjusted Returns
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    calmar_ratio: float = 0.0
    
    # Trade Statistics
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    avg_winner: float = 0.0
    avg_loser: float = 0.0
    profit_factor: float = 0.0
    expectancy: float = 0.0
    payoff_ratio: float = 0.0
    
    # Advanced Metrics
    sqn: float = 0.0  # System Quality Number
    recovery_factor: float = 0.0
    ulcer_index: float = 0.0
    
    # Streak Analysis
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0
    avg_win_streak: float = 0.0
    avg_loss_streak: float = 0.0
    
    # Time Analysis
    avg_holding_time_minutes: float = 0.0
    avg_trades_per_day: float = 0.0
    most_active_hour: int = 0
    
    # By Strategy
    metrics_by_strategy: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    # By Exit Reason
    exits_by_reason: Dict[str, int] = field(default_factory=dict)
    pnl_by_exit_reason: Dict[str, float] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            'basic': {
                'start_date': str(self.start_date),
                'end_date': str(self.end_date),
                'trading_days': self.trading_days,
                'total_trades': self.total_trades
            },
            'capital': {
                'initial': self.initial_capital,
                'final': self.final_capital,
                'peak': self.peak_capital
            },
            'returns': {
                'total_return': self.total_return,
                'total_return_pct': self.total_return_pct,
                'cagr': self.cagr,
                'avg_daily_return': self.avg_daily_return,
                'best_day': self.best_day,
                'worst_day': self.worst_day
            },
            'risk': {
                'max_drawdown_pct': self.max_drawdown_pct,
                'max_drawdown_amount': self.max_drawdown_amount,
                'volatility_annual': self.volatility_annual,
                'var_95': self.var_95
            },
            'risk_adjusted': {
                'sharpe_ratio': self.sharpe_ratio,
                'sortino_ratio': self.sortino_ratio,
                'calmar_ratio': self.calmar_ratio
            },
            'trades': {
                'winning': self.winning_trades,
                'losing': self.losing_trades,
                'win_rate': self.win_rate,
                'profit_factor': self.profit_factor,
                'expectancy': self.expectancy,
                'sqn': self.sqn
            },
            'by_strategy': self.metrics_by_strategy,
            'exits': self.exits_by_reason
        }
    
    def print_summary(self) -> None:
        """Print formatted summary."""
        print("\n" + "=" * 60)
        print("BACKTEST PERFORMANCE SUMMARY")
        print("=" * 60)
        
        print(f"\n📅 Period: {self.start_date} to {self.end_date} ({self.trading_days} days)")
        print(f"📊 Total Trades: {self.total_trades}")
        
        print("\n💰 RETURNS")
        print("-" * 40)
        print(f"  Initial Capital:    ₹{self.initial_capital:,.0f}")
        print(f"  Final Capital:      ₹{self.final_capital:,.0f}")
        print(f"  Total Return:       ₹{self.total_return:,.0f} ({self.total_return_pct:+.2f}%)")
        print(f"  CAGR:               {self.cagr:.2f}%")
        print(f"  Best Day:           {self.best_day:+.2f}%")
        print(f"  Worst Day:          {self.worst_day:+.2f}%")
        
        print("\n📉 RISK METRICS")
        print("-" * 40)
        print(f"  Max Drawdown:       {self.max_drawdown_pct:.2f}%")
        print(f"  Annual Volatility:  {self.volatility_annual:.2f}%")
        print(f"  VaR (95%):          {self.var_95:.2f}%")
        
        print("\n⚖️  RISK-ADJUSTED")
        print("-" * 40)
        print(f"  Sharpe Ratio:       {self.sharpe_ratio:.2f}")
        print(f"  Sortino Ratio:      {self.sortino_ratio:.2f}")
        print(f"  Calmar Ratio:       {self.calmar_ratio:.2f}")
        
        print("\n🎯 TRADE STATISTICS")
        print("-" * 40)
        print(f"  Win Rate:           {self.win_rate:.1f}%")
        print(f"  Avg Winner:         ₹{self.avg_winner:,.0f}")
        print(f"  Avg Loser:          ₹{self.avg_loser:,.0f}")
        print(f"  Profit Factor:      {self.profit_factor:.2f}")
        print(f"  Expectancy:         ₹{self.expectancy:,.0f}")
        print(f"  SQN:                {self.sqn:.2f}")
        
        print("\n🔥 STREAKS")
        print("-" * 40)
        print(f"  Max Win Streak:     {self.max_consecutive_wins}")
        print(f"  Max Loss Streak:    {self.max_consecutive_losses}")
        
        if self.metrics_by_strategy:
            print("\n📈 BY STRATEGY")
            print("-" * 40)
            for strategy, metrics in self.metrics_by_strategy.items():
                print(f"\n  {strategy}:")
                print(f"    Trades: {metrics.get('trades', 0)}")
                print(f"    Win Rate: {metrics.get('win_rate', 0):.1f}%")
                print(f"    Net PnL: ₹{metrics.get('net_pnl', 0):,.0f}")
        
        if self.exits_by_reason:
            print("\n🚪 EXIT REASONS")
            print("-" * 40)
            for reason, count in self.exits_by_reason.items():
                pnl = self.pnl_by_exit_reason.get(reason, 0)
                print(f"  {reason}: {count} trades (₹{pnl:,.0f})")
        
        print("\n" + "=" * 60)


class PerformanceEngine:
    """
    Performance calculation engine.
    
    Calculates comprehensive metrics from trade ledger.
    
    Usage:
        engine = PerformanceEngine(ledger, initial_capital)
        metrics = engine.calculate_all_metrics()
        metrics.print_summary()
    """
    
    # Risk-free rate for Sharpe ratio (annual)
    RISK_FREE_RATE = 0.06  # 6% Indian G-Sec
    TRADING_DAYS_PER_YEAR = 250
    
    def __init__(
        self,
        ledger: TradeLedger,
        initial_capital: float
    ):
        """
        Initialize performance engine.
        
        Args:
            ledger: Trade ledger with recorded trades
            initial_capital: Starting capital
        """
        self.ledger = ledger
        self.initial_capital = initial_capital
        
        # Get data from ledger
        self._trades = ledger.get_trades()
        self._trades_df = ledger.get_trades_dataframe()
        self._daily_df = ledger.get_daily_summary()
        self._equity_df = ledger.get_equity_curve()
    
    def calculate_all_metrics(self) -> PerformanceMetrics:
        """
        Calculate all performance metrics.
        
        Returns:
            PerformanceMetrics object with all calculations
        """
        metrics = PerformanceMetrics()
        
        if not self._trades:
            logger.warning("No trades to analyze")
            return metrics
        
        # Basic info
        metrics.initial_capital = self.initial_capital
        metrics.total_trades = len(self._trades)
        
        # Calculate all metric groups
        self._calculate_period_info(metrics)
        self._calculate_return_metrics(metrics)
        self._calculate_risk_metrics(metrics)
        self._calculate_risk_adjusted_metrics(metrics)
        self._calculate_trade_statistics(metrics)
        self._calculate_advanced_metrics(metrics)
        self._calculate_streak_analysis(metrics)
        self._calculate_time_analysis(metrics)
        self._calculate_strategy_breakdown(metrics)
        self._calculate_exit_analysis(metrics)
        
        return metrics
    
    def _calculate_period_info(self, metrics: PerformanceMetrics) -> None:
        """Calculate period information."""
        if self._trades:
            entry_times = [t.entry_time for t in self._trades]
            exit_times = [t.exit_time for t in self._trades]
            
            metrics.start_date = min(entry_times).date()
            metrics.end_date = max(exit_times).date()
            metrics.trading_days = len(self._daily_df) if not self._daily_df.empty else 0
    
    def _calculate_return_metrics(self, metrics: PerformanceMetrics) -> None:
        """Calculate return metrics."""
        
        # Total return
        total_pnl = sum(t.net_pnl for t in self._trades)
        metrics.total_return = total_pnl
        metrics.total_return_pct = (total_pnl / self.initial_capital) * 100
        
        # Final and peak capital
        metrics.final_capital = self.initial_capital + total_pnl
        
        if not self._equity_df.empty:
            metrics.peak_capital = self._equity_df['equity'].max()
        else:
            metrics.peak_capital = metrics.final_capital
        
        # CAGR
        if metrics.trading_days > 0:
            years = metrics.trading_days / self.TRADING_DAYS_PER_YEAR
            if years > 0 and metrics.final_capital > 0:
                metrics.cagr = (
                    (metrics.final_capital / self.initial_capital) ** (1 / years) - 1
                ) * 100
        
        # Daily returns
        if not self._daily_df.empty:
            daily_returns = self._daily_df['daily_return_pct']
            metrics.avg_daily_return = daily_returns.mean()
            metrics.best_day = daily_returns.max()
            metrics.worst_day = daily_returns.min()
    
    def _calculate_risk_metrics(self, metrics: PerformanceMetrics) -> None:
        """Calculate risk metrics."""
        
        if not self._daily_df.empty:
            daily_returns = self._daily_df['daily_return_pct']
            
            # Max drawdown
            metrics.max_drawdown_pct = self._daily_df['drawdown_pct'].max()
            metrics.max_drawdown_amount = (
                metrics.max_drawdown_pct / 100 * metrics.peak_capital
            )
            
            # Volatility (annualized)
            daily_vol = daily_returns.std()
            metrics.volatility_annual = daily_vol * np.sqrt(self.TRADING_DAYS_PER_YEAR)
            
            # Downside deviation (for Sortino)
            negative_returns = daily_returns[daily_returns < 0]
            if len(negative_returns) > 0:
                metrics.downside_deviation = negative_returns.std() * np.sqrt(self.TRADING_DAYS_PER_YEAR)
            
            # Value at Risk (95%)
            if len(daily_returns) > 0:
                metrics.var_95 = np.percentile(daily_returns, 5)
        
        # Max drawdown duration
        if not self._equity_df.empty:
            metrics.max_drawdown_duration_days = self._calculate_max_dd_duration()
    
    def _calculate_max_dd_duration(self) -> int:
        """Calculate maximum drawdown duration in days."""
        if self._equity_df.empty:
            return 0
        
        equity = self._equity_df['equity'].values
        peak = np.maximum.accumulate(equity)
        
        # Find drawdown periods
        in_drawdown = equity < peak
        
        if not any(in_drawdown):
            return 0
        
        # Count consecutive days in drawdown
        max_duration = 0
        current_duration = 0
        
        for is_dd in in_drawdown:
            if is_dd:
                current_duration += 1
                max_duration = max(max_duration, current_duration)
            else:
                current_duration = 0
        
        return max_duration
    
    def _calculate_risk_adjusted_metrics(self, metrics: PerformanceMetrics) -> None:
        """Calculate risk-adjusted return metrics."""
        
        # Sharpe Ratio
        if metrics.volatility_annual > 0:
            excess_return = metrics.cagr - (self.RISK_FREE_RATE * 100)
            metrics.sharpe_ratio = excess_return / metrics.volatility_annual
        
        # Sortino Ratio
        if metrics.downside_deviation > 0:
            excess_return = metrics.cagr - (self.RISK_FREE_RATE * 100)
            metrics.sortino_ratio = excess_return / metrics.downside_deviation
        
        # Calmar Ratio
        if metrics.max_drawdown_pct > 0:
            metrics.calmar_ratio = metrics.cagr / metrics.max_drawdown_pct
    
    def _calculate_trade_statistics(self, metrics: PerformanceMetrics) -> None:
        """Calculate trade statistics."""
        
        winners = [t for t in self._trades if t.net_pnl >= 0]
        losers = [t for t in self._trades if t.net_pnl < 0]
        
        metrics.winning_trades = len(winners)
        metrics.losing_trades = len(losers)
        
        # Win rate
        if metrics.total_trades > 0:
            metrics.win_rate = (metrics.winning_trades / metrics.total_trades) * 100
        
        # Average winner/loser
        if winners:
            metrics.avg_winner = np.mean([t.net_pnl for t in winners])
        if losers:
            metrics.avg_loser = np.mean([abs(t.net_pnl) for t in losers])
        
        # Payoff ratio (avg winner / avg loser)
        if metrics.avg_loser > 0:
            metrics.payoff_ratio = metrics.avg_winner / metrics.avg_loser
        
        # Profit factor
        gross_profit = sum(t.net_pnl for t in winners) if winners else 0
        gross_loss = abs(sum(t.net_pnl for t in losers)) if losers else 0
        
        if gross_loss > 0:
            metrics.profit_factor = gross_profit / gross_loss
        elif gross_profit > 0:
            metrics.profit_factor = float('inf')
        
        # Expectancy
        if metrics.total_trades > 0:
            metrics.expectancy = metrics.total_return / metrics.total_trades
    
    def _calculate_advanced_metrics(self, metrics: PerformanceMetrics) -> None:
        """Calculate advanced metrics."""
        
        if not self._trades:
            return
        
        # System Quality Number (SQN)
        # SQN = sqrt(N) * Expectancy / StdDev(R)
        pnl_values = [t.net_pnl for t in self._trades]
        n = len(pnl_values)
        
        if n > 0:
            std_dev = np.std(pnl_values)
            if std_dev > 0:
                metrics.sqn = np.sqrt(n) * metrics.expectancy / std_dev
        
        # Recovery Factor
        # Total Return / Max Drawdown
        if metrics.max_drawdown_amount > 0:
            metrics.recovery_factor = metrics.total_return / metrics.max_drawdown_amount
        
        # Ulcer Index (measures downside volatility)
        if not self._equity_df.empty:
            equity = self._equity_df['equity'].values
            peak = np.maximum.accumulate(equity)
            drawdown_pct = (peak - equity) / peak * 100
            
            if len(drawdown_pct) > 0:
                metrics.ulcer_index = np.sqrt(np.mean(drawdown_pct ** 2))
    
    def _calculate_streak_analysis(self, metrics: PerformanceMetrics) -> None:
        """Calculate win/loss streak analysis."""
        
        if not self._trades:
            return
        
        # Sort trades by exit time
        sorted_trades = sorted(self._trades, key=lambda t: t.exit_time)
        
        # Track streaks
        current_win_streak = 0
        current_loss_streak = 0
        max_win_streak = 0
        max_loss_streak = 0
        win_streaks = []
        loss_streaks = []
        
        for trade in sorted_trades:
            if trade.net_pnl >= 0:
                current_win_streak += 1
                if current_loss_streak > 0:
                    loss_streaks.append(current_loss_streak)
                current_loss_streak = 0
                max_win_streak = max(max_win_streak, current_win_streak)
            else:
                current_loss_streak += 1
                if current_win_streak > 0:
                    win_streaks.append(current_win_streak)
                current_win_streak = 0
                max_loss_streak = max(max_loss_streak, current_loss_streak)
        
        # Don't forget the last streak
        if current_win_streak > 0:
            win_streaks.append(current_win_streak)
        if current_loss_streak > 0:
            loss_streaks.append(current_loss_streak)
        
        metrics.max_consecutive_wins = max_win_streak
        metrics.max_consecutive_losses = max_loss_streak
        metrics.avg_win_streak = np.mean(win_streaks) if win_streaks else 0
        metrics.avg_loss_streak = np.mean(loss_streaks) if loss_streaks else 0
    
    def _calculate_time_analysis(self, metrics: PerformanceMetrics) -> None:
        """Calculate time-based analysis."""
        
        if not self._trades:
            return
        
        # Average holding time
        holding_times = [t.holding_minutes for t in self._trades]
        metrics.avg_holding_time_minutes = np.mean(holding_times)
        
        # Average trades per day
        if metrics.trading_days > 0:
            metrics.avg_trades_per_day = metrics.total_trades / metrics.trading_days
        
        # Most active hour
        entry_hours = [t.entry_time.hour for t in self._trades]
        if entry_hours:
            hour_counts = pd.Series(entry_hours).value_counts()
            metrics.most_active_hour = hour_counts.idxmax()
    
    def _calculate_strategy_breakdown(self, metrics: PerformanceMetrics) -> None:
        """Calculate metrics by strategy."""
        
        strategy_trades: Dict[str, List[Trade]] = {}
        
        for trade in self._trades:
            sid = trade.strategy_id
            if sid not in strategy_trades:
                strategy_trades[sid] = []
            strategy_trades[sid].append(trade)
        
        for strategy_id, trades in strategy_trades.items():
            winners = [t for t in trades if t.net_pnl >= 0]
            
            metrics.metrics_by_strategy[strategy_id] = {
                'trades': len(trades),
                'winners': len(winners),
                'losers': len(trades) - len(winners),
                'win_rate': len(winners) / len(trades) * 100 if trades else 0,
                'gross_pnl': sum(t.gross_pnl for t in trades),
                'net_pnl': sum(t.net_pnl for t in trades),
                'avg_pnl': np.mean([t.net_pnl for t in trades]) if trades else 0,
                'profit_factor': self._calculate_profit_factor(trades)
            }
    
    def _calculate_profit_factor(self, trades: List[Trade]) -> float:
        """Calculate profit factor for trades."""
        winners = [t for t in trades if t.net_pnl >= 0]
        losers = [t for t in trades if t.net_pnl < 0]
        
        gross_profit = sum(t.net_pnl for t in winners) if winners else 0
        gross_loss = abs(sum(t.net_pnl for t in losers)) if losers else 0
        
        if gross_loss > 0:
            return gross_profit / gross_loss
        return float('inf') if gross_profit > 0 else 0
    
    def _calculate_exit_analysis(self, metrics: PerformanceMetrics) -> None:
        """Analyze trades by exit reason."""
        
        for trade in self._trades:
            reason = trade.exit_reason
            
            metrics.exits_by_reason[reason] = metrics.exits_by_reason.get(reason, 0) + 1
            metrics.pnl_by_exit_reason[reason] = (
                metrics.pnl_by_exit_reason.get(reason, 0) + trade.net_pnl
            )
    
    def generate_report(self, filepath: Optional[str] = None) -> str:
        """
        Generate comprehensive HTML report.
        
        Args:
            filepath: Path to save report
        
        Returns:
            Path to generated report
        """
        metrics = self.calculate_all_metrics()
        
        # Generate HTML (simplified)
        html = f"""
        <html>
        <head>
            <title>Backtest Report</title>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 20px; }}
                h1 {{ color: #333; }}
                table {{ border-collapse: collapse; width: 100%; }}
                th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
                th {{ background-color: #4CAF50; color: white; }}
                .positive {{ color: green; }}
                .negative {{ color: red; }}
            </style>
        </head>
        <body>
            <h1>Backtest Performance Report</h1>
            <p>Period: {metrics.start_date} to {metrics.end_date}</p>
            
            <h2>Summary</h2>
            <table>
                <tr><th>Metric</th><th>Value</th></tr>
                <tr><td>Total Trades</td><td>{metrics.total_trades}</td></tr>
                <tr><td>Win Rate</td><td>{metrics.win_rate:.1f}%</td></tr>
                <tr><td>Total Return</td><td class="{'positive' if metrics.total_return >= 0 else 'negative'}">₹{metrics.total_return:,.0f} ({metrics.total_return_pct:+.2f}%)</td></tr>
                <tr><td>CAGR</td><td>{metrics.cagr:.2f}%</td></tr>
                <tr><td>Max Drawdown</td><td>{metrics.max_drawdown_pct:.2f}%</td></tr>
                <tr><td>Sharpe Ratio</td><td>{metrics.sharpe_ratio:.2f}</td></tr>
                <tr><td>Profit Factor</td><td>{metrics.profit_factor:.2f}</td></tr>
                <tr><td>SQN</td><td>{metrics.sqn:.2f}</td></tr>
            </table>
        </body>
        </html>
        """
        
        if filepath:
            with open(filepath, 'w') as f:
                f.write(html)
            logger.info(f"Report saved to {filepath}")
            return filepath
        
        return html
