"""
Retry Utilities

Provides exponential backoff retry mechanisms for API calls.
Critical for trading systems to handle transient failures gracefully.
"""

import asyncio
import logging
from functools import wraps
from typing import TypeVar, Callable, Optional, Tuple, Type
import random

logger = logging.getLogger(__name__)

T = TypeVar('T')


class RetryError(Exception):
    """Raised when all retry attempts fail"""
    def __init__(self, message: str, last_exception: Optional[Exception] = None):
        super().__init__(message)
        self.last_exception = last_exception


async def retry_async(
    func: Callable[..., T],
    *args,
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    exponential_base: float = 2.0,
    jitter: bool = True,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,),
    on_retry: Optional[Callable[[int, Exception], None]] = None,
    **kwargs
) -> T:
    """
    Execute an async function with exponential backoff retry.
    
    Args:
        func: Async function to execute
        *args: Positional arguments for func
        max_retries: Maximum number of retry attempts
        base_delay: Initial delay in seconds
        max_delay: Maximum delay cap in seconds
        exponential_base: Base for exponential backoff
        jitter: Add random jitter to prevent thundering herd
        retryable_exceptions: Tuple of exceptions that trigger retry
        on_retry: Optional callback called on each retry (attempt, exception)
        **kwargs: Keyword arguments for func
        
    Returns:
        Result from successful function call
        
    Raises:
        RetryError: If all retries fail
    """
    last_exception = None
    
    for attempt in range(max_retries + 1):
        try:
            return await func(*args, **kwargs)
        except retryable_exceptions as e:
            last_exception = e
            
            if attempt >= max_retries:
                break
            
            # Calculate delay with exponential backoff
            delay = min(base_delay * (exponential_base ** attempt), max_delay)
            
            # Add jitter (up to 25% of delay)
            if jitter:
                delay = delay * (1 + random.uniform(-0.25, 0.25))
            
            logger.warning(
                f"Attempt {attempt + 1}/{max_retries + 1} failed: {e}. "
                f"Retrying in {delay:.2f}s..."
            )
            
            if on_retry:
                on_retry(attempt + 1, e)
            
            await asyncio.sleep(delay)
    
    raise RetryError(
        f"Failed after {max_retries + 1} attempts",
        last_exception=last_exception
    )


def with_retry(
    max_retries: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    retryable_exceptions: Tuple[Type[Exception], ...] = (Exception,)
):
    """
    Decorator for async functions to add retry logic.
    
    Usage:
        @with_retry(max_retries=3, base_delay=1.0)
        async def fetch_data():
            ...
    """
    def decorator(func: Callable[..., T]) -> Callable[..., T]:
        @wraps(func)
        async def wrapper(*args, **kwargs) -> T:
            return await retry_async(
                func, *args,
                max_retries=max_retries,
                base_delay=base_delay,
                max_delay=max_delay,
                retryable_exceptions=retryable_exceptions,
                **kwargs
            )
        return wrapper
    return decorator


# Common exception groups for different APIs
NETWORK_ERRORS = (
    ConnectionError,
    TimeoutError,
    asyncio.TimeoutError,
)

try:
    import aiohttp
    AIOHTTP_ERRORS = (
        aiohttp.ClientError,
        aiohttp.ClientConnectionError,
        asyncio.TimeoutError,
    )
except ImportError:
    AIOHTTP_ERRORS = NETWORK_ERRORS


# Kite-specific retryable errors (rate limits, transient failures)
KITE_RETRYABLE_MESSAGES = [
    "Too many requests",
    "Network is unreachable",
    "Connection reset",
    "Timeout",
]


def is_kite_retryable(exception: Exception) -> bool:
    """Check if a Kite API error is retryable"""
    error_msg = str(exception).lower()
    return any(msg.lower() in error_msg for msg in KITE_RETRYABLE_MESSAGES)
