"""
Unit Tests for Cache Implementations

Tests for RedisCache and InMemoryCache classes.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch

from backend.infrastructure.cache.redis_cache import RedisCache, InMemoryCache


class TestInMemoryCache:
    """Test InMemoryCache class."""
    
    @pytest.fixture
    def cache(self):
        """Create InMemoryCache instance."""
        return InMemoryCache()
    
    def test_cache_initialization(self, cache):
        """Test cache is initialized correctly."""
        assert cache is not None
        assert cache._cache == {}
    
    def test_set_and_get(self, cache):
        """Test set and get operations."""
        cache.set("test_key", "test_value")
        
        result = cache.get("test_key")
        
        assert result == "test_value"
    
    def test_get_nonexistent_key(self, cache):
        """Test get returns None for nonexistent key."""
        result = cache.get("nonexistent_key")
        
        assert result is None
    
    def test_set_with_ttl(self, cache):
        """Test set with TTL (TTL not implemented but should not error)."""
        cache.set("test_key", "test_value", ttl=60)
        
        # Value should still be retrievable
        result = cache.get("test_key")
        assert result == "test_value"
    
    def test_set_overwrite(self, cache):
        """Test setting same key overwrites value."""
        cache.set("test_key", "value1")
        cache.set("test_key", "value2")
        
        result = cache.get("test_key")
        
        assert result == "value2"
    
    def test_delete(self, cache):
        """Test delete operation."""
        cache.set("test_key", "test_value")
        cache.delete("test_key")
        
        result = cache.get("test_key")
        
        assert result is None
    
    def test_delete_nonexistent_key(self, cache):
        """Test delete nonexistent key does not raise."""
        # Should not raise
        cache.delete("nonexistent_key")
    
    def test_keys_with_prefix_pattern(self, cache):
        """Test keys method with prefix pattern."""
        cache.set("prefix:key1", "value1")
        cache.set("prefix:key2", "value2")
        cache.set("other:key3", "value3")
        
        result = cache.keys("prefix:*")
        
        assert "prefix:key1" in result
        assert "prefix:key2" in result
        assert "other:key3" not in result
        assert len(result) == 2
    
    def test_keys_exact_match(self, cache):
        """Test keys method with exact pattern."""
        cache.set("exact_key", "value1")
        cache.set("exact_key_extra", "value2")
        
        result = cache.keys("exact_key")
        
        assert result == ["exact_key"]
    
    def test_keys_no_match(self, cache):
        """Test keys method returns empty list when no match."""
        cache.set("key1", "value1")
        
        result = cache.keys("nonexistent:*")
        
        assert result == []
    
    def test_close(self, cache):
        """Test close method does not raise."""
        cache.set("key", "value")
        
        # Should not raise
        cache.close()
        
        # Cache should still work after close (in-memory)
        result = cache.get("key")
        assert result == "value"
    
    def test_multiple_operations(self, cache):
        """Test multiple cache operations in sequence."""
        # Set multiple keys
        cache.set("user:1", "alice")
        cache.set("user:2", "bob")
        cache.set("session:1", "sess_abc")
        
        # Verify all set
        assert cache.get("user:1") == "alice"
        assert cache.get("user:2") == "bob"
        assert cache.get("session:1") == "sess_abc"
        
        # Delete one
        cache.delete("user:1")
        
        # Verify deleted
        assert cache.get("user:1") is None
        assert cache.get("user:2") == "bob"
        
        # Get keys by pattern
        user_keys = cache.keys("user:*")
        assert len(user_keys) == 1
        assert "user:2" in user_keys


class TestRedisCache:
    """Test RedisCache class with mocked Redis."""
    
    @pytest.fixture
    def mock_redis(self):
        """Create mock Redis client."""
        mock = MagicMock()
        mock.get.return_value = b"test_value"
        mock.keys.return_value = [b"key1", b"key2"]
        return mock
    
    @pytest.fixture
    def cache(self, mock_redis):
        """Create RedisCache instance with mocked Redis."""
        with patch('backend.infrastructure.cache.redis_cache.redis.Redis') as MockRedis:
            MockRedis.from_url.return_value = mock_redis
            cache = RedisCache("redis://localhost:6379")
            return cache
    
    def test_cache_initialization(self, cache):
        """Test cache is initialized correctly."""
        assert cache is not None
        assert cache.redis_url == "redis://localhost:6379"
    
    def test_get_existing_key(self, cache, mock_redis):
        """Test get returns decoded value for existing key."""
        mock_redis.get.return_value = b"test_value"
        
        result = cache.get("test_key")
        
        mock_redis.get.assert_called_once_with("test_key")
        assert result == "test_value"
    
    def test_get_nonexistent_key(self, cache, mock_redis):
        """Test get returns None for nonexistent key."""
        mock_redis.get.return_value = None
        
        result = cache.get("nonexistent_key")
        
        assert result is None
    
    def test_set_without_ttl(self, cache, mock_redis):
        """Test set without TTL."""
        cache.set("test_key", "test_value")
        
        mock_redis.set.assert_called_once_with("test_key", "test_value")
    
    def test_set_with_ttl(self, cache, mock_redis):
        """Test set with TTL uses setex."""
        cache.set("test_key", "test_value", ttl=60)
        
        mock_redis.setex.assert_called_once_with("test_key", 60, "test_value")
    
    def test_delete(self, cache, mock_redis):
        """Test delete operation."""
        cache.delete("test_key")
        
        mock_redis.delete.assert_called_once_with("test_key")
    
    def test_keys(self, cache, mock_redis):
        """Test keys method returns decoded keys."""
        mock_redis.keys.return_value = [b"prefix:key1", b"prefix:key2"]
        
        result = cache.keys("prefix:*")
        
        mock_redis.keys.assert_called_once_with("prefix:*")
        assert result == ["prefix:key1", "prefix:key2"]
    
    def test_keys_empty(self, cache, mock_redis):
        """Test keys method returns empty list when no matches."""
        mock_redis.keys.return_value = []
        
        result = cache.keys("nonexistent:*")
        
        assert result == []
    
    def test_close(self, cache, mock_redis):
        """Test close calls Redis close."""
        cache.close()
        
        mock_redis.close.assert_called_once()


class TestRedisCacheConnection:
    """Test Redis connection handling."""
    
    def test_cache_creates_redis_connection(self):
        """Test cache creates Redis connection from URL."""
        with patch('backend.infrastructure.cache.redis_cache.redis.Redis') as MockRedis:
            mock_redis = MagicMock()
            MockRedis.from_url.return_value = mock_redis
            
            cache = RedisCache("redis://localhost:6379/0")
            
            MockRedis.from_url.assert_called_once_with("redis://localhost:6379/0")
    
    def test_cache_with_auth_url(self):
        """Test cache with authenticated Redis URL."""
        with patch('backend.infrastructure.cache.redis_cache.redis.Redis') as MockRedis:
            mock_redis = MagicMock()
            MockRedis.from_url.return_value = mock_redis
            
            cache = RedisCache("redis://user:password@localhost:6379/0")
            
            MockRedis.from_url.assert_called_once_with("redis://user:password@localhost:6379/0")


class TestCacheInterface:
    """Test cache interface compliance."""
    
    def test_inmemory_cache_implements_interface(self):
        """Test InMemoryCache implements ICache interface."""
        cache = InMemoryCache()
        
        # Check all required methods exist
        assert hasattr(cache, 'get')
        assert hasattr(cache, 'set')
        assert hasattr(cache, 'delete')
        assert hasattr(cache, 'keys')
        assert hasattr(cache, 'close')
        
        # Check methods are callable
        assert callable(cache.get)
        assert callable(cache.set)
        assert callable(cache.delete)
        assert callable(cache.keys)
        assert callable(cache.close)
    
    def test_redis_cache_implements_interface(self):
        """Test RedisCache implements ICache interface."""
        with patch('backend.infrastructure.cache.redis_cache.redis.Redis') as MockRedis:
            MockRedis.from_url.return_value = MagicMock()
            
            cache = RedisCache("redis://localhost:6379")
            
            # Check all required methods exist
            assert hasattr(cache, 'get')
            assert hasattr(cache, 'set')
            assert hasattr(cache, 'delete')
            assert hasattr(cache, 'keys')
            assert hasattr(cache, 'close')


class TestCacheEdgeCases:
    """Test edge cases for cache implementations."""
    
    def test_inmemory_cache_special_characters_in_key(self):
        """Test InMemoryCache handles special characters in key."""
        cache = InMemoryCache()
        
        # Test various special character keys
        cache.set("key:with:colons", "value1")
        cache.set("key/with/slashes", "value2")
        cache.set("key.with.dots", "value3")
        cache.set("key-with-dashes", "value4")
        
        assert cache.get("key:with:colons") == "value1"
        assert cache.get("key/with/slashes") == "value2"
        assert cache.get("key.with.dots") == "value3"
        assert cache.get("key-with-dashes") == "value4"
    
    def test_inmemory_cache_large_value(self):
        """Test InMemoryCache handles large values."""
        cache = InMemoryCache()
        
        large_value = "x" * 1000000  # 1MB string
        
        cache.set("large_key", large_value)
        result = cache.get("large_key")
        
        assert result == large_value
    
    def test_inmemory_cache_empty_string_value(self):
        """Test InMemoryCache handles empty string value."""
        cache = InMemoryCache()
        
        cache.set("empty_key", "")
        result = cache.get("empty_key")
        
        assert result == ""
    
    def test_inmemory_cache_unicode_value(self):
        """Test InMemoryCache handles unicode values."""
        cache = InMemoryCache()
        
        cache.set("unicode_key", "Hello 世界 🌍")
        result = cache.get("unicode_key")
        
        assert result == "Hello 世界 🌍"
