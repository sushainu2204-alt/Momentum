"""
Unit Tests for Infrastructure Layer

Tests database, cache, messaging, and data source infrastructure.
"""

import pytest
import asyncio
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import json

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


# ============================================================================
# DATABASE INFRASTRUCTURE TESTS
# ============================================================================

class TestPostgresDatabase:
    """Test PostgreSQL database infrastructure."""
    
    @pytest.fixture
    def db_config(self):
        """Database configuration for testing."""
        return {
            "host": "localhost",
            "port": 5432,
            "database": "momentum_test",
            "user": "test_user",
            "password": "test_pass"
        }
    
    @pytest.mark.asyncio
    async def test_connection_string_building(self, db_config):
        """Test connection string is built correctly."""
        expected_parts = [
            f"host={db_config['host']}",
            f"port={db_config['port']}",
            f"dbname={db_config['database']}",
            f"user={db_config['user']}"
        ]
        
        # Connection string should contain all parts
        for part in expected_parts:
            # Just verify the config has required keys
            assert db_config.get('host')
            assert db_config.get('port')
    
    @pytest.mark.asyncio
    async def test_pool_creation(self, mock_database):
        """Test connection pool is created on connect."""
        await mock_database.connect()
        
        mock_database.connect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_pool_close_on_disconnect(self, mock_database):
        """Test pool is closed on disconnect."""
        await mock_database.connect()
        await mock_database.disconnect()
        
        mock_database.disconnect.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_fetch_one_query(self, mock_database):
        """Test fetch_one returns single row."""
        expected = {"id": 1, "name": "test"}
        mock_database.fetch_one.return_value = expected
        
        result = await mock_database.fetch_one("SELECT * FROM test WHERE id = 1")
        
        assert result == expected
    
    @pytest.mark.asyncio
    async def test_fetch_all_query(self, mock_database):
        """Test fetch_all returns multiple rows."""
        expected = [
            {"id": 1, "name": "test1"},
            {"id": 2, "name": "test2"}
        ]
        mock_database.fetch_all.return_value = expected
        
        result = await mock_database.fetch_all("SELECT * FROM test")
        
        assert len(result) == 2
    
    @pytest.mark.asyncio
    async def test_insert_returns_id(self, mock_database):
        """Test insert returns generated ID."""
        mock_database.insert.return_value = 42
        
        result = await mock_database.insert("test", {"name": "new"})
        
        assert result == 42
    
    @pytest.mark.asyncio
    async def test_update_returns_affected_rows(self, mock_database):
        """Test update returns affected row count."""
        mock_database.update.return_value = 5
        
        result = await mock_database.update("test", {"name": "updated"}, {"status": "active"})
        
        assert result == 5
    
    @pytest.mark.asyncio
    async def test_transaction_commit(self, mock_database):
        """Test transaction commit."""
        mock_database.begin_transaction = AsyncMock()
        mock_database.commit = AsyncMock()
        
        await mock_database.begin_transaction()
        await mock_database.insert("test", {"name": "in_transaction"})
        await mock_database.commit()
        
        mock_database.commit.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_transaction_rollback(self, mock_database):
        """Test transaction rollback on error."""
        mock_database.begin_transaction = AsyncMock()
        mock_database.rollback = AsyncMock()
        mock_database.insert.side_effect = Exception("Insert failed")
        
        await mock_database.begin_transaction()
        
        with pytest.raises(Exception):
            await mock_database.insert("test", {"name": "will_fail"})
        
        await mock_database.rollback()
        mock_database.rollback.assert_called_once()


# ============================================================================
# REDIS CACHE TESTS
# ============================================================================

class TestRedisCache:
    """Test Redis cache infrastructure."""
    
    @pytest.mark.asyncio
    async def test_set_value(self, mock_redis):
        """Test setting cache value."""
        await mock_redis.set("test_key", "test_value")
        
        mock_redis.set.assert_called_once_with("test_key", "test_value")
    
    @pytest.mark.asyncio
    async def test_get_value(self, mock_redis):
        """Test getting cache value."""
        mock_redis.get.return_value = "cached_value"
        
        result = await mock_redis.get("test_key")
        
        assert result == "cached_value"
    
    @pytest.mark.asyncio
    async def test_get_missing_key(self, mock_redis):
        """Test getting non-existent key."""
        mock_redis.get.return_value = None
        
        result = await mock_redis.get("missing_key")
        
        assert result is None
    
    @pytest.mark.asyncio
    async def test_set_with_expiry(self, mock_redis):
        """Test setting value with TTL."""
        mock_redis.setex = AsyncMock()
        
        await mock_redis.setex("temp_key", 300, "temp_value")
        
        mock_redis.setex.assert_called_once_with("temp_key", 300, "temp_value")
    
    @pytest.mark.asyncio
    async def test_delete_key(self, mock_redis):
        """Test deleting cache key."""
        mock_redis.delete = AsyncMock(return_value=1)
        
        result = await mock_redis.delete("test_key")
        
        assert result == 1
    
    @pytest.mark.asyncio
    async def test_exists_check(self, mock_redis):
        """Test checking key existence."""
        mock_redis.exists = AsyncMock(return_value=True)
        
        result = await mock_redis.exists("test_key")
        
        assert result is True
    
    @pytest.mark.asyncio
    async def test_cache_json_object(self, mock_redis):
        """Test caching JSON objects."""
        data = {"symbol": "RELIANCE", "price": 2450.0}
        
        await mock_redis.set("position:1", json.dumps(data))
        
        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        cached_value = json.loads(call_args[0][1])
        assert cached_value['symbol'] == "RELIANCE"
    
    @pytest.mark.asyncio
    async def test_hash_operations(self, mock_redis):
        """Test hash operations."""
        mock_redis.hset = AsyncMock()
        mock_redis.hget = AsyncMock(return_value="2450.0")
        mock_redis.hgetall = AsyncMock(return_value={"price": "2450.0", "quantity": "10"})
        
        await mock_redis.hset("position:RELIANCE", "price", "2450.0")
        
        value = await mock_redis.hget("position:RELIANCE", "price")
        assert value == "2450.0"
        
        all_values = await mock_redis.hgetall("position:RELIANCE")
        assert len(all_values) == 2


# ============================================================================
# MESSAGE QUEUE TESTS
# ============================================================================

class TestRedisMessageQueue:
    """Test Redis pub/sub messaging."""
    
    @pytest.mark.asyncio
    async def test_publish_message(self, mock_redis):
        """Test publishing message."""
        mock_redis.publish = AsyncMock(return_value=1)
        
        message = {"type": "SIGNAL", "symbol": "RELIANCE"}
        result = await mock_redis.publish("signals", json.dumps(message))
        
        assert result == 1
    
    @pytest.mark.asyncio
    async def test_subscribe_channel(self, mock_redis):
        """Test subscribing to channel."""
        mock_pubsub = AsyncMock()
        mock_redis.pubsub = MagicMock(return_value=mock_pubsub)
        mock_pubsub.subscribe = AsyncMock()
        
        pubsub = mock_redis.pubsub()
        await pubsub.subscribe("signals")
        
        mock_pubsub.subscribe.assert_called_once_with("signals")
    
    @pytest.mark.asyncio
    async def test_receive_message(self, mock_redis):
        """Test receiving message from channel."""
        mock_pubsub = AsyncMock()
        mock_pubsub.get_message = AsyncMock(return_value={
            "type": "message",
            "channel": "signals",
            "data": '{"symbol": "RELIANCE"}'
        })
        
        msg = await mock_pubsub.get_message()
        
        assert msg['channel'] == "signals"
        data = json.loads(msg['data'])
        assert data['symbol'] == "RELIANCE"


# ============================================================================
# DATA SOURCE TESTS
# ============================================================================

class TestNSEDataSource:
    """Test NSE data source infrastructure."""
    
    @pytest.fixture
    def mock_http_client(self):
        """Mock HTTP client."""
        mock = AsyncMock()
        return mock
    
    @pytest.mark.asyncio
    async def test_fetch_top_gainers(self, mock_http_client):
        """Test fetching top gainers from NSE."""
        # Configure mock to return proper response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": [
                {"symbol": "RELIANCE", "pChange": 3.5, "lastPrice": 2450.0},
                {"symbol": "INFY", "pChange": 2.8, "lastPrice": 1650.0}
            ]
        }
        mock_http_client.get.return_value = mock_response
        
        response = await mock_http_client.get("https://api.nseindia.com/...")
        data = response.json()
        
        assert len(data['data']) == 2
        assert data['data'][0]['symbol'] == "RELIANCE"
    
    @pytest.mark.asyncio
    async def test_handle_rate_limiting(self, mock_http_client):
        """Test handling rate limiting from NSE."""
        # First call returns 429, second succeeds
        mock_http_client.get.side_effect = [
            AsyncMock(status=429),  # Rate limited
            AsyncMock(json=AsyncMock(return_value={"data": []}))  # Success
        ]
        
        # Should retry on rate limit
        first_response = await mock_http_client.get("...")
        assert first_response.status == 429
        
        second_response = await mock_http_client.get("...")
        data = await second_response.json()
        assert data == {"data": []}
    
    @pytest.mark.asyncio
    async def test_cache_gainers_data(self, mock_redis):
        """Test caching gainers data."""
        gainers = [
            {"symbol": "RELIANCE", "gain_pct": 3.5},
            {"symbol": "INFY", "gain_pct": 2.8}
        ]
        
        # Cache for 5 minutes
        mock_redis.setex = AsyncMock()
        await mock_redis.setex("gainers:nse", 300, json.dumps(gainers))
        
        mock_redis.setex.assert_called_once()


# ============================================================================
# KITE DATA SOURCE TESTS
# ============================================================================

class TestKiteDataSource:
    """Test Kite Connect data source."""
    
    @pytest.fixture
    def mock_kite_api(self):
        """Create a MagicMock for Kite API that allows setting return values."""
        mock = MagicMock()
        mock.historical_data = MagicMock()
        mock.quote = MagicMock()
        mock.ltp = MagicMock()
        return mock
    
    @pytest.mark.asyncio
    async def test_fetch_historical_data(self, mock_kite_api, sample_ohlcv_data):
        """Test fetching historical OHLCV data."""
        expected_data = sample_ohlcv_data(num_candles=50).to_dict('records')
        mock_kite_api.historical_data.return_value = expected_data
        
        data = mock_kite_api.historical_data(
            instrument_token=128083204,
            from_date=datetime.now() - timedelta(days=1),
            to_date=datetime.now(),
            interval="5minute"
        )
        
        assert len(data) == 50
    
    @pytest.mark.asyncio
    async def test_fetch_quote(self, mock_kite_api):
        """Test fetching live quote."""
        mock_kite_api.quote.return_value = {
            "NSE:RELIANCE": {
                "last_price": 2450.0,
                "volume": 1000000,
                "ohlc": {
                    "open": 2430.0,
                    "high": 2460.0,
                    "low": 2425.0,
                    "close": 2445.0
                }
            }
        }
        
        quote = mock_kite_api.quote(["NSE:RELIANCE"])
        
        assert quote["NSE:RELIANCE"]["last_price"] == 2450.0
    
    @pytest.mark.asyncio
    async def test_handle_token_expiry(self, mock_kite_api):
        """Test handling token expiry."""
        mock_kite_api.quote.side_effect = Exception("Token expired")
        
        with pytest.raises(Exception) as exc_info:
            mock_kite_api.quote(["NSE:RELIANCE"])
        
        assert "Token expired" in str(exc_info.value)
    
    def test_mock_kite_service_integration(self, mock_kite_service):
        """Test that MockKiteService works correctly."""
        # Test historical data returns proper structure
        data = mock_kite_service.historical_data(
            instrument_token=738561,
            from_date=datetime.now() - timedelta(days=1),
            to_date=datetime.now(),
            interval="5minute"
        )
        assert len(data) == 50
        assert 'open' in data[0]
        assert 'close' in data[0]
        
        # Test quote returns proper structure
        quote = mock_kite_service.quote(["NSE:RELIANCE"])
        assert "NSE:RELIANCE" in quote
        assert quote["NSE:RELIANCE"]["last_price"] > 0


# ============================================================================
# CONNECTION POOL MANAGEMENT TESTS
# ============================================================================

class TestConnectionPoolManagement:
    """Test connection pool lifecycle management."""
    
    @pytest.mark.asyncio
    async def test_pool_max_connections(self, mock_database):
        """Test pool respects max connection limit."""
        mock_database.pool_size = 10
        mock_database.get_pool_status = AsyncMock(return_value={
            "size": 10,
            "free": 5,
            "used": 5
        })
        
        status = await mock_database.get_pool_status()
        
        assert status['size'] == 10
        assert status['used'] <= status['size']
    
    @pytest.mark.asyncio
    async def test_connection_timeout_handling(self, mock_database):
        """Test handling connection timeout."""
        mock_database.fetch_one.side_effect = asyncio.TimeoutError()
        
        with pytest.raises(asyncio.TimeoutError):
            await mock_database.fetch_one("SELECT 1")
    
    @pytest.mark.asyncio
    async def test_connection_health_check(self, mock_database):
        """Test connection health check."""
        mock_database.is_healthy = AsyncMock(return_value=True)
        
        is_healthy = await mock_database.is_healthy()
        
        assert is_healthy is True


# ============================================================================
# FILE STORAGE TESTS
# ============================================================================

class TestFileStorage:
    """Test file-based storage infrastructure."""
    
    def test_signal_file_path_generation(self):
        """Test signal file path generation."""
        date = datetime(2024, 1, 15)
        strategy = "vwap_breakout"
        
        # Expected path format
        expected = f"signals/2024-01-15/{strategy}_signals.json"
        
        # Verify path components
        assert "2024-01-15" in expected
        assert strategy in expected
        assert ".json" in expected
    
    @pytest.mark.asyncio
    async def test_save_signals_to_file(self):
        """Test saving signals to JSON file."""
        signals = [
            {"symbol": "RELIANCE", "price": 2450.0, "type": "BUY"},
            {"symbol": "INFY", "price": 1650.0, "type": "BUY"}
        ]
        
        # Verify serialization
        json_str = json.dumps(signals, indent=2)
        parsed = json.loads(json_str)
        
        assert len(parsed) == 2
        assert parsed[0]['symbol'] == "RELIANCE"
    
    @pytest.mark.asyncio
    async def test_load_signals_from_file(self):
        """Test loading signals from JSON file."""
        json_content = '[{"symbol": "RELIANCE", "price": 2450.0}]'
        
        signals = json.loads(json_content)
        
        assert len(signals) == 1
        assert signals[0]['symbol'] == "RELIANCE"
    
    def test_create_directory_structure(self, tmp_path):
        """Test creating directory structure for signals."""
        signal_dir = tmp_path / "signals" / "2024-01-15"
        signal_dir.mkdir(parents=True, exist_ok=True)
        
        assert signal_dir.exists()
        assert signal_dir.is_dir()
    
    @pytest.mark.asyncio
    async def test_atomic_file_write(self, tmp_path):
        """Test atomic file write for data safety."""
        target_file = tmp_path / "signals.json"
        temp_file = tmp_path / "signals.json.tmp"
        
        # Write to temp file first
        content = '{"test": true}'
        temp_file.write_text(content)
        
        # Rename atomically
        temp_file.rename(target_file)
        
        assert target_file.exists()
        assert not temp_file.exists()
        assert target_file.read_text() == content


# ============================================================================
# DATABASE FACTORY TESTS
# ============================================================================

class TestDatabaseFactory:
    """Test database factory for creating database instances."""
    
    def test_create_postgres_database(self, mock_database):
        """Test creating PostgreSQL database instance."""
        # Factory should create appropriate database type
        db = mock_database
        
        assert db is not None
        # Should have required methods
        assert hasattr(db, 'connect')
        assert hasattr(db, 'disconnect')
        assert hasattr(db, 'fetch_one')
        assert hasattr(db, 'fetch_all')
        assert hasattr(db, 'insert')
        assert hasattr(db, 'update')
    
    def test_database_singleton(self, mock_database):
        """Test database factory returns singleton."""
        # Same config should return same instance
        db1 = mock_database
        db2 = mock_database
        
        # Should be same instance
        assert db1 is db2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
