"""
Monitoring control routes for Docker event monitoring
"""

from datetime import datetime
from typing import Dict, Any, List
from fastapi import APIRouter, Request, HTTPException, Query, Depends
from celery.result import AsyncResult
import structlog

from app.models.events import (
    MonitoringServiceStatus, MonitoringMetrics, ContainerStatusInfo,
    StartMonitoringRequest, StartMonitoringResponse, StopMonitoringResponse,
    ReconciliationRequest, ReconciliationResponse, MonitoringConfiguration,
    EventFilterConfig, MonitoringStatus
)
from app.utils.database import InstanceDatabase
from app.utils.orchestrator_client import get_docker_client  # Uses orchestrator abstraction
from app.tasks.monitoring import (
    monitor_docker_events_task,
    stop_docker_events_monitoring_task,
    update_instance_status_from_event,
    _monitoring_active,
    _k8s_monitor
)

logger = structlog.get_logger(__name__)

router = APIRouter()


def get_database(request: Request) -> InstanceDatabase:
    """Dependency to get database instance"""
    return request.app.state.db


@router.get("/status", response_model=MonitoringServiceStatus)
async def get_monitoring_status():
    """Get current monitoring service status"""
    try:
        global _monitoring_active, _k8s_monitor

        # Determine current status
        if _monitoring_active and _k8s_monitor.is_running:
            status = MonitoringStatus.RUNNING
        elif _monitoring_active and not _k8s_monitor.is_running:
            status = MonitoringStatus.ERROR  # Should be running but isn't
        else:
            status = MonitoringStatus.STOPPED
        
        # Get basic statistics
        docker_client = get_docker_client()
        saasodoo_containers = docker_client.list_saasodoo_containers()
        
        return MonitoringServiceStatus(
            status=status,
            started_at=datetime.utcnow() if status == MonitoringStatus.RUNNING else None,
            containers_monitored=len(saasodoo_containers),
            total_events_processed=0,  # Would be tracked in production
            successful_events=0,
            failed_events=0,
            ignored_events=0,
            duplicate_events=0
        )
        
    except Exception as e:
        logger.error("Failed to get monitoring status", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get monitoring status: {str(e)}")


@router.post("/start", response_model=StartMonitoringResponse)
async def start_monitoring(request: StartMonitoringRequest = StartMonitoringRequest()):
    """Start Docker event monitoring"""
    try:
        global _monitoring_active
        
        if _monitoring_active:
            return StartMonitoringResponse(
                success=True,
                message="Docker event monitoring is already running",
                started_at=datetime.utcnow()
            )
        
        logger.info("Starting Docker event monitoring via API")
        
        # Start monitoring task
        task = monitor_docker_events_task.delay()

        # TODO: Re-implement reconciliation for Kubernetes
        # if request.auto_reconcile:
        #     logger.info("Performing initial status reconciliation")
        #     reconcile_task = reconcile_instance_statuses_task.delay()
        #     logger.info("Initial reconciliation task started", task_id=reconcile_task.id)

        return StartMonitoringResponse(
            success=True,
            message="Docker event monitoring started successfully",
            task_id=task.id,
            started_at=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error("Failed to start monitoring", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to start monitoring: {str(e)}")


@router.post("/stop", response_model=StopMonitoringResponse)
async def stop_monitoring():
    """Stop Docker event monitoring"""
    try:
        global _monitoring_active
        
        if not _monitoring_active:
            return StopMonitoringResponse(
                success=True,
                message="Docker event monitoring is not running",
                stopped_at=datetime.utcnow()
            )
        
        logger.info("Stopping Docker event monitoring via API")
        
        # Stop monitoring task
        task = stop_docker_events_monitoring_task.delay()
        
        # Wait a moment for the task to complete
        try:
            result = task.get(timeout=10)
            logger.info("Monitoring stopped successfully", result=result)
        except Exception as e:
            logger.warning("Failed to wait for stop task completion", error=str(e))
        
        return StopMonitoringResponse(
            success=True,
            message="Docker event monitoring stopped successfully",
            stopped_at=datetime.utcnow()
        )
        
    except Exception as e:
        logger.error("Failed to stop monitoring", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to stop monitoring: {str(e)}")


@router.post("/restart", response_model=StartMonitoringResponse)
async def restart_monitoring(request: StartMonitoringRequest = StartMonitoringRequest()):
    """Restart Docker event monitoring"""
    try:
        logger.info("Restarting Docker event monitoring")
        
        # Stop first
        await stop_monitoring()
        
        # Small delay
        import asyncio
        await asyncio.sleep(2)
        
        # Start again
        return await start_monitoring(request)
        
    except Exception as e:
        logger.error("Failed to restart monitoring", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to restart monitoring: {str(e)}")


@router.post("/reconcile", response_model=ReconciliationResponse)
async def reconcile_statuses(request: ReconciliationRequest = ReconciliationRequest()):
    """Manually trigger status reconciliation"""
    # TODO: Re-implement reconciliation for Kubernetes
    raise HTTPException(
        status_code=501,
        detail="Reconciliation not yet implemented for Kubernetes. Real-time monitoring handles most cases."
    )

    try:
        logger.info("Starting manual status reconciliation",
                   force_update=request.force_update,
                   dry_run=request.dry_run)

        # Start reconciliation task
        # task = reconcile_instance_statuses_task.delay()
        
        # Wait for completion (with timeout)
        try:
            result = task.get(timeout=300)  # 5 minute timeout
            
            return ReconciliationResponse(
                success=True,
                total_checked=result.get('total_checked', 0),
                mismatched=len(result.get('mismatched', [])),
                updated=result.get('updated_count', 0),
                errors=0,  # Would be tracked in production
                details=[],  # Could be populated with detailed results
                completed_at=datetime.utcnow()
            )
            
        except Exception as e:
            logger.error("Reconciliation task failed", error=str(e))
            return ReconciliationResponse(
                success=False,
                total_checked=0,
                mismatched=0,
                updated=0,
                errors=1,
                details=[],
                completed_at=datetime.utcnow()
            )
        
    except Exception as e:
        logger.error("Failed to start reconciliation", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to start reconciliation: {str(e)}")


@router.get("/containers", response_model=List[ContainerStatusInfo])
async def list_monitored_containers():
    """List all monitored SaaS Odoo containers"""
    try:
        docker_client = get_docker_client()
        containers = docker_client.list_saasodoo_containers()
        
        container_status_list = []
        for container in containers:
            # Get health check info
            health_info = docker_client.container_health_check(container['container_name'])
            
            # Parse started_at if available
            started_at = None
            if container.get('created'):
                try:
                    started_at = datetime.fromisoformat(container['created'].replace('Z', '+00:00'))
                except:
                    pass
            
            container_status = ContainerStatusInfo(
                container_name=container['container_name'],
                container_id=container.get('container_id'),
                docker_status=container['status'],
                is_healthy=health_info.get('healthy', False),
                uptime_seconds=health_info.get('uptime'),
                restart_count=health_info.get('restart_count', 0),
                started_at=started_at
            )
            container_status_list.append(container_status)
        
        return container_status_list
        
    except Exception as e:
        logger.error("Failed to list monitored containers", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to list containers: {str(e)}")


@router.get("/containers/{container_name}/status", response_model=ContainerStatusInfo)
async def get_container_status(container_name: str):
    """Get detailed status for a specific container"""
    try:
        docker_client = get_docker_client()
        
        # Check if it's a SaaS Odoo container
        if not docker_client.is_saasodoo_container(container_name):
            raise HTTPException(status_code=400, detail="Not a SaaS Odoo container")
        
        # Get container info
        container_info = docker_client.get_container_info(container_name)
        if not container_info:
            raise HTTPException(status_code=404, detail="Container not found")
        
        # Get health check info
        health_info = docker_client.container_health_check(container_name)
        
        # Parse started_at
        started_at = None
        if container_info.get('started_at'):
            try:
                started_at = datetime.fromisoformat(container_info['started_at'].replace('Z', '+00:00'))
            except:
                pass
        
        return ContainerStatusInfo(
            container_name=container_name,
            container_id=container_info.get('container_id'),
            docker_status=container_info['status'],
            is_healthy=health_info.get('healthy', False),
            uptime_seconds=health_info.get('uptime'),
            restart_count=health_info.get('restart_count', 0),
            started_at=started_at
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get container status", container=container_name, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get container status: {str(e)}")


@router.get("/metrics", response_model=MonitoringMetrics)
async def get_monitoring_metrics():
    """Get monitoring performance metrics"""
    try:
        # This would be implemented with actual metrics collection in production
        # For now, return placeholder values
        return MonitoringMetrics(
            event_processing_latency_ms=25.5,
            events_per_minute=12.3,
            database_update_latency_ms=15.2,
            docker_api_latency_ms=8.7,
            error_rate_percent=0.5,
            uptime_seconds=86400.0  # 24 hours
        )
        
    except Exception as e:
        logger.error("Failed to get monitoring metrics", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get metrics: {str(e)}")


@router.get("/config", response_model=MonitoringConfiguration)
async def get_monitoring_config():
    """Get current monitoring configuration"""
    try:
        # Return default configuration
        # In production, this would be loaded from environment/database
        return MonitoringConfiguration()
        
    except Exception as e:
        logger.error("Failed to get monitoring configuration", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get configuration: {str(e)}")


@router.put("/config", response_model=MonitoringConfiguration)
async def update_monitoring_config(config: MonitoringConfiguration):
    """Update monitoring configuration"""
    try:
        # In production, this would save to database/environment
        logger.info("Monitoring configuration updated", 
                   enabled=config.enabled, 
                   auto_start=config.auto_start,
                   reconciliation_interval=config.reconciliation_interval_minutes)
        
        return config
        
    except Exception as e:
        logger.error("Failed to update monitoring configuration", error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to update configuration: {str(e)}")


@router.get("/tasks/{task_id}/status")
async def get_task_status(task_id: str):
    """Get status of a monitoring task"""
    try:
        result = AsyncResult(task_id)
        
        return {
            "task_id": task_id,
            "status": result.status,
            "result": result.result if result.ready() else None,
            "info": result.info,
            "successful": result.successful() if result.ready() else None,
            "failed": result.failed() if result.ready() else None
        }
        
    except Exception as e:
        logger.error("Failed to get task status", task_id=task_id, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to get task status: {str(e)}")


@router.post("/containers/{container_name}/sync")
async def sync_container_status(container_name: str):
    """Manually sync a specific container's status"""
    try:
        if not get_docker_client().is_saasodoo_container(container_name):
            raise HTTPException(status_code=400, detail="Not a SaaS Odoo container")
        
        logger.info("Manual container status sync requested", container=container_name)
        
        # Get container metadata
        docker_client = get_docker_client()
        container_metadata = docker_client.extract_container_metadata(container_name)
        if not container_metadata:
            raise HTTPException(status_code=400, detail="Invalid container name format")
        
        # Get container status
        container_status = docker_client.get_container_status(container_name)
        if container_status is None:
            raise HTTPException(status_code=404, detail="Container not found")
        
        # Map to instance status
        from app.models.events import map_docker_status_to_instance_status
        instance_status = map_docker_status_to_instance_status(container_status)
        
        # Trigger status update (this would need the instance ID)
        # For now, just return the information
        return {
            "container_name": container_name,
            "docker_status": container_status,
            "mapped_status": instance_status.value,
            "metadata": container_metadata,
            "sync_time": datetime.utcnow().isoformat(),
            "message": "Status sync information retrieved successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to sync container status", container=container_name, error=str(e))
        raise HTTPException(status_code=500, detail=f"Failed to sync container status: {str(e)}")


@router.get("/health")
async def health_check():
    """Health check endpoint for monitoring service"""
    try:
        # Check Docker connectivity
        docker_client = get_docker_client()
        docker_client._ensure_connection()
        
        # Check monitoring status
        global _monitoring_active
        
        health_status = {
            "service": "monitoring",
            "status": "healthy",
            "docker_connection": "ok",
            "monitoring_active": _monitoring_active,
            "timestamp": datetime.utcnow().isoformat()
        }
        
        return health_status
        
    except Exception as e:
        logger.error("Monitoring health check failed", error=str(e))
        return {
            "service": "monitoring",
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.utcnow().isoformat()
        }