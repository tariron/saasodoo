"""
User Service - FastAPI Application
Customer authentication and user management for SaaS Odoo Kit
"""

from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse
import logging
from contextlib import asynccontextmanager

from app.routes import auth, users
from app.utils.dependencies import get_database
from app.utils.database import init_database
from app.utils.billing_client import billing_client

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    # Startup
    logger.info("User Service starting up...")

    # Initialize database connections
    await init_database()

    # Initialize HTTP client with connection pooling
    await billing_client.start()

    logger.info("User Service startup complete - using Redis for sessions")

    yield

    # Shutdown
    logger.info("User Service shutting down...")

    # Close HTTP client connections
    await billing_client.stop()

# Create FastAPI application
app = FastAPI(
    title="User Service",
    description="Customer authentication and user management for SaaS Odoo Kit",
    version="1.0.0",
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Add trusted host middleware
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=["*"]  # Configure for production
)

# Global exception handler
@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    """Custom HTTP exception handler"""
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": True,
            "message": exc.detail,
            "status_code": exc.status_code
        }
    )

# Health check endpoint
@app.get("/health")
async def health_check():
    """Service health check"""
    return {
        "status": "healthy",
        "service": "user-service",
        "version": "1.0.0"
    }

# Database connection test endpoint
@app.get("/health/database")
async def database_health_check(db=Depends(get_database)):
    """Database connection health check"""
    try:
        # Test database connection
        result = await db.fetch("SELECT 1 as test")
        return {
            "status": "healthy",
            "database": "connected",
            "test_query": "passed"
        }
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database connection failed"
        )

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/users", tags=["User Management"])

# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "User Service",
        "version": "1.0.0",
        "description": "Customer authentication and user management",
        "docs": "/docs"
    }

 