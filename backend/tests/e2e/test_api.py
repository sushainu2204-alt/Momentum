"""
E2E Tests for API Endpoints

Tests the FastAPI application endpoints using TestClient.
"""
import pytest
from unittest.mock import Mock, patch, MagicMock
from fastapi.testclient import TestClient


class TestMainApp:
    """Test main.py FastAPI application endpoints."""
    
    @pytest.fixture
    def client(self):
        """Create test client with mocked Kite."""
        with patch('backend.main.KiteConnect') as mock_kite_class:
            # Setup mock KiteConnect
            mock_kite = Mock()
            mock_kite.login_url.return_value = "https://kite.zerodha.com/connect/login?v=3&api_key=test"
            mock_kite_class.return_value = mock_kite
            
            # Patch settings
            with patch('backend.main.settings') as mock_settings:
                mock_settings.KITE_API_KEY = "test_api_key"
                mock_settings.KITE_API_SECRET = "test_api_secret"
                mock_settings.KITE_REDIRECT_URL = "http://localhost:8000/callback"
                
                # Import after patching
                from backend.main import app
                
                # Manually set the kite instance
                import backend.main as main_module
                main_module.kite = mock_kite
                
                yield TestClient(app)
    
    @pytest.fixture
    def client_no_kite(self):
        """Create test client without Kite configured."""
        with patch('backend.main.settings') as mock_settings:
            mock_settings.KITE_API_KEY = None
            mock_settings.KITE_API_SECRET = None
            mock_settings.KITE_REDIRECT_URL = None
            
            from backend.main import app
            import backend.main as main_module
            main_module.kite = None
            
            yield TestClient(app)
    
    def test_root_endpoint(self, client):
        """Test GET / returns service info."""
        response = client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "Zerodha Momentum" in data["message"]
        assert "docs" in data
        assert data["docs"] == "/docs"
        assert "auth" in data
    
    def test_health_endpoint(self, client):
        """Test GET /health returns healthy status."""
        response = client.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data
    
    def test_connect_returns_login_url(self, client):
        """Test GET /connect returns login URL."""
        response = client.get("/connect")
        
        assert response.status_code == 200
        data = response.json()
        assert "login_url" in data
        assert "kite.zerodha.com" in data["login_url"]
    
    def test_connect_without_kite_returns_error(self, client_no_kite):
        """Test GET /connect without Kite config returns error."""
        response = client_no_kite.get("/connect")
        
        assert response.status_code == 500
        data = response.json()
        assert "error" in data
    
    def test_callback_without_token_returns_error(self, client):
        """Test GET /callback without request_token returns 400."""
        response = client.get("/callback")
        
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "request_token" in data["error"].lower()
    
    def test_callback_success(self, client):
        """Test GET /callback with valid token exchanges for access token."""
        # Setup mock to return session data
        import backend.main as main_module
        main_module.kite.generate_session.return_value = {
            "user_id": "TEST123",
            "user_name": "Test User",
            "access_token": "test_access_token_123"
        }
        
        with patch.object(main_module.settings, 'update_access_token'):
            response = client.get("/callback?request_token=valid_token")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"
        assert data["user_id"] == "TEST123"
        assert data["user_name"] == "Test User"
    
    def test_callback_with_invalid_token_returns_error(self, client):
        """Test GET /callback with invalid token returns error."""
        import backend.main as main_module
        main_module.kite.generate_session.side_effect = Exception("Invalid request token")
        
        response = client.get("/callback?request_token=invalid_token")
        
        assert response.status_code == 500
        data = response.json()
        assert "error" in data


class TestAPIRouter:
    """Test api/routes.py router endpoints."""
    
    @pytest.fixture
    def mock_kite_service(self):
        """Create mock KiteService."""
        mock = Mock()
        mock.get_login_url.return_value = "https://kite.zerodha.com/connect/login?v=3&api_key=test"
        mock.generate_session.return_value = {
            "user_id": "TEST456",
            "user_name": "Router Test User",
            "access_token": "router_access_token"
        }
        return mock
    
    @pytest.fixture
    def client_with_router(self, mock_kite_service):
        """Create test client using the router."""
        from fastapi import FastAPI
        from backend.api.routes import router, KiteServiceManager
        
        # Reset singleton
        KiteServiceManager._instance = mock_kite_service
        
        app = FastAPI()
        app.include_router(router)
        
        yield TestClient(app)
        
        # Cleanup
        KiteServiceManager._instance = None
    
    @pytest.fixture
    def client_without_kite_service(self):
        """Create test client with no KiteService."""
        from fastapi import FastAPI
        from backend.api.routes import router, KiteServiceManager
        
        # Reset singleton to None
        KiteServiceManager._instance = None
        
        app = FastAPI()
        app.include_router(router)
        
        # Patch get_service to return None
        with patch.object(KiteServiceManager, 'get_service', return_value=None):
            yield TestClient(app)
    
    def test_router_health_endpoint(self, client_with_router):
        """Test GET /health on router returns healthy status."""
        response = client_with_router.get("/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "service" in data
    
    def test_router_connect_returns_login_url(self, client_with_router):
        """Test GET /connect on router returns login URL."""
        response = client_with_router.get("/connect")
        
        assert response.status_code == 200
        data = response.json()
        assert "login_url" in data
        assert "message" in data
    
    def test_router_connect_without_service_returns_error(self, client_without_kite_service):
        """Test GET /connect without KiteService returns error."""
        response = client_without_kite_service.get("/connect")
        
        assert response.status_code == 500
        data = response.json()
        assert "error" in data
    
    def test_router_callback_success(self, client_with_router, mock_kite_service):
        """Test GET /callback with valid token on router."""
        response = client_with_router.get("/callback?request_token=valid_token")
        
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["user_id"] == "TEST456"
    
    def test_router_callback_missing_token(self, client_with_router):
        """Test GET /callback without token on router returns 400."""
        response = client_with_router.get("/callback")
        
        assert response.status_code == 400
        data = response.json()
        assert "error" in data
        assert "request_token" in data["error"].lower()
    
    def test_router_callback_without_service_returns_error(self, client_without_kite_service):
        """Test GET /callback without KiteService returns error."""
        response = client_without_kite_service.get("/callback?request_token=test")
        
        assert response.status_code == 500
        data = response.json()
        assert "error" in data
    
    def test_router_callback_with_exception(self, client_with_router, mock_kite_service):
        """Test GET /callback handles exceptions gracefully."""
        mock_kite_service.generate_session.side_effect = Exception("Authentication failed")
        
        response = client_with_router.get("/callback?request_token=bad_token")
        
        assert response.status_code == 500
        data = response.json()
        assert "error" in data


class TestKiteServiceManager:
    """Test KiteServiceManager singleton."""
    
    def test_get_service_creates_instance(self):
        """Test get_service creates KiteService instance."""
        from backend.api.routes import KiteServiceManager
        
        # Reset singleton
        KiteServiceManager._instance = None
        
        with patch('backend.api.routes.KiteService') as mock_service_class:
            mock_service = Mock()
            mock_service_class.return_value = mock_service
            
            result = KiteServiceManager.get_service()
            
            assert result == mock_service
            mock_service_class.assert_called_once()
    
    def test_get_service_returns_existing_instance(self):
        """Test get_service returns existing instance (singleton)."""
        from backend.api.routes import KiteServiceManager
        
        # Set existing instance
        mock_service = Mock()
        KiteServiceManager._instance = mock_service
        
        result = KiteServiceManager.get_service()
        
        assert result == mock_service
        
        # Cleanup
        KiteServiceManager._instance = None
    
    def test_get_service_handles_initialization_error(self):
        """Test get_service returns None on initialization error."""
        from backend.api.routes import KiteServiceManager
        
        # Reset singleton
        KiteServiceManager._instance = None
        
        with patch('backend.api.routes.KiteService') as mock_service_class:
            mock_service_class.side_effect = Exception("Init failed")
            
            result = KiteServiceManager.get_service()
            
            assert result is None
        
        # Cleanup
        KiteServiceManager._instance = None


class TestAPIErrorHandling:
    """Test API error handling scenarios."""
    
    @pytest.fixture
    def client(self):
        """Create basic test client."""
        with patch('backend.main.KiteConnect') as mock_kite_class:
            mock_kite = Mock()
            mock_kite_class.return_value = mock_kite
            
            with patch('backend.main.settings') as mock_settings:
                mock_settings.KITE_API_KEY = "test_key"
                mock_settings.KITE_API_SECRET = "test_secret"
                mock_settings.KITE_REDIRECT_URL = "http://localhost/callback"
                
                from backend.main import app
                import backend.main as main_module
                main_module.kite = mock_kite
                
                yield TestClient(app)
    
    def test_invalid_endpoint_returns_404(self, client):
        """Test accessing invalid endpoint returns 404."""
        response = client.get("/nonexistent")
        
        assert response.status_code == 404
    
    def test_method_not_allowed(self, client):
        """Test POST to GET-only endpoint returns 405."""
        response = client.post("/health")
        
        assert response.status_code == 405
    
    def test_callback_network_error(self, client):
        """Test callback handles network errors."""
        import backend.main as main_module
        main_module.kite.generate_session.side_effect = ConnectionError("Network unavailable")
        
        response = client.get("/callback?request_token=test")
        
        assert response.status_code == 500
        data = response.json()
        assert "error" in data
    
    def test_callback_timeout_error(self, client):
        """Test callback handles timeout errors."""
        import backend.main as main_module
        main_module.kite.generate_session.side_effect = TimeoutError("Request timed out")
        
        response = client.get("/callback?request_token=test")
        
        assert response.status_code == 500
        data = response.json()
        assert "error" in data


class TestAPIIntegration:
    """Integration tests for API workflow."""
    
    @pytest.fixture
    def full_client(self):
        """Create fully configured test client."""
        with patch('backend.main.KiteConnect') as mock_kite_class:
            mock_kite = Mock()
            mock_kite.login_url.return_value = "https://kite.zerodha.com/login?api_key=test"
            mock_kite.generate_session.return_value = {
                "user_id": "INTEG123",
                "user_name": "Integration User",
                "access_token": "integration_token"
            }
            mock_kite_class.return_value = mock_kite
            
            with patch('backend.main.settings') as mock_settings:
                mock_settings.KITE_API_KEY = "test_key"
                mock_settings.KITE_API_SECRET = "test_secret"
                mock_settings.KITE_REDIRECT_URL = "http://localhost/callback"
                mock_settings.update_access_token = Mock()
                
                from backend.main import app
                import backend.main as main_module
                main_module.kite = mock_kite
                
                yield TestClient(app)
    
    def test_full_oauth_flow(self, full_client):
        """Test complete OAuth flow: connect -> callback."""
        # Step 1: Get login URL
        connect_response = full_client.get("/connect")
        assert connect_response.status_code == 200
        login_url = connect_response.json()["login_url"]
        assert "zerodha.com" in login_url
        
        # Step 2: Simulate callback (user authenticated)
        callback_response = full_client.get("/callback?request_token=mock_token")
        assert callback_response.status_code == 200
        
        data = callback_response.json()
        assert data["status"] == "connected"
        assert data["user_id"] == "INTEG123"
    
    def test_health_check_always_works(self, full_client):
        """Test health check works regardless of auth state."""
        response = full_client.get("/health")
        
        assert response.status_code == 200
        assert response.json()["status"] == "healthy"
    
    def test_api_info_available(self, full_client):
        """Test API info available at root."""
        response = full_client.get("/")
        
        assert response.status_code == 200
        data = response.json()
        assert "message" in data
        assert "docs" in data
