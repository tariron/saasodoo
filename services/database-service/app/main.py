"""
Database Service - FastAPI Application
Manages dynamic PostgreSQL database allocation for SaaSOdoo platform
"""

import os
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import structlog

from app.utils.database import db_service
from app.routes import allocation, admin

# Configure structlog for consistent logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ]
)

logger = structlog.get_logger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifecycle manager
    Handles startup and shutdown events
    """
    # Startup
    logger.info("Database Service starting...")
    logger.info("Environment", environment=os.getenv('ENVIRONMENT', 'development'))
    logger.info("PostgreSQL Host", host=os.getenv('POSTGRES_HOST', 'postgres'))
    logger.info("CephFS Mount", path=os.getenv('CEPHFS_MOUNT_PATH', '/mnt/cephfs'))

    # Initialize database connection pool
    try:
        await db_service.connect()
        logger.info("Database connection pool initialized")
    except Exception as e:
        logger.error("Failed to initialize database pool", error=str(e))
        raise

    # Test database connectivity
    try:
        health = await db_service.health_check()
        if health:
            logger.info("Database connectivity test passed")
        else:
            logger.warning("Database connectivity test failed")
    except Exception as e:
        logger.error("Database health check error", error=str(e))

    # TODO: Test Redis connection
    # TODO: Test Docker connection

    logger.info("Database Service started successfully")

    yield

    # Shutdown
    logger.info("Database Service shutting down...")

    # Close database connection pool
    try:
        await db_service.disconnect()
        logger.info("Database connection pool closed")
    except Exception as e:
        logger.error("Error closing database pool", error=str(e))

    logger.info("Database Service stopped")

# Create FastAPI application
app = FastAPI(
    title=os.getenv("API_TITLE", "Database Service"),
    description="Dynamic PostgreSQL database allocation and management for SaaSOdoo",
    version=os.getenv("API_VERSION", "1.0.0"),
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)

# CORS Configuration from environment
def get_cors_origins():
    origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if origins:
        return [o.strip() for o in origins.split(",") if o.strip()]
    return ["http://localhost:3000"]  # Development fallback

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true",
    allow_methods=os.getenv("CORS_ALLOWED_METHODS", "GET,POST,PUT,DELETE,OPTIONS").split(","),
    allow_headers=os.getenv("CORS_ALLOWED_HEADERS", "Authorization,Content-Type").split(","),
)

# Health check endpoint
@app.get("/health", tags=["Health"])
async def health_check():
    """
    Service health check endpoint
    Returns service status and version information
    """
    return {
        "status": "healthy",
        "service": "database-service",
        "version": os.getenv("API_VERSION", "1.0.0"),
        "environment": os.getenv("ENVIRONMENT", "development")
    }

@app.get("/health/database", tags=["Health"])
async def database_health():
    """
    Database connectivity health check
    Tests connection to the platform PostgreSQL database
    """
    # TODO: Implement actual database connection test
    return {
        "status": "healthy",
        "database": "connected",
        "host": os.getenv("POSTGRES_HOST", "postgres"),
        "port": int(os.getenv("POSTGRES_PORT", "5432"))
    }

@app.get("/health/docker", tags=["Health"])
async def docker_health():
    """
    Docker connectivity health check
    Tests connection to Docker daemon
    """
    # TODO: Implement actual Docker connection test
    return {
        "status": "healthy",
        "docker": "connected",
        "socket": os.getenv("DOCKER_HOST", "unix:///var/run/docker.sock")
    }

@app.get("/", tags=["Root"])
async def root():
    """
    Root endpoint
    Returns service information
    """
    return {
        "service": "database-service",
        "description": "Dynamic PostgreSQL database allocation for SaaSOdoo",
        "version": os.getenv("API_VERSION", "1.0.0"),
        "docs": "/docs",
        "health": "/health"
    }

# Include routers for allocation, admin endpoints
app.include_router(allocation.router, prefix="/api/database", tags=["Allocation"])
app.include_router(admin.router, prefix="/api/database/admin", tags=["Admin"])

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8005,
        reload=os.getenv("DEBUG", "false").lower() == "true",
        log_level=os.getenv("LOG_LEVEL", "info").lower()
    )
