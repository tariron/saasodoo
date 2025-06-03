"""
Health check routes for tenant service
"""

from datetime import datetime
from fastapi import APIRouter, Request, HTTPException
import structlog

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check(request: Request):
    """Health check endpoint"""
    try:
        # Test database connection
        if hasattr(request.app.state, 'db'):
            async with request.app.state.db.pool.acquire() as conn:
                await conn.execute('SELECT 1')
            db_status = "healthy"
        else:
            db_status = "not_initialized"
        
        return {
            "service": "tenant-service",
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "database": db_status,
            "version": "1.0.0"
        }
    
    except Exception as e:
        logger.error("Health check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Service unavailable")


@router.get("/health/detailed")
async def detailed_health_check(request: Request):
    """Detailed health check with component status"""
    try:
        health_data = {
            "service": "tenant-service",
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "components": {}
        }
        
        # Database health
        try:
            if hasattr(request.app.state, 'db'):
                async with request.app.state.db.pool.acquire() as conn:
                    result = await conn.fetchval('SELECT COUNT(*) FROM tenants')
                    health_data["components"]["database"] = {
                        "status": "healthy",
                        "tenant_count": result,
                        "pool_size": len(request.app.state.db.pool._holders) if request.app.state.db.pool else 0
                    }
            else:
                health_data["components"]["database"] = {
                    "status": "not_initialized"
                }
        except Exception as e:
            health_data["components"]["database"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            health_data["status"] = "degraded"
        
        # Docker connectivity (for future instance management)
        try:
            import docker
            client = docker.from_env()
            client.ping()
            health_data["components"]["docker"] = {
                "status": "healthy"
            }
        except Exception as e:
            health_data["components"]["docker"] = {
                "status": "unhealthy",
                "error": str(e)
            }
            # Docker issues shouldn't mark service as unhealthy initially
            # health_data["status"] = "degraded"
        
        return health_data
    
    except Exception as e:
        logger.error("Detailed health check failed", error=str(e))
        raise HTTPException(status_code=503, detail="Service unavailable") 