"""
Unit Tests for Kite Service

Tests the KiteService wrapper for Kite Connect API.
"""
import pytest
from datetime import datetime
from unittest.mock import Mock, patch, MagicMock


class TestKiteService:
    """Test KiteService."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        with patch('backend.core.services.market.kite_service.settings') as mock:
            mock.KITE_API_KEY = "test_api_key"
            mock.KITE_API_SECRET = "test_api_secret"
            mock.KITE_ACCESS_TOKEN = "test_access_token"
            mock.update_access_token = Mock()
            yield mock
    
    @pytest.fixture
    def mock_kite_connect(self):
        """Create mock KiteConnect."""
        with patch('backend.core.services.market.kite_service.KiteConnect') as mock_class:
            mock_instance = Mock()
            mock_instance.login_url.return_value = "https://kite.zerodha.com/connect/login?v=3&api_key=test"
            mock_class.return_value = mock_instance
            yield mock_class, mock_instance
    
    def test_init_with_defaults(self, mock_settings, mock_kite_connect):
        """Test initialization with default settings."""
        mock_class, mock_instance = mock_kite_connect
        
        from backend.core.services.market.kite_service import KiteService
        service = KiteService()
        
        assert service.api_key == "test_api_key"
        assert service.api_secret == "test_api_secret"
        mock_class.assert_called_once_with(api_key="test_api_key")
        mock_instance.set_access_token.assert_called_once_with("test_access_token")
    
    def test_init_with_custom_credentials(self, mock_settings, mock_kite_connect):
        """Test initialization with custom credentials."""
        mock_class, mock_instance = mock_kite_connect
        
        from backend.core.services.market.kite_service import KiteService
        service = KiteService(
            api_key="custom_key",
            api_secret="custom_secret"
        )
        
        assert service.api_key == "custom_key"
        assert service.api_secret == "custom_secret"
        mock_class.assert_called_once_with(api_key="custom_key")
    
    def test_init_without_access_token(self, mock_settings, mock_kite_connect):
        """Test initialization without existing access token."""
        mock_class, mock_instance = mock_kite_connect
        mock_settings.KITE_ACCESS_TOKEN = None
        
        from backend.core.services.market.kite_service import KiteService
        service = KiteService()
        
        # Should not call set_access_token
        mock_instance.set_access_token.assert_not_called()
    
    def test_get_login_url(self, mock_settings, mock_kite_connect):
        """Test get_login_url returns correct URL."""
        mock_class, mock_instance = mock_kite_connect
        
        from backend.core.services.market.kite_service import KiteService
        service = KiteService()
        
        url = service.get_login_url()
        
        assert "kite.zerodha.com" in url
        mock_instance.login_url.assert_called_once()
    
    def test_generate_session(self, mock_settings, mock_kite_connect):
        """Test generate_session exchanges token."""
        mock_class, mock_instance = mock_kite_connect
        mock_instance.generate_session.return_value = {
            "user_id": "TEST123",
            "access_token": "new_access_token"
        }
        
        from backend.core.services.market.kite_service import KiteService
        service = KiteService()
        
        session = service.generate_session("test_request_token")
        
        assert session["user_id"] == "TEST123"
        assert session["access_token"] == "new_access_token"
        mock_instance.generate_session.assert_called_once_with(
            request_token="test_request_token",
            api_secret="test_api_secret"
        )
        mock_settings.update_access_token.assert_called_with("new_access_token")
    
    def test_set_access_token(self, mock_settings, mock_kite_connect):
        """Test set_access_token updates token."""
        mock_class, mock_instance = mock_kite_connect
        
        from backend.core.services.market.kite_service import KiteService
        service = KiteService()
        
        service.set_access_token("new_token")
        
        # Called twice: once in init, once in set_access_token
        assert mock_instance.set_access_token.call_count == 2
        mock_settings.update_access_token.assert_called_with("new_token")
    
    def test_margins(self, mock_settings, mock_kite_connect):
        """Test margins returns margin data."""
        mock_class, mock_instance = mock_kite_connect
        mock_instance.margins.return_value = {
            "equity": {"available": {"cash": 100000}}
        }
        
        from backend.core.services.market.kite_service import KiteService
        service = KiteService()
        
        margins = service.margins()
        
        assert "equity" in margins
        mock_instance.margins.assert_called_once()
    
    def test_get_historical_data(self, mock_settings, mock_kite_connect):
        """Test get_historical_data fetches OHLC data."""
        mock_class, mock_instance = mock_kite_connect
        mock_data = [
            {
                "date": datetime(2024, 1, 15, 9, 15),
                "open": 2400.0,
                "high": 2450.0,
                "low": 2380.0,
                "close": 2440.0,
                "volume": 100000
            }
        ]
        mock_instance.historical_data.return_value = mock_data
        
        from backend.core.services.market.kite_service import KiteService
        service = KiteService()
        
        data = service.get_historical_data(
            instrument_token=738561,
            from_date="2024-01-15",
            to_date="2024-01-15",
            interval="5minute"
        )
        
        assert len(data) == 1
        assert data[0]["open"] == 2400.0
        mock_instance.historical_data.assert_called_once_with(
            instrument_token=738561,
            from_date="2024-01-15",
            to_date="2024-01-15",
            interval="5minute"
        )
    
    def test_get_historical_data_default_interval(self, mock_settings, mock_kite_connect):
        """Test get_historical_data uses default interval."""
        mock_class, mock_instance = mock_kite_connect
        mock_instance.historical_data.return_value = []
        
        from backend.core.services.market.kite_service import KiteService
        service = KiteService()
        
        service.get_historical_data(
            instrument_token=738561,
            from_date="2024-01-15",
            to_date="2024-01-15"
        )
        
        mock_instance.historical_data.assert_called_once_with(
            instrument_token=738561,
            from_date="2024-01-15",
            to_date="2024-01-15",
            interval="5minute"
        )


class TestKiteServiceErrorHandling:
    """Test KiteService error handling."""
    
    @pytest.fixture
    def mock_settings(self):
        """Create mock settings."""
        with patch('backend.core.services.market.kite_service.settings') as mock:
            mock.KITE_API_KEY = "test_api_key"
            mock.KITE_API_SECRET = "test_api_secret"
            mock.KITE_ACCESS_TOKEN = "test_access_token"
            mock.update_access_token = Mock()
            yield mock
    
    @pytest.fixture
    def mock_kite_connect(self):
        """Create mock KiteConnect."""
        with patch('backend.core.services.market.kite_service.KiteConnect') as mock_class:
            mock_instance = Mock()
            mock_class.return_value = mock_instance
            yield mock_class, mock_instance
    
    def test_generate_session_error(self, mock_settings, mock_kite_connect):
        """Test generate_session handles errors."""
        mock_class, mock_instance = mock_kite_connect
        mock_instance.generate_session.side_effect = Exception("Invalid token")
        
        from backend.core.services.market.kite_service import KiteService
        service = KiteService()
        
        with pytest.raises(Exception) as exc_info:
            service.generate_session("invalid_token")
        
        assert "Invalid token" in str(exc_info.value)
    
    def test_margins_error(self, mock_settings, mock_kite_connect):
        """Test margins handles API errors."""
        mock_class, mock_instance = mock_kite_connect
        mock_instance.margins.side_effect = Exception("API error")
        
        from backend.core.services.market.kite_service import KiteService
        service = KiteService()
        
        with pytest.raises(Exception) as exc_info:
            service.margins()
        
        assert "API error" in str(exc_info.value)
    
    def test_historical_data_error(self, mock_settings, mock_kite_connect):
        """Test get_historical_data handles errors."""
        mock_class, mock_instance = mock_kite_connect
        mock_instance.historical_data.side_effect = Exception("Rate limited")
        
        from backend.core.services.market.kite_service import KiteService
        service = KiteService()
        
        with pytest.raises(Exception) as exc_info:
            service.get_historical_data(
                instrument_token=738561,
                from_date="2024-01-15",
                to_date="2024-01-15"
            )
        
        assert "Rate limited" in str(exc_info.value)
