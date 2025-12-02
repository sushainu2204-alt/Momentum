"""
Unit Tests for Core Utilities

Tests timezone utilities, retry mechanisms, and other core utilities.
"""

import pytest
import asyncio
from datetime import datetime, time, timedelta
from unittest.mock import patch, MagicMock
import pytz

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))


# ============================================================================
# TIMEZONE UTILITY TESTS
# ============================================================================

class TestTimezoneUtilities:
    """Test timezone utility functions."""
    
    def test_ist_timezone_exists(self):
        """Test IST timezone is properly defined."""
        from backend.core.utils.timezone import IST
        
        assert IST is not None
        assert str(IST) == "Asia/Kolkata"
    
    def test_now_ist_returns_timezone_aware(self):
        """Test now_ist returns timezone-aware datetime."""
        from backend.core.utils.timezone import now_ist, IST
        
        dt = now_ist()
        
        assert dt.tzinfo is not None
        # Compare zone names since pytz timezones don't compare equal directly
        assert str(dt.tzinfo.zone) == str(IST.zone) or str(dt.tzinfo) == str(IST)
    
    def test_today_ist_returns_midnight(self):
        """Test today_ist returns midnight IST."""
        from backend.core.utils.timezone import today_ist
        
        dt = today_ist()
        
        assert dt.hour == 0
        assert dt.minute == 0
        assert dt.second == 0
        assert dt.microsecond == 0
    
    def test_make_ist_with_naive_datetime(self):
        """Test make_ist localizes naive datetime to IST."""
        from backend.core.utils.timezone import make_ist, IST
        
        naive = datetime(2025, 12, 1, 10, 30, 0)
        ist_dt = make_ist(naive)
        
        # Compare zone names since pytz timezones don't compare equal directly
        assert hasattr(ist_dt.tzinfo, 'zone') and ist_dt.tzinfo.zone == 'Asia/Kolkata' or str(ist_dt.tzinfo) == str(IST)
        assert ist_dt.hour == 10
        assert ist_dt.minute == 30
    
    def test_make_ist_with_utc_datetime(self):
        """Test make_ist converts UTC to IST correctly."""
        from backend.core.utils.timezone import make_ist, IST
        
        utc_dt = datetime(2025, 12, 1, 5, 0, 0, tzinfo=pytz.UTC)  # 5:00 UTC = 10:30 IST
        ist_dt = make_ist(utc_dt)
        
        # Compare zone names since pytz timezones don't compare equal directly
        assert hasattr(ist_dt.tzinfo, 'zone') and ist_dt.tzinfo.zone == 'Asia/Kolkata' or str(ist_dt.tzinfo) == str(IST)
        assert ist_dt.hour == 10
        assert ist_dt.minute == 30
    
    def test_to_utc_conversion(self):
        """Test to_utc converts IST to UTC correctly."""
        from backend.core.utils.timezone import to_utc, IST
        
        ist_dt = IST.localize(datetime(2025, 12, 1, 10, 30, 0))  # 10:30 IST
        utc_dt = to_utc(ist_dt)
        
        assert utc_dt.tzinfo == pytz.UTC
        assert utc_dt.hour == 5
        assert utc_dt.minute == 0
    
    def test_get_market_open_time(self):
        """Test market open time is 9:15 AM."""
        from backend.core.utils.timezone import get_market_open_time
        
        market_open = get_market_open_time()
        
        assert market_open == time(9, 15)
    
    def test_get_market_close_time(self):
        """Test market close time is 3:30 PM."""
        from backend.core.utils.timezone import get_market_close_time
        
        market_close = get_market_close_time()
        
        assert market_close == time(15, 30)
    
    def test_get_auto_exit_time(self):
        """Test auto-exit time is 3:15 PM."""
        from backend.core.utils.timezone import get_auto_exit_time
        
        auto_exit = get_auto_exit_time()
        
        assert auto_exit == time(15, 15)
    
    def test_is_market_hours_during_trading(self, market_hours_datetime):
        """Test is_market_hours returns True during market hours."""
        from backend.core.utils.timezone import is_market_hours
        
        # Monday 10:30 AM IST
        if market_hours_datetime.weekday() < 5:
            assert is_market_hours(market_hours_datetime) is True
    
    def test_is_market_hours_before_open(self, before_market_datetime):
        """Test is_market_hours returns False before market open."""
        from backend.core.utils.timezone import is_market_hours
        
        assert is_market_hours(before_market_datetime) is False
    
    def test_is_market_hours_after_close(self, after_market_datetime):
        """Test is_market_hours returns False after market close."""
        from backend.core.utils.timezone import is_market_hours
        
        assert is_market_hours(after_market_datetime) is False
    
    def test_is_market_hours_weekend(self):
        """Test is_market_hours returns False on weekends."""
        from backend.core.utils.timezone import is_market_hours, IST
        
        # Find next Saturday
        dt = datetime.now(IST)
        days_until_saturday = (5 - dt.weekday()) % 7
        if days_until_saturday == 0:
            days_until_saturday = 7
        saturday = dt + timedelta(days=days_until_saturday)
        saturday = saturday.replace(hour=10, minute=30)
        
        assert is_market_hours(saturday) is False
    
    def test_is_trading_window_skips_first_minutes(self):
        """Test is_trading_window skips first N minutes."""
        from backend.core.utils.timezone import is_trading_window, IST
        
        # 9:20 AM - within skip window of 15 minutes
        dt = datetime.now(IST).replace(hour=9, minute=20, second=0)
        if dt.weekday() < 5:
            assert is_trading_window(dt, skip_first_minutes=15) is False
    
    def test_is_trading_window_during_valid_time(self):
        """Test is_trading_window returns True during valid trading time."""
        from backend.core.utils.timezone import is_trading_window, IST
        
        # 11:00 AM - valid trading window
        dt = datetime.now(IST).replace(hour=11, minute=0, second=0)
        if dt.weekday() < 5:
            assert is_trading_window(dt) is True
    
    def test_get_today_date_str_format(self):
        """Test get_today_date_str returns correctly formatted date."""
        from backend.core.utils.timezone import get_today_date_str, now_ist
        
        date_str = get_today_date_str()
        expected = now_ist().strftime("%Y-%m-%d")
        
        assert date_str == expected


# ============================================================================
# RETRY UTILITY TESTS
# ============================================================================

class TestRetryUtilities:
    """Test retry mechanisms."""
    
    @pytest.mark.asyncio
    async def test_retry_succeeds_first_try(self):
        """Test successful execution on first attempt."""
        from backend.core.utils.retry import retry_async
        
        call_count = 0
        
        async def success_func():
            nonlocal call_count
            call_count += 1
            return "success"
        
        result = await retry_async(success_func, max_retries=3)
        
        assert result == "success"
        assert call_count == 1
    
    @pytest.mark.asyncio
    async def test_retry_succeeds_after_failures(self):
        """Test successful execution after transient failures."""
        from backend.core.utils.retry import retry_async
        
        call_count = 0
        
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Transient failure")
            return "success"
        
        result = await retry_async(
            flaky_func, 
            max_retries=3, 
            base_delay=0.01  # Fast for testing
        )
        
        assert result == "success"
        assert call_count == 3
    
    @pytest.mark.asyncio
    async def test_retry_raises_after_max_attempts(self):
        """Test RetryError is raised after max attempts."""
        from backend.core.utils.retry import retry_async, RetryError
        
        async def always_fail():
            raise ValueError("Always fails")
        
        with pytest.raises(RetryError) as exc_info:
            await retry_async(
                always_fail, 
                max_retries=2, 
                base_delay=0.01,
                retryable_exceptions=(ValueError,)
            )
        
        assert "Failed after 3 attempts" in str(exc_info.value)
        assert exc_info.value.last_exception is not None
    
    @pytest.mark.asyncio
    async def test_retry_only_catches_specified_exceptions(self):
        """Test only specified exceptions trigger retry."""
        from backend.core.utils.retry import retry_async
        
        async def raise_type_error():
            raise TypeError("Not retryable")
        
        with pytest.raises(TypeError):
            await retry_async(
                raise_type_error,
                max_retries=3,
                retryable_exceptions=(ValueError,)  # Only ValueError is retryable
            )
    
    @pytest.mark.asyncio
    async def test_retry_calls_on_retry_callback(self):
        """Test on_retry callback is called on each retry."""
        from backend.core.utils.retry import retry_async
        
        retry_attempts = []
        
        def on_retry_callback(attempt, exception):
            retry_attempts.append((attempt, str(exception)))
        
        call_count = 0
        
        async def flaky_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError(f"Fail {call_count}")
            return "success"
        
        await retry_async(
            flaky_func,
            max_retries=3,
            base_delay=0.01,
            on_retry=on_retry_callback
        )
        
        assert len(retry_attempts) == 2
        assert retry_attempts[0][0] == 1
        assert retry_attempts[1][0] == 2
    
    @pytest.mark.asyncio
    async def test_with_retry_decorator(self):
        """Test with_retry decorator."""
        from backend.core.utils.retry import with_retry
        
        call_count = 0
        
        @with_retry(max_retries=2, base_delay=0.01)
        async def decorated_func():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ConnectionError("Transient")
            return "decorated success"
        
        result = await decorated_func()
        
        assert result == "decorated success"
        assert call_count == 2
    
    def test_is_kite_retryable_with_rate_limit(self):
        """Test is_kite_retryable detects rate limit errors."""
        from backend.core.utils.retry import is_kite_retryable
        
        rate_limit_error = Exception("Too many requests - rate limited")
        assert is_kite_retryable(rate_limit_error) is True
    
    def test_is_kite_retryable_with_timeout(self):
        """Test is_kite_retryable detects timeout errors."""
        from backend.core.utils.retry import is_kite_retryable
        
        timeout_error = Exception("Connection timeout occurred")
        assert is_kite_retryable(timeout_error) is True
    
    def test_is_kite_retryable_with_normal_error(self):
        """Test is_kite_retryable returns False for normal errors."""
        from backend.core.utils.retry import is_kite_retryable
        
        normal_error = Exception("Invalid order quantity")
        assert is_kite_retryable(normal_error) is False


# ============================================================================
# TECHNICAL INDICATORS TESTS
# ============================================================================

class TestTechnicalIndicators:
    """Test technical indicator calculations."""
    
    def test_calculate_ema(self, sample_ohlcv_data):
        """Test EMA calculation."""
        from backend.core.indicators.technical import TechnicalIndicators
        
        df = sample_ohlcv_data(num_candles=50)
        ema = TechnicalIndicators.calculate_ema(df, column='close', period=9)
        
        assert len(ema) == len(df)
        assert not ema.isnull().all()
        # EMA should be close to price
        assert abs(ema.iloc[-1] - df['close'].iloc[-1]) < df['close'].iloc[-1] * 0.1
    
    def test_calculate_sma(self, sample_ohlcv_data):
        """Test SMA calculation."""
        from backend.core.indicators.technical import TechnicalIndicators
        
        df = sample_ohlcv_data(num_candles=50)
        sma = TechnicalIndicators.calculate_sma(df, column='close', period=20)
        
        assert len(sma) == len(df)
        # First 19 values should be NaN
        assert sma.iloc[:19].isnull().all()
        assert not sma.iloc[19:].isnull().any()
    
    def test_calculate_rsi_range(self, sample_ohlcv_data):
        """Test RSI is within 0-100 range."""
        from backend.core.indicators.technical import TechnicalIndicators
        
        df = sample_ohlcv_data(num_candles=50)
        rsi = TechnicalIndicators.calculate_rsi(df, column='close', period=14)
        
        # Remove NaN values
        valid_rsi = rsi.dropna()
        
        assert all(0 <= val <= 100 for val in valid_rsi)
    
    def test_calculate_vwap(self, sample_ohlcv_data):
        """Test VWAP calculation."""
        from backend.core.indicators.technical import TechnicalIndicators
        
        df = sample_ohlcv_data(num_candles=50)
        vwap = TechnicalIndicators.calculate_vwap(df)
        
        assert len(vwap) == len(df)
        # VWAP should be within price range
        assert vwap.iloc[-1] >= df['low'].min()
        assert vwap.iloc[-1] <= df['high'].max()
    
    def test_calculate_volume_surge(self, sample_ohlcv_data):
        """Test volume surge detection."""
        from backend.core.indicators.technical import TechnicalIndicators
        
        df = sample_ohlcv_data(num_candles=50)
        # Add a volume spike at the end
        df.loc[df.index[-1], 'volume'] = df['volume'].mean() * 3
        
        surge = TechnicalIndicators.calculate_volume_surge(df, lookback=10, multiplier=2.0)
        
        assert surge.iloc[-1] == True  # Last candle has spike
    
    def test_calculate_atr(self, sample_ohlcv_data):
        """Test ATR calculation."""
        from backend.core.indicators.technical import TechnicalIndicators
        
        df = sample_ohlcv_data(num_candles=50)
        atr = TechnicalIndicators.calculate_atr(df, period=14)
        
        valid_atr = atr.dropna()
        
        # ATR should be positive
        assert all(val > 0 for val in valid_atr)
    
    def test_calculate_bollinger_bands(self, sample_ohlcv_data):
        """Test Bollinger Bands calculation."""
        from backend.core.indicators.technical import TechnicalIndicators
        
        df = sample_ohlcv_data(num_candles=50)
        upper, middle, lower = TechnicalIndicators.calculate_bollinger_bands(df, column='close', period=20)
        
        # Upper > Middle > Lower
        valid_idx = ~upper.isnull()
        assert all(upper[valid_idx] >= middle[valid_idx])
        assert all(middle[valid_idx] >= lower[valid_idx])
    
    def test_is_candle_break(self, sample_ohlcv_data):
        """Test candle breakout detection."""
        from backend.core.indicators.technical import TechnicalIndicators
        
        df = sample_ohlcv_data(num_candles=50, trend="up")
        is_break = TechnicalIndicators.is_candle_break(df, lookback=1)
        
        assert isinstance(is_break, pd.Series)
        assert len(is_break) == len(df)


# Import pandas for assertions
import pandas as pd


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
