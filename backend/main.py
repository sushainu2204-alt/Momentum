# backend/main.py
"""
Main FastAPI application entry point.

Handles:
- Kite Connect OAuth flow (auto-opens browser if not authenticated)
- Health checks
- Background sync jobs (auto-start)
"""
import webbrowser
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from dotenv import load_dotenv

from kiteconnect import KiteConnect
from backend.config import settings
from backend.config.logging_config import setup_logging

load_dotenv()

# Setup logging using app config
logger = setup_logging(name="main", log_to_file=True)

KITE_API_KEY = settings.KITE_API_KEY
KITE_API_SECRET = settings.KITE_API_SECRET
KITE_REDIRECT_URL = settings.KITE_REDIRECT_URL

# Global instances
kite: KiteConnect = None
sync_scheduler = None
db = None


async def init_background_jobs():
    """Initialize and start background sync jobs."""
    global sync_scheduler, db
    
    try:
        from backend.jobs.sync.sync_jobs import SyncJobsScheduler
        from backend.core.services import (
            OrderManager,
            PositionManager,
            CapitalManager,
            SignalExecutor,
            KiteService,
            TrailingSLService as TrailingStopLossService,
        )
        from backend.infrastructure.database.factory import create_database
        from backend.infrastructure.database.order_repository import OrderRepository
        from backend.infrastructure.database.position_repository import PositionRepository
        
        # Initialize database
        db = create_database()
        await db.connect()
        logger.info("✓ Database connected")
        
        # Check if Kite token is available
        if not settings.KITE_ACCESS_TOKEN:
            logger.warning("⚠️  KITE_ACCESS_TOKEN not set. Background jobs will start but may fail.")
            logger.warning("   Use /connect to authenticate with Zerodha first.")
        
        # Initialize Kite service
        kite_service = KiteService()
        logger.info("✓ Kite service initialized")
        
        # Initialize repositories
        order_repo = OrderRepository(db)
        position_repo = PositionRepository(db)
        
        # Initialize managers
        order_manager = OrderManager(
            kite_service=kite_service,
            order_repository=order_repo
        )
        
        position_manager = PositionManager(
            kite_service=kite_service,
            position_repository=position_repo,
            order_repository=order_repo
        )
        
        capital_manager = CapitalManager(
            database=db,
            kite_service=kite_service,
            position_manager=position_manager
        )
        
        signal_executor = SignalExecutor(
            database=db,
            order_manager=order_manager,
            position_manager=position_manager,
            capital_manager=capital_manager
        )
        
        # Trailing SL service
        trailing_sl_service = TrailingStopLossService(
            position_repository=position_repo,
            kite_service=kite_service,
            order_repository=order_repo,
            order_manager=order_manager
        )
        
        logger.info("✓ All managers initialized")
        
        # Create and start scheduler
        sync_scheduler = SyncJobsScheduler(
            order_manager=order_manager,
            position_manager=position_manager,
            capital_manager=capital_manager,
            signal_executor=signal_executor,
            trailing_sl_service=trailing_sl_service
        )
        
        sync_scheduler.start()
        logger.info("✅ Background sync jobs started!")
        
    except Exception as e:
        logger.error(f"❌ Failed to start background jobs: {e}", exc_info=True)
        raise RuntimeError(f"Cannot start application without background jobs: {e}")


async def shutdown_background_jobs():
    """Stop background jobs gracefully."""
    global sync_scheduler, db
    
    if sync_scheduler:
        try:
            sync_scheduler.stop()
            logger.info("✓ Background sync jobs stopped")
        except Exception as e:
            logger.error(f"Error stopping sync jobs: {e}")
    
    if db:
        try:
            await db.disconnect()
            logger.info("✓ Database connection closed")
        except Exception as e:
            logger.error(f"Error closing database: {e}")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan manager.
    
    Startup: Initialize Kite client, authenticate, then start background jobs
    Shutdown: Stop background jobs and cleanup
    
    NOTE: Kite access tokens expire daily, so we always require fresh login.
    """
    global kite
    
    # === STARTUP ===
    logger.info("=" * 60)
    logger.info("  MOMENTUM TRADING BACKEND - STARTING")
    logger.info("=" * 60)
    
    # Initialize Kite client for OAuth
    if KITE_API_KEY and KITE_API_SECRET and KITE_REDIRECT_URL:
        kite = KiteConnect(api_key=KITE_API_KEY)
        logger.info("✓ Kite OAuth client initialized")
        
        # Always open browser for fresh login (tokens expire daily)
        login_url = kite.login_url()
        logger.info("")
        logger.info("🔐 Opening Zerodha login for fresh token...")
        logger.info(f"   URL: {login_url}")
        try:
            webbrowser.open(login_url)
            logger.info("   ✓ Browser opened! Please login to Zerodha.")
        except Exception as e:
            logger.warning(f"   ⚠️  Could not open browser: {e}")
            logger.info(f"   Please manually open: {login_url}")
        
        logger.info("")
        logger.info("⏳ Waiting for Zerodha authentication...")
        logger.info("   Background jobs will start after you login.")
    else:
        logger.warning("⚠️  KITE credentials not set. Cannot start.")
        raise RuntimeError("KITE_API_KEY, KITE_API_SECRET, and KITE_REDIRECT_URL must be set")

    logger.info("")
    logger.info("🚀 Application ready!")
    logger.info("   - API docs: /docs")
    logger.info("   - Health check: /health")
    logger.info("   - Complete Zerodha login to start trading jobs")
    logger.info("=" * 60)
    
    yield  # Application runs here
    
    # === SHUTDOWN ===
    logger.info("")
    logger.info("🛑 Shutting down...")
    await shutdown_background_jobs()
    logger.info("✅ Shutdown complete")


app = FastAPI(
    title="Zerodha Momentum - Backend",
    lifespan=lifespan
)

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
        
        # Start background jobs now that we're authenticated
        global sync_scheduler
        if not sync_scheduler or not sync_scheduler._is_running:
            logger.info("")
            logger.info("🔓 Authentication successful! Starting background jobs...")
            await init_background_jobs()
        
        return JSONResponse({
            "status": "connected", 
            "user_id": user_id,
            "user_name": access_data.get("user_name"),
            "message": "Successfully authenticated. Background jobs started."
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
        "service": "Momentum Trading Backend",
        "sync_jobs_running": sync_scheduler._is_running if sync_scheduler else False,
        "database_connected": db is not None and db.pool is not None
    }


@app.get("/jobs/status")
async def jobs_status():
    """Get status of background sync jobs."""
    if not sync_scheduler:
        return {
            "status": "not_initialized",
            "message": "Sync jobs scheduler not initialized"
        }
    
    jobs = []
    if sync_scheduler.scheduler.running:
        for job in sync_scheduler.scheduler.get_jobs():
            jobs.append({
                "id": job.id,
                "name": job.name,
                "next_run": str(job.next_run_time) if job.next_run_time else None
            })
    
    return {
        "status": "running" if sync_scheduler._is_running else "stopped",
        "jobs": jobs
    }
