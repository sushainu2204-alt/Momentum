# backend/main.py
import os
import threading
import asyncio
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from dotenv import load_dotenv
from backend.kite_client import KiteClient
from typing import Optional

load_dotenv()

KITE_API_KEY = os.environ.get("KITE_API_KEY")
KITE_API_SECRET = os.environ.get("KITE_API_SECRET")
KITE_REDIRECT_URL = os.environ.get("KITE_REDIRECT_URL")  # e.g. http://localhost:8000/callback

app = FastAPI(title="Zerodha Momentum - Backend")

kite_client: Optional[KiteClient] = None
kite_thread = None

def _save_access_token_to_env(access_token: str):
    """
    Save or update KITE_ACCESS_TOKEN in .env file.
    """
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    
    # Read existing .env content
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()
    else:
        lines = []
    
    # Check if KITE_ACCESS_TOKEN already exists
    token_found = False
    for i, line in enumerate(lines):
        if line.strip().startswith("KITE_ACCESS_TOKEN="):
            lines[i] = f"KITE_ACCESS_TOKEN={access_token}\n"
            token_found = True
            break
    
    # If not found, append it
    if not token_found:
        lines.append(f"KITE_ACCESS_TOKEN={access_token}\n")
    
    # Write back to .env
    with open(env_path, "w") as f:
        f.writelines(lines)

@app.on_event("startup")
async def on_startup():
    global kite_client, kite_thread
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    if not (KITE_API_KEY and KITE_API_SECRET and KITE_REDIRECT_URL):
        print("Warning: KITE_API_KEY / KITE_API_SECRET / KITE_REDIRECT_URL not set. Auth endpoints will still work but streaming won't start.")
        return

    kite_client = KiteClient(api_key=KITE_API_KEY, api_secret=KITE_API_SECRET, redirect_url=KITE_REDIRECT_URL, redis_url=redis_url)
    # We do not auto-login — the user must connect via the /connect flow.
    print("Backend started. Use /connect to get the login URL.")

@app.get("/connect")
async def connect():
    """
    Returns the login URL where user should authenticate and grant access.
    After the user logs in on Zerodha, Zerodha will redirect to /callback with request_token.
    """
    if not kite_client:
        return JSONResponse({"error": "Kite client not configured on server. Set env vars."}, status_code=500)
    login_url = kite_client.get_login_url()
    return {"login_url": login_url}

@app.get("/callback")
async def callback(request: Request):
    """
    Callback endpoint Zerodha will redirect to with ?request_token=...
    Exchange for access_token and store it safely.
    NOTE: In production you must associate token with user account and store encrypted.
    """
    params = dict(request.query_params)
    request_token = params.get("request_token")
    if not request_token:
        return JSONResponse({"error": "missing request_token"}, status_code=400)

    try:
        print(f"Exchanging request_token for access_token...")
        print(f"Using API Key: {KITE_API_KEY}")
        access_data = kite_client.generate_session(request_token)
        print(f"Session generated successfully for user: {access_data.get('user_id')}")
        print(f"Access token received: {access_data['access_token'][:20]}...")
        
        # Set access token on the kite instance
        kite_client.kite.set_access_token(access_data["access_token"])
        
        # Save access token to .env file for backtesting and reuse
        _save_access_token_to_env(access_data["access_token"])
        print("✅ Access token saved to .env file")
        
        # Save keys securely here (DB/encrypted storage) -- quick demo returns JSON
        # Start a ticker thread for this user (in production run per-user workers)
        if kite_client and access_data.get("access_token"):
            # Give a moment for token to be set
            import time
            time.sleep(0.5)
            
            # start ticker streaming in background thread
            def start_ticker():
                kite_client.start_ticker(access_token=access_data["access_token"], user_id=access_data["user_id"])
            t = threading.Thread(target=start_ticker, daemon=True)
            t.start()
            print("Ticker thread started successfully")
        
        # Return success without exposing full access_token
        return JSONResponse({
            "status": "connected", 
            "user_id": access_data.get("user_id"),
            "user_name": access_data.get("user_name"),
            "message": "Successfully authenticated. Ticker streaming started."
        })
    except Exception as e:
        print(f"Callback error: {e}")
        import traceback
        traceback.print_exc()
        return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/")
async def root():
    return {"message": "Zerodha Momentum backend up. Use /connect to begin."}
