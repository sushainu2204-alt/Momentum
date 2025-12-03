"""
Unit Tests for Timezone Utilities

Tests for IST timezone handling and market hours functions.
"""
import pytest
from datetime import datetime, time
from unittest.mock import patch, Mock
import pytz

from backend.core.utils.timezone import (
    IST,
    now_ist,
    today_ist,
    make_ist,
    to_utc,
    get_market_open_time,
    get_market_close_time,
    get_auto_exit_time,
    is_market_hours,
    is_trading_window,
    get_today_date_str,
    format_time_ist
)


class TestISTConstant:
    """Test IST timezone constant."""
    
    def test_ist_is_correct_timezone(self):
        """Test IST is Asia/Kolkata timezone."""
        assert str(IST) == "Asia/Kolkata"


class TestNowIST:
    """Test now_ist function."""
    
    def test_returns_timezone_aware_datetime(self):
        """Test returned datetime is timezone-aware."""
        result = now_ist()
        
        assert result.tzinfo is not None
        # Check timezone name instead of object equality (pytz comparison issue)
        assert str(result.tzinfo) == "Asia/Kolkata"
    
    def test_returns_current_time_approximately(self):
        """Test returned time is close to current time."""
        before = datetime.now(IST)
        result = now_ist()
        after = datetime.now(IST)
        
        assert before <= result <= after


class TestTodayIST:
    """Test today_ist function."""
    
    def test_returns_midnight(self):
        """Test returned datetime is at midnight."""
        result = today_ist()
        
        assert result.hour == 0
        assert result.minute == 0
        assert result.second == 0
        assert result.microsecond == 0
    
    def test_returns_timezone_aware(self):
        """Test returned datetime is timezone-aware."""
        result = today_ist()
        
        assert result.tzinfo is not None
        # Check timezone name instead of object equality (pytz comparison issue)
        assert str(result.tzinfo) == "Asia/Kolkata"
    
    def test_returns_today_date(self):
        """Test returned date is today."""
        result = today_ist()
        now = now_ist()
        
        assert result.date() == now.date()


class TestMakeIST:
    """Test make_ist function."""
    
    def test_naive_datetime_localized_to_ist(self):
        """Test naive datetime is assumed to be IST."""
        naive_dt = datetime(2024, 1, 15, 10, 30, 0)
        
        result = make_ist(naive_dt)
        
        # Check timezone name instead of object equality (pytz comparison issue)
        assert str(result.tzinfo) == "Asia/Kolkata"
        assert result.hour == 10
        assert result.minute == 30
    
    def test_utc_datetime_converted_to_ist(self):
        """Test UTC datetime is converted to IST."""
        utc_dt = datetime(2024, 1, 15, 10, 0, 0, tzinfo=pytz.UTC)
        
        result = make_ist(utc_dt)
        
        # Check timezone name instead of object equality (pytz comparison issue)
        assert str(result.tzinfo) == "Asia/Kolkata"
        # IST is UTC+5:30, so 10:00 UTC = 15:30 IST
        assert result.hour == 15
        assert result.minute == 30
    
    def test_already_ist_unchanged(self):
        """Test IST datetime remains unchanged."""
        ist_dt = IST.localize(datetime(2024, 1, 15, 10, 30, 0))
        
        result = make_ist(ist_dt)
        
        assert result == ist_dt


class TestToUTC:
    """Test to_utc function."""
    
    def test_naive_datetime_assumed_ist(self):
        """Test naive datetime is assumed to be IST."""
        naive_dt = datetime(2024, 1, 15, 15, 30, 0)  # 3:30 PM IST
        
        result = to_utc(naive_dt)
        
        assert result.tzinfo == pytz.UTC
        # IST is UTC+5:30, so 15:30 IST = 10:00 UTC
        assert result.hour == 10
        assert result.minute == 0
    
    def test_ist_datetime_converted_to_utc(self):
        """Test IST datetime is converted to UTC."""
        ist_dt = IST.localize(datetime(2024, 1, 15, 15, 30, 0))
        
        result = to_utc(ist_dt)
        
        assert result.tzinfo == pytz.UTC
        assert result.hour == 10
        assert result.minute == 0


class TestMarketTimeFunctions:
    """Test market time getter functions."""
    
    def test_get_market_open_time(self):
        """Test market open time is 9:15 AM."""
        result = get_market_open_time()
        
        assert result == time(9, 15)
    
    def test_get_market_close_time(self):
        """Test market close time is 3:30 PM."""
        result = get_market_close_time()
        
        assert result == time(15, 30)
    
    def test_get_auto_exit_time(self):
        """Test auto exit time is 3:15 PM."""
        result = get_auto_exit_time()
        
        assert result == time(15, 15)


class TestIsMarketHours:
    """Test is_market_hours function."""
    
    def test_during_market_hours_weekday(self):
        """Test returns True during market hours on weekday."""
        # Monday 10:00 AM IST
        dt = IST.localize(datetime(2024, 1, 15, 10, 0, 0))  # Monday
        
        result = is_market_hours(dt)
        
        assert result is True
    
    def test_before_market_open(self):
        """Test returns False before market opens."""
        dt = IST.localize(datetime(2024, 1, 15, 9, 0, 0))  # 9:00 AM, before 9:15
        
        result = is_market_hours(dt)
        
        assert result is False
    
    def test_after_market_close(self):
        """Test returns False after market closes."""
        dt = IST.localize(datetime(2024, 1, 15, 16, 0, 0))  # 4:00 PM
        
        result = is_market_hours(dt)
        
        assert result is False
    
    def test_weekend_saturday(self):
        """Test returns False on Saturday."""
        dt = IST.localize(datetime(2024, 1, 13, 10, 0, 0))  # Saturday
        
        result = is_market_hours(dt)
        
        assert result is False
    
    def test_weekend_sunday(self):
        """Test returns False on Sunday."""
        dt = IST.localize(datetime(2024, 1, 14, 10, 0, 0))  # Sunday
        
        result = is_market_hours(dt)
        
        assert result is False
    
    def test_exactly_at_market_open(self):
        """Test returns True exactly at market open."""
        dt = IST.localize(datetime(2024, 1, 15, 9, 15, 0))  # Monday 9:15 AM
        
        result = is_market_hours(dt)
        
        assert result is True
    
    def test_exactly_at_market_close(self):
        """Test returns True exactly at market close."""
        dt = IST.localize(datetime(2024, 1, 15, 15, 30, 0))  # Monday 3:30 PM
        
        result = is_market_hours(dt)
        
        assert result is True
    
    def test_uses_current_time_if_none(self):
        """Test uses current time if no argument provided."""
        with patch('backend.core.utils.timezone.now_ist') as mock_now:
            mock_now.return_value = IST.localize(datetime(2024, 1, 15, 10, 0, 0))
            
            result = is_market_hours()
            
            mock_now.assert_called_once()
    
    def test_naive_datetime_converted_to_ist(self):
        """Test naive datetime is converted to IST."""
        dt = datetime(2024, 1, 15, 10, 0, 0)  # Naive, Monday
        
        result = is_market_hours(dt)
        
        assert result is True


class TestIsTradingWindow:
    """Test is_trading_window function."""
    
    def test_within_trading_window(self):
        """Test returns True within valid trading window."""
        # Monday 10:00 AM (after 9:30, before 3:15)
        dt = IST.localize(datetime(2024, 1, 15, 10, 0, 0))
        
        result = is_trading_window(dt, skip_first_minutes=15, skip_last_minutes=15)
        
        assert result is True
    
    def test_too_early_skip_first_minutes(self):
        """Test returns False during skip_first_minutes period."""
        # Monday 9:20 AM (within first 15 minutes)
        dt = IST.localize(datetime(2024, 1, 15, 9, 20, 0))
        
        result = is_trading_window(dt, skip_first_minutes=15, skip_last_minutes=15)
        
        assert result is False
    
    def test_too_late_skip_last_minutes(self):
        """Test returns False during skip_last_minutes period."""
        # Monday 3:20 PM (within last 15 minutes)
        dt = IST.localize(datetime(2024, 1, 15, 15, 20, 0))
        
        result = is_trading_window(dt, skip_first_minutes=15, skip_last_minutes=15)
        
        assert result is False
    
    def test_outside_market_hours(self):
        """Test returns False outside market hours."""
        dt = IST.localize(datetime(2024, 1, 15, 8, 0, 0))  # Before market
        
        result = is_trading_window(dt)
        
        assert result is False
    
    def test_exactly_at_skip_boundary_start(self):
        """Test boundary condition at start of trading window."""
        # 9:15 + 15 min = 9:30
        dt = IST.localize(datetime(2024, 1, 15, 9, 30, 0))
        
        result = is_trading_window(dt, skip_first_minutes=15, skip_last_minutes=15)
        
        assert result is True
    
    def test_exactly_at_skip_boundary_end(self):
        """Test boundary condition at end of trading window."""
        # 15:30 - 15 min = 15:15
        dt = IST.localize(datetime(2024, 1, 15, 15, 15, 0))
        
        result = is_trading_window(dt, skip_first_minutes=15, skip_last_minutes=15)
        
        assert result is True


class TestGetTodayDateStr:
    """Test get_today_date_str function."""
    
    def test_default_format(self):
        """Test default date format."""
        with patch('backend.core.utils.timezone.now_ist') as mock_now:
            mock_now.return_value = IST.localize(datetime(2024, 1, 15, 10, 0, 0))
            
            result = get_today_date_str()
            
            assert result == "2024-01-15"
    
    def test_custom_format(self):
        """Test custom date format."""
        with patch('backend.core.utils.timezone.now_ist') as mock_now:
            mock_now.return_value = IST.localize(datetime(2024, 1, 15, 10, 0, 0))
            
            result = get_today_date_str("%d/%m/%Y")
            
            assert result == "15/01/2024"


class TestFormatTimeIST:
    """Test format_time_ist function."""
    
    def test_default_format(self):
        """Test default time format."""
        dt = IST.localize(datetime(2024, 1, 15, 10, 30, 45))
        
        result = format_time_ist(dt)
        
        assert result == "10:30:45"
    
    def test_custom_format(self):
        """Test custom time format."""
        dt = IST.localize(datetime(2024, 1, 15, 10, 30, 45))
        
        result = format_time_ist(dt, "%H:%M")
        
        assert result == "10:30"
    
    def test_naive_datetime_converted_to_ist(self):
        """Test naive datetime is converted to IST."""
        dt = datetime(2024, 1, 15, 10, 30, 45)
        
        result = format_time_ist(dt)
        
        assert result == "10:30:45"
