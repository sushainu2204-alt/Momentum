"""
Unit Tests for Retry Utilities

Tests for retry_async, retry_sync, with_retry decorator,
and helper functions.
"""
import pytest
import asyncio
import time
from unittest.mock import Mock, AsyncMock, patch, call

from backend.core.utils.retry import (
    RetryError,
    retry_async,
    retry_sync,
    with_retry,
    NETWORK_ERRORS,
    KITE_API_ERRORS,
    KITE_RETRYABLE_MESSAGES,
    is_kite_retryable
)


class TestRetryError:
    """Test RetryError exception class."""
    
    def test_error_message(self):
        """Test error message is stored correctly."""
        error = RetryError("Test error")
        
        assert str(error) == "Test error"
        assert error.last_exception is None
    
    def test_error_with_last_exception(self):
        """Test error with last exception attached."""
        original = ValueError("Original error")
        error = RetryError("Failed after retries", last_exception=original)
        
        assert error.last_exception is original
        assert "Failed after retries" in str(error)


class TestRetryAsync:
    """Test retry_async function."""
    
    @pytest.mark.asyncio
    async def test_success_on_first_attempt(self):
        """Test function succeeds on first attempt."""
        mock_func = AsyncMock(return_value="success")
        
        result = await retry_async(mock_func, max_retries=3)
        
        assert result == "success"
        assert mock_func.call_count == 1
    
    @pytest.mark.asyncio
    async def test_success_after_retry(self):
        """Test function succeeds after initial failure."""
        mock_func = AsyncMock(side_effect=[ValueError("fail"), "success"])
        
        with patch('backend.core.utils.retry.asyncio.sleep', new_callable=AsyncMock):
            result = await retry_async(
                mock_func,
                max_retries=3,
                base_delay=0.01,
                retryable_exceptions=(ValueError,)
            )
        
        assert result == "success"
        assert mock_func.call_count == 2
    
    @pytest.mark.asyncio
    async def test_exhausts_all_retries(self):
        """Test error raised after all retries exhausted."""
        mock_func = AsyncMock(side_effect=ValueError("always fails"))
        
        with patch('backend.core.utils.retry.asyncio.sleep', new_callable=AsyncMock):
            with pytest.raises(RetryError) as exc_info:
                await retry_async(
                    mock_func,
                    max_retries=2,
                    base_delay=0.01,
                    retryable_exceptions=(ValueError,)
                )
        
        assert mock_func.call_count == 3  # Initial + 2 retries
        assert "Failed after 3 attempts" in str(exc_info.value)
        assert isinstance(exc_info.value.last_exception, ValueError)
    
    @pytest.mark.asyncio
    async def test_non_retryable_exception_raises_immediately(self):
        """Test non-retryable exceptions are raised directly (not wrapped in RetryError)."""
        mock_func = AsyncMock(side_effect=KeyError("not retryable"))
        
        # When the exception is not retryable, it should be raised directly
        with pytest.raises(KeyError):
            await retry_async(
                mock_func,
                max_retries=3,
                retryable_exceptions=(ValueError,)  # KeyError not included
            )
        
        assert mock_func.call_count == 1
    
    @pytest.mark.asyncio
    async def test_on_retry_callback(self):
        """Test on_retry callback is called on each retry."""
        expected_exception = ValueError("fail")
        mock_func = AsyncMock(side_effect=[expected_exception, ValueError("fail2"), "success"])
        callback = Mock()
        
        with patch('backend.core.utils.retry.asyncio.sleep', new_callable=AsyncMock):
            result = await retry_async(
                mock_func,
                max_retries=3,
                base_delay=0.01,
                retryable_exceptions=(ValueError,),
                on_retry=callback
            )
        
        assert result == "success"
        assert callback.call_count == 2
        # Check callback was called with attempt number and exception
        assert callback.call_args_list[0][0][0] == 1  # First retry attempt
    
    @pytest.mark.asyncio
    async def test_exponential_backoff(self):
        """Test delay increases exponentially."""
        mock_func = AsyncMock(side_effect=[ValueError("fail")] * 3 + ["success"])
        sleep_calls = []
        
        async def capture_sleep(delay):
            sleep_calls.append(delay)
        
        with patch('backend.core.utils.retry.asyncio.sleep', side_effect=capture_sleep):
            with patch('backend.core.utils.retry.random.uniform', return_value=0):
                await retry_async(
                    mock_func,
                    max_retries=3,
                    base_delay=1.0,
                    exponential_base=2.0,
                    jitter=False,
                    retryable_exceptions=(ValueError,)
                )
        
        assert len(sleep_calls) == 3
        assert sleep_calls[0] == 1.0  # 1 * 2^0
        assert sleep_calls[1] == 2.0  # 1 * 2^1
        assert sleep_calls[2] == 4.0  # 1 * 2^2
    
    @pytest.mark.asyncio
    async def test_max_delay_cap(self):
        """Test delay is capped at max_delay."""
        mock_func = AsyncMock(side_effect=[ValueError("fail")] * 5 + ["success"])
        sleep_calls = []
        
        async def capture_sleep(delay):
            sleep_calls.append(delay)
        
        with patch('backend.core.utils.retry.asyncio.sleep', side_effect=capture_sleep):
            with patch('backend.core.utils.retry.random.uniform', return_value=0):
                await retry_async(
                    mock_func,
                    max_retries=5,
                    base_delay=1.0,
                    max_delay=5.0,
                    jitter=False,
                    retryable_exceptions=(ValueError,)
                )
        
        # All delays should be capped at 5.0
        assert all(d <= 5.0 for d in sleep_calls)
    
    @pytest.mark.asyncio
    async def test_passes_args_and_kwargs(self):
        """Test function receives correct arguments."""
        mock_func = AsyncMock(return_value="result")
        
        result = await retry_async(mock_func, "arg1", "arg2", kwarg1="value1")
        
        mock_func.assert_called_once_with("arg1", "arg2", kwarg1="value1")
        assert result == "result"


class TestRetrySync:
    """Test retry_sync function."""
    
    def test_success_on_first_attempt(self):
        """Test function succeeds on first attempt."""
        mock_func = Mock(return_value="success")
        
        result = retry_sync(mock_func, max_retries=3)
        
        assert result == "success"
        assert mock_func.call_count == 1
    
    def test_success_after_retry(self):
        """Test function succeeds after initial failure."""
        mock_func = Mock(side_effect=[ValueError("fail"), "success"])
        
        with patch('time.sleep'):
            result = retry_sync(
                mock_func,
                max_retries=3,
                base_delay=0.01,
                retryable_exceptions=(ValueError,)
            )
        
        assert result == "success"
        assert mock_func.call_count == 2
    
    def test_exhausts_all_retries(self):
        """Test error raised after all retries exhausted."""
        mock_func = Mock(side_effect=ValueError("always fails"))
        
        with patch('time.sleep'):
            with pytest.raises(RetryError) as exc_info:
                retry_sync(
                    mock_func,
                    max_retries=2,
                    base_delay=0.01,
                    retryable_exceptions=(ValueError,)
                )
        
        assert mock_func.call_count == 3
        assert isinstance(exc_info.value.last_exception, ValueError)
    
    def test_on_retry_callback(self):
        """Test on_retry callback is called on each retry."""
        mock_func = Mock(side_effect=[ValueError("fail"), "success"])
        callback = Mock()
        
        with patch('time.sleep'):
            result = retry_sync(
                mock_func,
                max_retries=3,
                base_delay=0.01,
                retryable_exceptions=(ValueError,),
                on_retry=callback
            )
        
        assert result == "success"
        callback.assert_called_once()
    
    def test_passes_args_and_kwargs(self):
        """Test function receives correct arguments."""
        mock_func = Mock(return_value="result")
        
        result = retry_sync(mock_func, "arg1", "arg2", kwarg1="value1")
        
        mock_func.assert_called_once_with("arg1", "arg2", kwarg1="value1")
        assert result == "result"


class TestWithRetryDecorator:
    """Test with_retry decorator."""
    
    @pytest.mark.asyncio
    async def test_decorated_function_retries(self):
        """Test decorated function has retry behavior."""
        call_count = 0
        
        @with_retry(max_retries=2, base_delay=0.01, retryable_exceptions=(ValueError,))
        async def flaky_function():
            nonlocal call_count
            call_count += 1
            if call_count < 2:
                raise ValueError("Temporary failure")
            return "success"
        
        with patch('backend.core.utils.retry.asyncio.sleep', new_callable=AsyncMock):
            result = await flaky_function()
        
        assert result == "success"
        assert call_count == 2
    
    @pytest.mark.asyncio
    async def test_decorated_function_raises_after_exhausted_retries(self):
        """Test decorated function raises RetryError after exhausting retries."""
        @with_retry(max_retries=1, base_delay=0.01, retryable_exceptions=(ValueError,))
        async def always_fails():
            raise ValueError("Always fails")
        
        with patch('backend.core.utils.retry.asyncio.sleep', new_callable=AsyncMock):
            with pytest.raises(RetryError):
                await always_fails()


class TestIsKiteRetryable:
    """Test is_kite_retryable helper function."""
    
    def test_retryable_too_many_requests(self):
        """Test 'Too many requests' error is retryable."""
        error = Exception("Too many requests - rate limit exceeded")
        
        assert is_kite_retryable(error) is True
    
    def test_retryable_network_unreachable(self):
        """Test 'Network is unreachable' error is retryable."""
        error = Exception("Network is unreachable")
        
        assert is_kite_retryable(error) is True
    
    def test_retryable_connection_reset(self):
        """Test 'Connection reset' error is retryable."""
        error = Exception("Connection reset by peer")
        
        assert is_kite_retryable(error) is True
    
    def test_retryable_timeout(self):
        """Test 'Timeout' error is retryable."""
        error = Exception("Request timeout")
        
        assert is_kite_retryable(error) is True
    
    def test_not_retryable_other_error(self):
        """Test other errors are not retryable."""
        error = Exception("Invalid API key")
        
        assert is_kite_retryable(error) is False
    
    def test_case_insensitive_matching(self):
        """Test error message matching is case insensitive."""
        error = Exception("TIMEOUT occurred")
        
        assert is_kite_retryable(error) is True


class TestExceptionGroups:
    """Test exception group constants."""
    
    def test_network_errors_contains_expected(self):
        """Test NETWORK_ERRORS contains expected exceptions."""
        assert ConnectionError in NETWORK_ERRORS
        assert TimeoutError in NETWORK_ERRORS
        assert asyncio.TimeoutError in NETWORK_ERRORS
    
    def test_kite_api_errors_contains_network(self):
        """Test KITE_API_ERRORS includes network errors."""
        for error_type in NETWORK_ERRORS:
            assert error_type in KITE_API_ERRORS
    
    def test_kite_retryable_messages(self):
        """Test KITE_RETRYABLE_MESSAGES list."""
        expected = ["Too many requests", "Network is unreachable", "Connection reset", "Timeout"]
        
        for msg in expected:
            assert msg in KITE_RETRYABLE_MESSAGES
