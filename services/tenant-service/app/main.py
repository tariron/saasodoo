"""
Tenant Service - Main Application
Handles Odoo instance provisioning and tenant management
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from app.utils.database import TenantDatabase
from app.routes import health, tenants, instances


# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.stdlib.PositionalArgumentsFormatter(),
        structlog.processors.JSONRenderer()
    ],
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """Application lifespan events"""
    logger.info("Starting Tenant Service")
    
    # Initialize database connection
    try:
        db = TenantDatabase()
        await db.initialize()
        app.state.db = db
        logger.info("Database connection initialized")
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        raise
    
    yield
    
    # Cleanup
    if hasattr(app.state, 'db'):
        await app.state.db.close()
        logger.info("Database connection closed")
    
    logger.info("Tenant Service shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="SaaS Odoo - Tenant Service",
    description="Manages Odoo tenant instances and provisioning",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure properly for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests"""
    logger.info(
        "Request received",
        method=request.method,
        url=str(request.url),
        client_ip=request.client.host if request.client else "unknown"
    )
    
    response = await call_next(request)
    
    logger.info(
        "Request completed",
        method=request.method,
        url=str(request.url),
        status_code=response.status_code
    )
    
    return response


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    """Global exception handler"""
    logger.error(
        "Unhandled exception",
        error=str(exc),
        method=request.method,
        url=str(request.url),
        exc_info=True
    )
    
    return JSONResponse(
        status_code=500,
        content={
            "error": "Internal server error",
            "message": "An unexpected error occurred"
        }
    )


# Register routes
app.include_router(health.router, tags=["Health"])
app.include_router(tenants.router, prefix="/api/v1/tenants", tags=["Tenants"])
app.include_router(instances.router, prefix="/api/v1/instances", tags=["Instances"])


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "tenant-service",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8002,
        reload=True,
        log_level="info"
    ) 