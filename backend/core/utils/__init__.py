"""Core utilities"""

from backend.core.utils.timezone import (
    IST,
    now_ist,
    today_ist,
    make_ist,
    to_utc,
    is_market_hours,
    is_trading_window,
    get_market_open_time,
    get_market_close_time,
    get_auto_exit_time,
    get_today_date_str,
    format_time_ist
)

from backend.core.utils.retry import (
    retry_async,
    retry_sync,
    with_retry,
    RetryError,
    NETWORK_ERRORS,
    AIOHTTP_ERRORS,
    KITE_API_ERRORS,
    is_kite_retryable
)

__all__ = [
    # Timezone
    'IST',
    'now_ist',
    'today_ist',
    'make_ist',
    'to_utc',
    'is_market_hours',
    'is_trading_window',
    'get_market_open_time',
    'get_market_close_time',
    'get_auto_exit_time',
    'get_today_date_str',
    'format_time_ist',
    # Retry
    'retry_async',
    'retry_sync',
    'with_retry',
    'RetryError',
    'NETWORK_ERRORS',
    'AIOHTTP_ERRORS',
    'KITE_API_ERRORS',
    'is_kite_retryable'
]
