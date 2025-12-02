"""
Timezone Utilities

Centralized timezone handling for IST (Indian Standard Time).
All trading operations should use IST for consistency with market hours.
"""

from datetime import datetime, time, timedelta
from typing import Optional
import pytz


# Indian Standard Time
IST = pytz.timezone('Asia/Kolkata')


def now_ist() -> datetime:
    """
    Get current datetime in IST timezone.
    
    Returns:
        Timezone-aware datetime in IST
    """
    return datetime.now(IST)


def today_ist() -> datetime:
    """
    Get today's date at midnight in IST.
    
    Returns:
        Timezone-aware datetime at midnight IST
    """
    return now_ist().replace(hour=0, minute=0, second=0, microsecond=0)


def make_ist(dt: datetime) -> datetime:
    """
    Convert a naive or UTC datetime to IST.
    
    Args:
        dt: Input datetime (naive or timezone-aware)
        
    Returns:
        Timezone-aware datetime in IST
    """
    if dt.tzinfo is None:
        # Assume naive datetime is in IST
        return IST.localize(dt)
    else:
        # Convert from other timezone to IST
        return dt.astimezone(IST)


def to_utc(dt: datetime) -> datetime:
    """
    Convert datetime to UTC.
    
    Args:
        dt: Input datetime (IST or naive)
        
    Returns:
        Timezone-aware datetime in UTC
    """
    if dt.tzinfo is None:
        # Assume naive datetime is in IST
        ist_dt = IST.localize(dt)
    else:
        ist_dt = dt
    
    return ist_dt.astimezone(pytz.UTC)


def get_market_open_time() -> time:
    """Get market open time (9:15 AM IST)"""
    return time(9, 15)


def get_market_close_time() -> time:
    """Get market close time (3:30 PM IST)"""
    return time(15, 30)


def get_auto_exit_time() -> time:
    """Get auto-exit time (3:15 PM IST - before Zerodha's 3:20 square-off)"""
    return time(15, 15)


def is_market_hours(dt: Optional[datetime] = None) -> bool:
    """
    Check if given time is during market hours.
    
    Args:
        dt: Datetime to check (defaults to now)
        
    Returns:
        True if during market hours (9:15 AM - 3:30 PM IST, Mon-Fri)
    """
    if dt is None:
        dt = now_ist()
    elif dt.tzinfo is None:
        dt = make_ist(dt)
    
    # Check weekday (Monday=0, Sunday=6)
    if dt.weekday() >= 5:
        return False
    
    current_time = dt.time()
    return get_market_open_time() <= current_time <= get_market_close_time()


def is_trading_window(dt: Optional[datetime] = None, skip_first_minutes: int = 15, skip_last_minutes: int = 15) -> bool:
    """
    Check if given time is in valid trading window.
    Skips first and last N minutes of market hours.
    
    Args:
        dt: Datetime to check (defaults to now)
        skip_first_minutes: Minutes to skip after market open
        skip_last_minutes: Minutes to skip before market close
        
    Returns:
        True if in valid trading window
    """
    if dt is None:
        dt = now_ist()
    elif dt.tzinfo is None:
        dt = make_ist(dt)
    
    # First check if market is open
    if not is_market_hours(dt):
        return False
    
    current_time = dt.time()
    
    # Calculate skip windows
    market_open = get_market_open_time()
    market_close = get_market_close_time()
    
    skip_until = time(
        market_open.hour,
        market_open.minute + skip_first_minutes
    )
    
    skip_from_hour = market_close.hour
    skip_from_minute = market_close.minute - skip_last_minutes
    if skip_from_minute < 0:
        skip_from_hour -= 1
        skip_from_minute += 60
    skip_from = time(skip_from_hour, skip_from_minute)
    
    return skip_until <= current_time <= skip_from


def get_today_date_str(fmt: str = "%Y-%m-%d") -> str:
    """
    Get today's date as string in IST.
    
    Args:
        fmt: Date format string
        
    Returns:
        Formatted date string
    """
    return now_ist().strftime(fmt)


def format_time_ist(dt: datetime, fmt: str = "%H:%M:%S") -> str:
    """
    Format datetime as time string in IST.
    
    Args:
        dt: Datetime to format
        fmt: Time format string
        
    Returns:
        Formatted time string
    """
    if dt.tzinfo is None:
        dt = make_ist(dt)
    return dt.strftime(fmt)
