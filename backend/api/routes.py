"""
API Routes

Handles OAuth flow.
Uses dependency injection for proper state management.
"""
import logging
from functools import lru_cache
from typing import Optional

from fastapi import APIRouter, Request, Depends
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.core.services import KiteService


logger = logging.getLogger(__name__)

router = APIRouter()


# ================================================================
# DEPENDENCY INJECTION
# ================================================================

class KiteServiceManager:
    """
    Singleton manager for KiteService instance.
    Provides proper lifecycle management for the Kite service.
    """
    
    _instance: Optional[KiteService] = None
    
    @classmethod
    def get_service(cls) -> Optional[KiteService]:
        """Get or create KiteService instance."""
        if cls._instance is None:
            try:
                cls._instance = KiteService()
                logger.info("KiteService initialized")
            except Exception as e:
                logger.error(f"Failed to initialize KiteService: {e}")
                return None
        return cls._instance


def get_kite_service() -> Optional[KiteService]:
    """Dependency for getting KiteService instance."""
    return KiteServiceManager.get_service()


# ================================================================
# ROUTES
# ================================================================

@router.get("/connect")
async def connect(
    kite_service: Optional[KiteService] = Depends(get_kite_service)
):
    """
    Get Zerodha login URL for OAuth flow.
    User should visit this URL to authenticate.
    """
    if not kite_service:
        return JSONResponse(
            {"error": "Kite service not initialized. Check API credentials."},
            status_code=500
        )
    
    login_url = kite_service.get_login_url()
    return {
        "login_url": login_url,
        "message": "Visit this URL to login with Zerodha"
    }


@router.get("/callback")
async def callback(
    request: Request,
    kite_service: Optional[KiteService] = Depends(get_kite_service)
):
    """
    OAuth callback endpoint.
    Zerodha redirects here with request_token after user authentication.
    """
    if not kite_service:
        return JSONResponse(
            {"error": "Kite service not initialized"},
            status_code=500
        )
    
    request_token = request.query_params.get("request_token")
    
    if not request_token:
        return JSONResponse(
            {"error": "Missing request_token parameter"},
            status_code=400
        )
    
    try:
        # Exchange request token for access token
        session_data = kite_service.generate_session(request_token)
        
        logger.info(f"Authentication successful for user: {session_data.get('user_id')}")
        
        return JSONResponse({
            "status": "success",
            "user_id": session_data.get("user_id"),
            "user_name": session_data.get("user_name"),
            "message": "Authentication successful. Access token saved to .env"
        })
        
    except Exception as e:
        logger.error(f"Callback error: {e}", exc_info=True)
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )


@router.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Momentum Trading API"
    }
