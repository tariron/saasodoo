"""
Billing Service - Main Application
FastAPI microservice for handling billing operations with KillBill integration
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os

from .routes import accounts, subscriptions, webhooks
from .utils.database import init_db, close_db
from .utils.killbill_client import KillBillClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("Starting Billing Service...")
    await init_db()
    
    # Initialize KillBill client
    app.state.killbill = KillBillClient(
        base_url=os.getenv("KILLBILL_URL", "http://killbill:8080"),
        api_key=os.getenv("KILLBILL_API_KEY", "lazar"),
        api_secret=os.getenv("KILLBILL_API_SECRET", "bob"),
        username=os.getenv("KILLBILL_USERNAME", "admin"),
        password=os.getenv("KILLBILL_PASSWORD", "password")
    )
    
    logger.info("Billing Service started successfully")
    yield
    
    # Shutdown
    logger.info("Shutting down Billing Service...")
    await close_db()

# Create FastAPI app
app = FastAPI(
    title="Billing Service",
    description="SaaS Odoo Billing Service with KillBill integration",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(accounts.router, prefix="/api/billing/accounts", tags=["accounts"])
app.include_router(subscriptions.router, prefix="/api/billing/subscriptions", tags=["subscriptions"])
app.include_router(webhooks.router, prefix="/api/billing/webhooks", tags=["webhooks"])

@app.get("/")
async def root():
    """Root endpoint"""
    return {"service": "billing-service", "status": "running", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test KillBill connection
        killbill_status = await app.state.killbill.health_check()
        
        return {
            "status": "healthy",
            "service": "billing-service",
            "killbill": killbill_status
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
