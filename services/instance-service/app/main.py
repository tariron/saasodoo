"""
Instance Service - Main Application
Handles Odoo instance provisioning and lifecycle management
"""

import os
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import structlog

from app.utils.database import InstanceDatabase
from app.routes import instances, admin, monitoring


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
    logger.info("Starting Instance Service")
    
    # Initialize database connection
    try:
        db = InstanceDatabase()
        await db.initialize()
        app.state.db = db
        logger.info("Database connection initialized")
    except Exception as e:
        logger.error("Failed to initialize database", error=str(e))
        raise
    
    # Initialize Docker event monitoring (if enabled)
    try:
        auto_start_monitoring = os.getenv('AUTO_START_MONITORING', 'true').lower() == 'true'
        if auto_start_monitoring:
            logger.info("Auto-starting Docker event monitoring")
            from app.tasks.monitoring import monitor_docker_events_task
            task = monitor_docker_events_task.delay()
            logger.info("Docker event monitoring task started", task_id=task.id)
        else:
            logger.info("Docker event monitoring auto-start disabled")
    except Exception as e:
        logger.error("Failed to start Docker event monitoring", error=str(e))
        # Don't raise - monitoring is optional and can be started manually
    
    yield
    
    # Cleanup
    try:
        # Stop Docker event monitoring if running
        from app.tasks.monitoring import stop_docker_events_monitoring_task, _monitoring_active
        if _monitoring_active:
            logger.info("Stopping Docker event monitoring")
            stop_task = stop_docker_events_monitoring_task.delay()
            try:
                stop_task.get(timeout=10)
                logger.info("Docker event monitoring stopped")
            except Exception as e:
                logger.warning("Failed to gracefully stop monitoring", error=str(e))
    except Exception as e:
        logger.error("Error during monitoring cleanup", error=str(e))
    
    if hasattr(app.state, 'db'):
        await app.state.db.close()
        logger.info("Database connection closed")
    
    logger.info("Instance Service shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="SaaS Odoo - Instance Service",
    description="Manages Odoo instance provisioning and lifecycle",
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


# Health check endpoint
@app.get("/health")
async def health_check():
    """Service health check"""
    return {
        "status": "healthy",
        "service": "instance-service",
        "version": "1.0.0"
    }


# Database health check endpoint
@app.get("/health/database")
async def database_health_check(request: Request):
    """Database connection health check"""
    try:
        db = request.app.state.db
        async with db.pool.acquire() as conn:
            result = await conn.fetchval('SELECT COUNT(*) FROM instances')
            return {
                "status": "healthy",
                "database": "connected",
                "instance_count": result
            }
    except Exception as e:
        logger.error("Database health check failed", error=str(e))
        return JSONResponse(
            status_code=503,
            content={
                "status": "unhealthy",
                "database": "failed",
                "error": str(e)
            }
        )


# Register routes
app.include_router(instances.router, prefix="/api/v1/instances", tags=["Instances"])
app.include_router(admin.router, prefix="/admin", tags=["Admin"])
app.include_router(monitoring.router, prefix="/api/v1/monitoring", tags=["Monitoring"])


# Root endpoint
@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "instance-service",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8003,
        reload=True,
        log_level="info"
    ) 