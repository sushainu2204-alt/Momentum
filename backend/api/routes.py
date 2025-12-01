"""
API Routes
Handles OAuth flow and ticker management.
"""
import threading
from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from backend.config import settings
from backend.core.services import KiteService
from backend.core.models import Tick


router = APIRouter()

# Global kite service instance
kite_service: KiteService = None
ticker_thread: threading.Thread = None


def init_kite_service():
    """Initialize Kite service"""
    global kite_service
    kite_service = KiteService()


@router.get("/connect")
async def connect():
    """
    Get Zerodha login URL for OAuth flow.
    User should visit this URL to authenticate.
    """
    if not kite_service:
        return JSONResponse(
            {"error": "Kite service not initialized"},
            status_code=500
        )
    
    login_url = kite_service.get_login_url()
    return {
        "login_url": login_url,
        "message": "Visit this URL to login with Zerodha"
    }


@router.get("/callback")
async def callback(request: Request):
    """
    OAuth callback endpoint.
    Zerodha redirects here with request_token after user authentication.
    """
    request_token = request.query_params.get("request_token")
    
    if not request_token:
        return JSONResponse(
            {"error": "Missing request_token parameter"},
            status_code=400
        )
    
    try:
        # Exchange request token for access token
        session_data = kite_service.generate_session(request_token)
        
        print(f"✓ Authentication successful")
        print(f"  User ID: {session_data.get('user_id')}")
        print(f"  Access token saved to .env")
        
        # TODO: Uncomment below to enable tick streaming to Redis
        # Start ticker in background thread
        # def start_ticker_background():
        #     """Start ticker for NIFTY 50"""
        #     instruments = [256265]  # NIFTY 50
        #     
        #     def on_tick(ticks: list[Tick]):
        #         """Callback for tick processing"""
        #         for tick in ticks:
        #             print(f"📊 Tick: {tick.instrument_token} @ ₹{tick.last_price:.2f}")
        #     
        #     kite_service.start_ticker(
        #         instruments=instruments,
        #         on_tick_callback=on_tick
        #     )
        # 
        # global ticker_thread
        # ticker_thread = threading.Thread(target=start_ticker_background, daemon=True)
        # ticker_thread.start()
        
        return JSONResponse({
            "status": "success",
            "user_id": session_data.get("user_id"),
            "user_name": session_data.get("user_name"),
            "message": "Authentication successful."
        })
        
    except Exception as e:
        print(f"⚠ Callback error: {e}")
        import traceback
        traceback.print_exc()
        
        return JSONResponse(
            {"error": str(e)},
            status_code=500
        )


@router.get("/health")
async def health():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "service": "Momentum Trading Backend",
        "ticker_active": ticker_thread is not None and ticker_thread.is_alive()
    }
