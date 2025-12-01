"""
Momentum Trading Backend
FastAPI application with clean architecture.
"""
from fastapi import FastAPI
from backend.api.routes import router, init_kite_service


app = FastAPI(
    title="Momentum Trading Backend",
    description="Algorithmic trading system with Kite Connect integration",
    version="2.0.0"
)

# Include API routes
app.include_router(router)


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup"""
    print("\n" + "="*60)
    print("MOMENTUM TRADING BACKEND")
    print("="*60)
    print("Starting services...")
    
    # Initialize Kite service
    init_kite_service()
    
    print("✓ All services initialized")
    print("\n📡 API Endpoints:")
    print("  GET  /connect  - Get Zerodha login URL")
    print("  GET  /callback - OAuth callback (auto-called by Zerodha)")
    print("  GET  /health   - Health check")
    print("\n✨ To get started:")
    print("  1. Visit http://localhost:8000/connect")
    print("  2. Login with your Zerodha credentials")
    print("  3. Access token will be saved automatically")
    print("="*60 + "\n")


@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "Momentum Trading Backend",
        "version": "2.0.0",
        "status": "running",
        "endpoints": {
            "connect": "/connect",
            "health": "/health",
            "docs": "/docs"
        }
    }
