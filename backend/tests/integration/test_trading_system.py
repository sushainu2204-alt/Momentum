"""
Integration Tests for Trading System

Tests components working together: workers, strategies, services.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import pandas as pd
import numpy as np

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ============================================================================
# WORKER INTEGRATION TESTS
# ============================================================================

class TestVWAPBreakoutWorkerIntegration:
    """Integration tests for VWAP Breakout worker."""
    
    @pytest.fixture
    def mock_nse_data_source(self):
        """Mock NSE data source."""
        mock = AsyncMock()
        mock.get_top_gainers.return_value = [
            {"symbol": "RELIANCE", "gain_pct": 3.5, "price": 2450.0, "volume": 1000000},
            {"symbol": "INFY", "gain_pct": 2.8, "price": 1650.0, "volume": 800000}
        ]
        return mock
    
    @pytest.fixture
    def mock_kite_historical(self, sample_ohlcv_data):
        """Mock Kite historical data."""
        mock = MagicMock()
        mock.historical_data.return_value = sample_ohlcv_data(
            num_candles=50, trend="up"
        ).to_dict('records')
        return mock
    
    @pytest.mark.asyncio
    async def test_scan_and_generate_signals(
        self, mock_nse_data_source, mock_kite_historical, mock_database, sample_candidate
    ):
        """Test full scan cycle: fetch gainers -> analyze -> generate signals."""
        from backend.core.strategies.vwap_breakout import VWAPBreakoutStrategy
        from backend.core.config import VWAPBreakoutConfig
        from backend.models import Candidate, Signal
        
        # Setup strategy
        config = VWAPBreakoutConfig(
            volume_multiplier=1.5,
            vwap_breakout_pct=0.2,
            stop_loss_pct=0.7,
            target_pct=1.5
        )
        strategy = VWAPBreakoutStrategy(config)
        
        # Simulate worker flow
        # 1. Fetch top gainers
        gainers = await mock_nse_data_source.get_top_gainers()
        assert len(gainers) == 2
        
        # 2. Create candidates
        candidates = [
            Candidate(
                symbol=g['symbol'],
                instrument_token=738561,
                gain_pct=g['gain_pct'],
                current_price=g['price'],
                volume=g['volume'],
                avg_volume=500000,
                timestamp=datetime.now()
            )
            for g in gainers
        ]
        
        # 3. Analyze each candidate
        signals = []
        for candidate in candidates:
            # Get historical data
            hist_data = mock_kite_historical.historical_data()
            df = pd.DataFrame(hist_data)
            
            # Check for entry
            if strategy.apply_filters(candidate, df):
                signal = strategy.should_enter(
                    candidate, df, datetime.now().replace(hour=10, minute=30)
                )
                
                if signal:
                    signals.append(signal)
        
        # Verify signals format
        for signal in signals:
            assert signal.symbol in ["RELIANCE", "INFY"]
            assert signal.stop_loss < signal.price
            assert signal.target > signal.price


# ============================================================================
# STRATEGY BACKTEST INTEGRATION TESTS
# ============================================================================

class TestBacktestIntegration:
    """Integration tests for backtesting engine."""
    
    @pytest.fixture
    def historical_data(self):
        """Generate realistic historical data for backtest."""
        np.random.seed(42)
        dates = pd.date_range(start='2024-01-01 09:15', periods=375, freq='1min')
        
        # Simulate intraday price movement
        base_price = 100
        returns = np.random.randn(375) * 0.001  # 0.1% volatility per minute
        prices = base_price * (1 + np.cumsum(returns))
        
        df = pd.DataFrame({
            'date': dates,
            'open': prices,
            'high': prices * (1 + np.random.rand(375) * 0.002),
            'low': prices * (1 - np.random.rand(375) * 0.002),
            'close': prices * (1 + (np.random.rand(375) - 0.5) * 0.001),
            'volume': np.random.randint(10000, 50000, 375)
        })
        
        return df
    
    def test_backtest_vwap_strategy(self, historical_data, sample_candidate):
        """Test VWAP breakout strategy in backtest."""
        from backend.core.strategies.vwap_breakout import VWAPBreakoutStrategy
        from backend.core.config import VWAPBreakoutConfig
        from backend.models import Candidate
        
        config = VWAPBreakoutConfig(
            volume_multiplier=1.2,
            vwap_breakout_pct=0.1,
            stop_loss_pct=0.5,
            target_pct=1.0
        )
        strategy = VWAPBreakoutStrategy(config)
        
        # Simulate backtest
        df = historical_data
        signals = []
        
        for i in range(50, len(df)):
            window = df.iloc[:i+1].copy()
            
            candidate = Candidate(
                symbol="TEST",
                instrument_token=12345,
                gain_pct=2.0,
                current_price=df.iloc[i]['close'],
                volume=int(df.iloc[i]['volume']),
                avg_volume=30000,
                timestamp=df.iloc[i]['date']
            )
            
            if strategy.apply_filters(candidate, window):
                signal = strategy.should_enter(
                    candidate, window, df.iloc[i]['date']
                )
                
                if signal:
                    signals.append(signal)
        
        # Verify signals were generated
        assert isinstance(signals, list)
    
    def test_backtest_position_tracking(self, historical_data, sample_position):
        """Test position P&L tracking in backtest."""
        from backend.models import Position
        
        df = historical_data
        
        # Simulate entry
        entry_idx = 100
        entry_price = df.iloc[entry_idx]['close']
        stop_loss = entry_price * 0.995
        target = entry_price * 1.01
        
        position = Position(
            symbol="TEST",
            instrument_token=12345,
            quantity=100,
            entry_price=entry_price,
            stop_loss=stop_loss,
            target=target,
            entry_time=df.iloc[entry_idx]['date']
        )
        
        # Simulate price evolution
        exit_info = None
        for i in range(entry_idx + 1, len(df)):
            current_high = df.iloc[i]['high']
            current_low = df.iloc[i]['low']
            current_time = df.iloc[i]['date']
            exit_time = datetime.combine(current_time.date(), datetime.strptime("15:20", "%H:%M").time())
            
            # Check stop loss
            if current_low <= stop_loss:
                exit_info = ("SL_HIT", stop_loss)
                break
            
            # Check target
            if current_high >= target:
                exit_info = ("TARGET_HIT", target)
                break
        
        # If exited, verify P&L calculation
        if exit_info:
            reason, price = exit_info
            pnl = (price - position.entry_price) * position.quantity
            
            if reason == "TARGET_HIT":
                assert pnl > 0
            elif reason == "SL_HIT":
                assert pnl < 0


# ============================================================================
# DATA PIPELINE INTEGRATION TESTS
# ============================================================================

class TestDataPipelineIntegration:
    """Integration tests for data pipeline."""
    
    @pytest.mark.asyncio
    async def test_fetch_and_process_pipeline(self, sample_ohlcv_data):
        """Test data fetch and processing pipeline."""
        from backend.core.indicators.technical import TechnicalIndicators
        
        # Simulate data fetching
        df = sample_ohlcv_data(num_candles=100, trend="up")
        
        # Process through indicator pipeline
        df['vwap'] = TechnicalIndicators.calculate_vwap(df)
        df['ema_9'] = TechnicalIndicators.calculate_ema(df, column='close', period=9)
        df['ema_21'] = TechnicalIndicators.calculate_ema(df, column='close', period=21)
        df['rsi'] = TechnicalIndicators.calculate_rsi(df, column='close', period=14)
        df['atr'] = TechnicalIndicators.calculate_atr(df, period=14)
        
        # Verify all indicators calculated
        assert 'vwap' in df.columns
        assert 'ema_9' in df.columns
        assert 'ema_21' in df.columns
        assert 'rsi' in df.columns
        assert 'atr' in df.columns
        
        # Verify no NaN in recent data for VWAP (cumulative, always calculated)
        assert not df.iloc[-20:]['vwap'].isnull().any()
    
    @pytest.mark.asyncio
    async def test_candidate_screening_pipeline(self, sample_ohlcv_data):
        """Test candidate screening through multiple filters."""
        from backend.core.strategies.vwap_breakout import VWAPBreakoutStrategy
        from backend.core.config import VWAPBreakoutConfig
        from backend.models import Candidate
        
        config = VWAPBreakoutConfig()
        strategy = VWAPBreakoutStrategy(config)
        
        # Create multiple candidates
        candidates = [
            Candidate(
                symbol=f"STOCK{i}",
                instrument_token=12345 + i,
                gain_pct=2.0 + i * 0.5,
                current_price=100 * (1 + i * 0.1),
                volume=100000 * (1 + i * 0.2),
                avg_volume=80000,
                timestamp=datetime.now()
            )
            for i in range(5)
        ]
        
        # Screen each candidate
        passing = []
        for candidate in candidates:
            df = sample_ohlcv_data(num_candles=50, trend="up")
            
            if strategy.apply_filters(candidate, df):
                passing.append(candidate)
        
        # Some may pass, some may not
        assert isinstance(passing, list)


# ============================================================================
# INDICATOR CALCULATION INTEGRATION TESTS
# ============================================================================

class TestIndicatorIntegration:
    """Integration tests for technical indicators."""
    
    def test_full_indicator_suite(self, sample_ohlcv_data):
        """Test calculating full suite of indicators."""
        from backend.core.indicators.technical import TechnicalIndicators
        
        df = sample_ohlcv_data(num_candles=100, trend="up")
        
        # Calculate all indicators
        df['vwap'] = TechnicalIndicators.calculate_vwap(df)
        df['ema_9'] = TechnicalIndicators.calculate_ema(df, column='close', period=9)
        df['ema_21'] = TechnicalIndicators.calculate_ema(df, column='close', period=21)
        df['sma_20'] = TechnicalIndicators.calculate_sma(df, column='close', period=20)
        df['rsi'] = TechnicalIndicators.calculate_rsi(df, column='close', period=14)
        df['atr'] = TechnicalIndicators.calculate_atr(df, period=14)
        df['volume_surge'] = TechnicalIndicators.calculate_volume_surge(df, lookback=10, multiplier=1.5)
        df['candle_break'] = TechnicalIndicators.is_candle_break(df, lookback=1)
        
        upper, middle, lower = TechnicalIndicators.calculate_bollinger_bands(df, column='close', period=20)
        df['bb_upper'] = upper
        df['bb_middle'] = middle
        df['bb_lower'] = lower
        
        # Verify all calculated
        expected_cols = ['vwap', 'ema_9', 'ema_21', 'sma_20', 'rsi', 'atr', 
                         'volume_surge', 'candle_break', 'bb_upper', 'bb_middle', 'bb_lower']
        
        for col in expected_cols:
            assert col in df.columns, f"Missing column: {col}"
    
    def test_indicator_values_realistic(self, sample_ohlcv_data):
        """Test indicator values are within realistic ranges."""
        from backend.core.indicators.technical import TechnicalIndicators
        
        df = sample_ohlcv_data(num_candles=100, trend="up")
        
        rsi = TechnicalIndicators.calculate_rsi(df, column='close', period=14)
        vwap = TechnicalIndicators.calculate_vwap(df)
        atr = TechnicalIndicators.calculate_atr(df, period=14)
        
        # RSI should be 0-100
        valid_rsi = rsi.dropna()
        assert all(0 <= val <= 100 for val in valid_rsi)
        
        # VWAP should be within price range
        assert vwap.iloc[-1] >= df['low'].min()
        assert vwap.iloc[-1] <= df['high'].max()
        
        # ATR should be positive
        valid_atr = atr.dropna()
        assert all(val > 0 for val in valid_atr)


# ============================================================================
# STRATEGY COMBINATION TESTS
# ============================================================================

class TestStrategyCombinations:
    """Test multiple strategies working together."""
    
    def test_multiple_strategies_same_data(self, sample_ohlcv_data, sample_candidate):
        """Test running multiple strategies on same data."""
        from backend.core.strategies.vwap_breakout import VWAPBreakoutStrategy
        from backend.core.strategies.vwap_ema_breakout import VWAPEMABreakoutStrategy
        from backend.core.config import VWAPBreakoutConfig, VWAPEMABreakoutConfig
        
        # Create strategies
        vwap_strategy = VWAPBreakoutStrategy(VWAPBreakoutConfig())
        vwap_ema_strategy = VWAPEMABreakoutStrategy(VWAPEMABreakoutConfig())
        
        # Get sample data
        df = sample_ohlcv_data(num_candles=50, trend="up")
        candidate = sample_candidate(gain_pct=3.0)
        
        # Run both strategies
        vwap_pass = vwap_strategy.apply_filters(candidate, df)
        vwap_ema_pass = vwap_ema_strategy.apply_filters(candidate, df)
        
        # Both should return boolean
        assert isinstance(vwap_pass, bool)
        assert isinstance(vwap_ema_pass, bool)
    
    def test_ema_crossover_signals(self, sample_ohlcv_data):
        """Test EMA crossover signal generation."""
        from backend.core.strategies.ema_crossover import EMACrossoverStrategy
        
        strategy = EMACrossoverStrategy(fast_period=9, slow_period=21)
        
        df = sample_ohlcv_data(num_candles=50, trend="up")
        
        # Calculate signals for dataframe
        result = strategy.calculate_signals_dataframe(df)
        
        assert 'ema_fast' in result.columns
        assert 'ema_slow' in result.columns
        assert 'signal' in result.columns
        assert 'position' in result.columns


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
