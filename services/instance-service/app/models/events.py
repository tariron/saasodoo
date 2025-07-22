"""
Docker event data models and schemas for monitoring
"""

from datetime import datetime
from typing import Dict, Any, Optional, List
from enum import Enum
from uuid import UUID

from pydantic import BaseModel, Field, validator
from app.models.instance import InstanceStatus


class DockerEventType(str, Enum):
    """Docker container event types we monitor"""
    START = "start"
    STOP = "stop"
    DIE = "die"
    KILL = "kill"
    RESTART = "restart"
    PAUSE = "pause"
    UNPAUSE = "unpause"
    CREATE = "create"
    DESTROY = "destroy"


class DockerContainerState(str, Enum):
    """Docker container states"""
    RUNNING = "running"
    EXITED = "exited"
    STOPPED = "stopped"
    PAUSED = "paused"
    RESTARTING = "restarting"
    DEAD = "dead"
    CREATED = "created"
    REMOVING = "removing"


class MonitoringStatus(str, Enum):
    """Monitoring service status"""
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    STOPPED = "stopped"
    ERROR = "error"


class EventProcessingResult(str, Enum):
    """Result of event processing"""
    SUCCESS = "success"
    IGNORED = "ignored"
    FAILED = "failed"
    DUPLICATE = "duplicate"
    NOT_SAASODOO = "not_saasodoo"
    INSTANCE_NOT_FOUND = "instance_not_found"


class ContainerMetadata(BaseModel):
    """Metadata extracted from SaaS Odoo container"""
    container_name: str = Field(..., description="Full container name")
    database_name: str = Field(..., description="Database name from container")
    instance_id_hex: str = Field(..., description="Instance ID hex prefix")
    
    class Config:
        """Pydantic configuration"""
        from_attributes = True


class DockerEventData(BaseModel):
    """Docker event data structure"""
    event_id: str = Field(..., description="Unique event ID")
    event_type: DockerEventType = Field(..., description="Type of Docker event")
    container_name: str = Field(..., description="Container name")
    container_id: str = Field(..., description="Container ID")
    timestamp: datetime = Field(..., description="Event timestamp")
    actor_attributes: Dict[str, Any] = Field(default_factory=dict, description="Actor attributes from Docker event")
    
    class Config:
        """Pydantic configuration"""
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ProcessedEvent(BaseModel):
    """Processed Docker event with additional metadata"""
    event_data: DockerEventData = Field(..., description="Original Docker event data")
    container_metadata: Optional[ContainerMetadata] = Field(None, description="Container metadata if SaaS Odoo container")
    instance_id: Optional[UUID] = Field(None, description="Full instance UUID if found")
    old_status: Optional[InstanceStatus] = Field(None, description="Previous instance status")
    new_status: Optional[InstanceStatus] = Field(None, description="New instance status")
    processing_result: EventProcessingResult = Field(..., description="Processing result")
    processing_message: Optional[str] = Field(None, description="Processing message or error")
    processed_at: datetime = Field(default_factory=datetime.utcnow, description="Processing timestamp")
    
    class Config:
        """Pydantic configuration"""
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat(),
            UUID: lambda v: str(v)
        }


class ContainerStatusInfo(BaseModel):
    """Container status information"""
    container_name: str = Field(..., description="Container name")
    container_id: Optional[str] = Field(None, description="Container ID")
    docker_status: DockerContainerState = Field(..., description="Docker container status")
    instance_status: Optional[InstanceStatus] = Field(None, description="Corresponding instance status")
    is_healthy: bool = Field(..., description="Container health status")
    uptime_seconds: Optional[float] = Field(None, description="Container uptime in seconds")
    restart_count: int = Field(default=0, description="Container restart count")
    started_at: Optional[datetime] = Field(None, description="Container start timestamp")
    last_checked: datetime = Field(default_factory=datetime.utcnow, description="Last health check timestamp")
    
    class Config:
        """Pydantic configuration"""
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class StatusReconciliation(BaseModel):
    """Status reconciliation result"""
    instance_id: UUID = Field(..., description="Instance UUID")
    container_name: str = Field(..., description="Expected container name")
    database_status: InstanceStatus = Field(..., description="Status in database")
    docker_status: Optional[DockerContainerState] = Field(None, description="Docker container status")
    expected_status: Optional[InstanceStatus] = Field(None, description="Expected instance status based on Docker")
    needs_update: bool = Field(..., description="Whether database needs to be updated")
    updated: bool = Field(default=False, description="Whether update was performed")
    error_message: Optional[str] = Field(None, description="Error message if update failed")
    
    class Config:
        """Pydantic configuration"""
        from_attributes = True
        json_encoders = {
            UUID: lambda v: str(v)
        }


class MonitoringServiceStatus(BaseModel):
    """Monitoring service status information"""
    status: MonitoringStatus = Field(..., description="Current monitoring status")
    started_at: Optional[datetime] = Field(None, description="Service start time")
    last_event_time: Optional[datetime] = Field(None, description="Last processed event time")
    total_events_processed: int = Field(default=0, description="Total events processed")
    successful_events: int = Field(default=0, description="Successfully processed events")
    failed_events: int = Field(default=0, description="Failed event processing")
    ignored_events: int = Field(default=0, description="Ignored events")
    duplicate_events: int = Field(default=0, description="Duplicate events")
    containers_monitored: int = Field(default=0, description="Number of containers being monitored")
    last_reconciliation: Optional[datetime] = Field(None, description="Last reconciliation timestamp")
    
    class Config:
        """Pydantic configuration"""
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class MonitoringMetrics(BaseModel):
    """Monitoring performance metrics"""
    event_processing_latency_ms: float = Field(..., description="Average event processing latency in milliseconds")
    events_per_minute: float = Field(..., description="Events processed per minute")
    database_update_latency_ms: float = Field(..., description="Average database update latency in milliseconds")
    docker_api_latency_ms: float = Field(..., description="Average Docker API call latency in milliseconds")
    error_rate_percent: float = Field(..., description="Error rate percentage")
    uptime_seconds: float = Field(..., description="Service uptime in seconds")
    memory_usage_mb: Optional[float] = Field(None, description="Memory usage in MB")
    cpu_usage_percent: Optional[float] = Field(None, description="CPU usage percentage")
    
    class Config:
        """Pydantic configuration"""
        from_attributes = True


class EventFilterConfig(BaseModel):
    """Configuration for event filtering"""
    monitored_events: List[DockerEventType] = Field(
        default=[
            DockerEventType.START,
            DockerEventType.STOP,
            DockerEventType.DIE,
            DockerEventType.KILL,
            DockerEventType.RESTART,
            DockerEventType.PAUSE,
            DockerEventType.UNPAUSE
        ],
        description="List of Docker events to monitor"
    )
    container_name_pattern: str = Field(
        default=r'^odoo_([^_]+)_([a-f0-9]{8})$',
        description="Regex pattern for SaaS Odoo container names"
    )
    ignore_system_containers: bool = Field(default=True, description="Ignore system containers")
    deduplication_window_seconds: int = Field(default=5, description="Event deduplication window in seconds")
    
    class Config:
        """Pydantic configuration"""
        from_attributes = True


class MonitoringConfiguration(BaseModel):
    """Complete monitoring configuration"""
    enabled: bool = Field(default=True, description="Whether monitoring is enabled")
    auto_start: bool = Field(default=True, description="Auto-start monitoring on service startup")
    event_filter: EventFilterConfig = Field(default_factory=EventFilterConfig, description="Event filtering configuration")
    reconciliation_interval_minutes: int = Field(default=15, description="Status reconciliation interval in minutes")
    max_event_processing_threads: int = Field(default=5, description="Maximum event processing threads")
    database_update_timeout_seconds: int = Field(default=30, description="Database update timeout in seconds")
    docker_api_timeout_seconds: int = Field(default=10, description="Docker API call timeout in seconds")
    health_check_interval_seconds: int = Field(default=60, description="Container health check interval in seconds")
    
    class Config:
        """Pydantic configuration"""
        from_attributes = True


# Status mapping utilities
DOCKER_STATUS_TO_INSTANCE_STATUS = {
    DockerContainerState.RUNNING: InstanceStatus.RUNNING,
    DockerContainerState.EXITED: InstanceStatus.STOPPED,
    DockerContainerState.STOPPED: InstanceStatus.STOPPED,
    DockerContainerState.PAUSED: InstanceStatus.SUSPENDED,
    DockerContainerState.RESTARTING: InstanceStatus.RESTARTING,
    DockerContainerState.DEAD: InstanceStatus.ERROR,
    DockerContainerState.CREATED: InstanceStatus.CREATING,
    DockerContainerState.REMOVING: InstanceStatus.TERMINATED,
}

EVENT_TYPE_TO_INSTANCE_STATUS = {
    DockerEventType.START: InstanceStatus.RUNNING,
    DockerEventType.STOP: InstanceStatus.STOPPED,
    DockerEventType.DIE: InstanceStatus.STOPPED,
    DockerEventType.KILL: InstanceStatus.STOPPED,
    DockerEventType.RESTART: InstanceStatus.RUNNING,
    DockerEventType.PAUSE: InstanceStatus.SUSPENDED,
    DockerEventType.UNPAUSE: InstanceStatus.RUNNING,
    DockerEventType.CREATE: InstanceStatus.CREATING,
    DockerEventType.DESTROY: InstanceStatus.TERMINATED,
}


def map_docker_status_to_instance_status(docker_status: str) -> InstanceStatus:
    """Map Docker container status to instance status"""
    try:
        docker_state = DockerContainerState(docker_status.lower())
        return DOCKER_STATUS_TO_INSTANCE_STATUS.get(docker_state, InstanceStatus.ERROR)
    except ValueError:
        return InstanceStatus.ERROR


def map_event_type_to_instance_status(event_type: str) -> InstanceStatus:
    """Map Docker event type to instance status"""
    try:
        docker_event = DockerEventType(event_type.lower())
        return EVENT_TYPE_TO_INSTANCE_STATUS.get(docker_event, InstanceStatus.ERROR)
    except ValueError:
        return InstanceStatus.ERROR


def should_process_event(event_type: str, monitored_events: List[DockerEventType]) -> bool:
    """Check if event type should be processed"""
    try:
        docker_event = DockerEventType(event_type.lower())
        return docker_event in monitored_events
    except ValueError:
        return False


# Request/Response schemas for API endpoints
class StartMonitoringRequest(BaseModel):
    """Request to start monitoring"""
    auto_reconcile: bool = Field(default=True, description="Perform initial reconciliation on start")
    
    class Config:
        """Pydantic configuration"""
        from_attributes = True


class StartMonitoringResponse(BaseModel):
    """Response for start monitoring request"""
    success: bool = Field(..., description="Whether monitoring started successfully")
    message: str = Field(..., description="Status message")
    task_id: Optional[str] = Field(None, description="Celery task ID")
    started_at: datetime = Field(..., description="Start timestamp")
    
    class Config:
        """Pydantic configuration"""
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class StopMonitoringResponse(BaseModel):
    """Response for stop monitoring request"""
    success: bool = Field(..., description="Whether monitoring stopped successfully")
    message: str = Field(..., description="Status message")
    stopped_at: datetime = Field(..., description="Stop timestamp")
    
    class Config:
        """Pydantic configuration"""
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }


class ReconciliationRequest(BaseModel):
    """Request for manual status reconciliation"""
    force_update: bool = Field(default=False, description="Force update even if statuses match")
    dry_run: bool = Field(default=False, description="Only report mismatches, don't update")
    
    class Config:
        """Pydantic configuration"""
        from_attributes = True


class ReconciliationResponse(BaseModel):
    """Response for reconciliation request"""
    success: bool = Field(..., description="Whether reconciliation completed successfully")
    total_checked: int = Field(..., description="Total instances checked")
    mismatched: int = Field(..., description="Number of status mismatches found")
    updated: int = Field(..., description="Number of statuses updated")
    errors: int = Field(..., description="Number of errors encountered")
    details: List[StatusReconciliation] = Field(default_factory=list, description="Detailed reconciliation results")
    completed_at: datetime = Field(..., description="Completion timestamp")
    
    class Config:
        """Pydantic configuration"""
        from_attributes = True
        json_encoders = {
            datetime: lambda v: v.isoformat()
        }