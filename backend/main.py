# backend/main.py
"""
Main FastAPI application entry point.

Handles:
- Kite Connect OAuth flow
- Health checks
"""
import logging
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from kiteconnect import KiteConnect
from backend.config import settings

load_dotenv()

logger = logging.getLogger(__name__)

KITE_API_KEY = settings.KITE_API_KEY
KITE_API_SECRET = settings.KITE_API_SECRET
KITE_REDIRECT_URL = settings.KITE_REDIRECT_URL

app = FastAPI(title="Zerodha Momentum - Backend")

# KiteConnect instance for OAuth
kite: KiteConnect = None


@app.on_event("startup")
async def on_startup():
    """Initialize Kite client on application startup."""
    global kite
    
    if not (KITE_API_KEY and KITE_API_SECRET and KITE_REDIRECT_URL):
        logger.warning(
            "KITE_API_KEY / KITE_API_SECRET / KITE_REDIRECT_URL not set. "
            "Auth endpoints will not work."
        )
        return

    kite = KiteConnect(api_key=KITE_API_KEY)
    logger.info("Backend started. Use /connect to get the login URL.")

@app.get("/connect")
async def connect():
    """
    Returns the login URL where user should authenticate and grant access.
    After the user logs in on Zerodha, Zerodha will redirect to /callback with request_token.
    """
    if not kite:
        return JSONResponse(
            {"error": "Kite client not configured. Set environment variables."},
            status_code=500
        )
    login_url = kite.login_url()
    return {"login_url": login_url}


@app.get("/callback")
async def callback(request: Request):
    """
    OAuth callback endpoint.
    
    Zerodha redirects here with ?request_token=... after user authentication.
    Exchanges request_token for access_token and stores it in .env.
    
    NOTE: In production, you must associate token with user account and store encrypted.
    """
    request_token = request.query_params.get("request_token")
    if not request_token:
        return JSONResponse({"error": "Missing request_token"}, status_code=400)

    try:
        logger.info("Exchanging request_token for access_token...")
        access_data = kite.generate_session(request_token, api_secret=KITE_API_SECRET)
        
        user_id = access_data.get('user_id')
        access_token = access_data['access_token']
        
        logger.info(f"Session generated successfully for user: {user_id}")
        
        # Set access token on the kite instance
        kite.set_access_token(access_token)
        
        # Save access token using centralized Settings method
        settings.update_access_token(access_token)
        logger.info("Access token saved to .env file")
        
        return JSONResponse({
            "status": "connected", 
            "user_id": user_id,
            "user_name": access_data.get("user_name"),
            "message": "Successfully authenticated. Access token saved."
        })
        
    except Exception as e:
        logger.error(f"Callback error: {e}", exc_info=True)
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/")
async def root():
    """Root endpoint with basic service info."""
    return {
        "message": "Zerodha Momentum backend running",
        "docs": "/docs",
        "auth": "Use /connect to begin OAuth flow"
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "service": "Momentum Trading Backend"
    }
