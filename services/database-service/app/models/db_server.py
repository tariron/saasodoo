"""
SQLAlchemy model for db_servers table
Represents PostgreSQL database server pools for dynamic allocation
"""

import enum
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy import (
    Column, String, Integer, Boolean, DateTime, Enum as SQLEnum,
    CheckConstraint, UUID as SQLUUID, Text
)
from sqlalchemy.orm import declarative_base
from sqlalchemy.sql import func
import uuid

Base = declarative_base()


class ServerType(str, enum.Enum):
    """Type of database server"""
    PLATFORM = "platform"      # Internal platform database
    SHARED = "shared"          # Multi-tenant shared pool
    DEDICATED = "dedicated"     # Single customer dedicated server


class ServerStatus(str, enum.Enum):
    """Lifecycle status of database server"""
    PROVISIONING = "provisioning"      # Being created
    INITIALIZING = "initializing"      # Docker service created, waiting for ready
    ACTIVE = "active"                  # Healthy and accepting allocations
    FULL = "full"                      # At capacity, no more allocations
    MAINTENANCE = "maintenance"        # Temporarily unavailable for allocations
    ERROR = "error"                    # Health checks failing
    DEPROVISIONING = "deprovisioning"  # Being removed


class HealthStatus(str, enum.Enum):
    """Health check status"""
    HEALTHY = "healthy"        # All health checks passing
    DEGRADED = "degraded"      # Some health checks failing (failures < 3)
    UNHEALTHY = "unhealthy"    # Health checks consistently failing (failures >= 3)
    UNKNOWN = "unknown"        # Not yet checked or status unclear


class AllocationStrategy(str, enum.Enum):
    """How this server should be used for allocation"""
    AUTO = "auto"      # Available for automatic allocation
    MANUAL = "manual"  # Admin-controlled, not for automatic allocation


class DBServer(Base):
    """
    Database Server Pool Model
    Represents a PostgreSQL server (Docker Swarm service) that hosts multiple Odoo instance databases
    """
    __tablename__ = "db_servers"

    # Identity
    id = Column(SQLUUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(100), unique=True, nullable=False, index=True)
    host = Column(String(255), nullable=False)
    port = Column(Integer, default=5432, nullable=False)

    # Type & Capacity
    server_type = Column(SQLEnum(ServerType), nullable=False)
    max_instances = Column(Integer, nullable=False, default=50)
    current_instances = Column(Integer, nullable=False, default=0)

    # Docker Swarm Metadata
    swarm_service_id = Column(String(255), nullable=True)
    swarm_service_name = Column(String(255), nullable=True)
    node_placement = Column(String(255), default="node.labels.role==database")

    # Status
    status = Column(SQLEnum(ServerStatus), nullable=False, default=ServerStatus.PROVISIONING)
    health_status = Column(SQLEnum(HealthStatus), default=HealthStatus.UNKNOWN)
    last_health_check = Column(DateTime(timezone=True), nullable=True)
    health_check_failures = Column(Integer, default=0, nullable=False)

    # Resources
    cpu_limit = Column(String(10), default="2")
    memory_limit = Column(String(10), default="4G")
    storage_path = Column(String(500), nullable=True)
    allocated_storage_gb = Column(Integer, default=0)

    # PostgreSQL Configuration
    postgres_version = Column(String(10), default="18")
    postgres_image = Column(String(100), default="postgres:18-alpine")

    # Allocation Strategy
    allocation_strategy = Column(SQLEnum(AllocationStrategy), default=AllocationStrategy.AUTO)
    priority = Column(Integer, default=100, nullable=False)  # Lower = higher priority

    # Dedicated Server Tracking (nullable - only for dedicated servers)
    dedicated_to_customer_id = Column(SQLUUID(as_uuid=True), nullable=True)
    dedicated_to_instance_id = Column(SQLUUID(as_uuid=True), nullable=True)

    # Audit Fields
    provisioned_by = Column(String(100), nullable=True)
    provisioned_at = Column(DateTime(timezone=True), default=func.now())
    last_allocated_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    # Table-level constraints (enforced in database schema as well)
    __table_args__ = (
        CheckConstraint('current_instances >= 0', name='check_current_instances_non_negative'),
        CheckConstraint('current_instances <= max_instances', name='check_capacity'),
        CheckConstraint('health_check_failures >= 0', name='check_failures_non_negative'),
        CheckConstraint('allocated_storage_gb >= 0', name='check_storage_non_negative'),
        CheckConstraint('priority >= 0', name='check_priority_non_negative'),
    )

    def is_available(self) -> bool:
        """
        Check if this server is available for allocation

        Returns:
            True if server is healthy, active, and has capacity
        """
        return (
            self.status == ServerStatus.ACTIVE
            and self.health_status in (HealthStatus.HEALTHY, HealthStatus.UNKNOWN)
            and self.current_instances < self.max_instances
            and self.allocation_strategy == AllocationStrategy.AUTO
        )

    def is_full(self) -> bool:
        """
        Check if server is at capacity

        Returns:
            True if current_instances equals or exceeds max_instances
        """
        return self.current_instances >= self.max_instances

    def get_capacity_percentage(self) -> float:
        """
        Calculate capacity utilization percentage

        Returns:
            Percentage of capacity used (0.0 to 100.0)
        """
        if self.max_instances == 0:
            return 100.0
        return (self.current_instances / self.max_instances) * 100.0

    def increment_instance_count(self, session) -> None:
        """
        Increment the instance count and update status if at capacity

        Args:
            session: SQLAlchemy session for database operations

        Raises:
            ValueError: If already at capacity
        """
        if self.is_full():
            raise ValueError(f"Server {self.name} is already at capacity ({self.current_instances}/{self.max_instances})")

        self.current_instances += 1
        self.last_allocated_at = datetime.utcnow()

        # Update status to FULL if we just reached capacity
        if self.is_full():
            self.status = ServerStatus.FULL

        session.commit()

    def decrement_instance_count(self, session) -> None:
        """
        Decrement the instance count and update status if no longer full

        Args:
            session: SQLAlchemy session for database operations

        Raises:
            ValueError: If count is already zero
        """
        if self.current_instances == 0:
            raise ValueError(f"Server {self.name} instance count is already zero")

        was_full = self.is_full()
        self.current_instances -= 1

        # Update status to ACTIVE if we were full and now have capacity
        if was_full and not self.is_full() and self.status == ServerStatus.FULL:
            self.status = ServerStatus.ACTIVE

        session.commit()

    def mark_healthy(self, session) -> None:
        """
        Mark server as healthy and reset failure counter

        Args:
            session: SQLAlchemy session for database operations
        """
        self.health_status = HealthStatus.HEALTHY
        self.health_check_failures = 0
        self.last_health_check = datetime.utcnow()

        # If server was in initializing state and is now healthy, promote to active
        if self.status == ServerStatus.INITIALIZING:
            self.status = ServerStatus.ACTIVE

        session.commit()

    def mark_unhealthy(self, session) -> None:
        """
        Increment failure counter and update health status

        Args:
            session: SQLAlchemy session for database operations
        """
        self.health_check_failures += 1
        self.last_health_check = datetime.utcnow()

        # Update health status based on failure count
        if self.health_check_failures >= 3:
            self.health_status = HealthStatus.UNHEALTHY
            # Mark server as error if it was active
            if self.status == ServerStatus.ACTIVE:
                self.status = ServerStatus.ERROR
        else:
            self.health_status = HealthStatus.DEGRADED

        session.commit()

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert model to dictionary for JSON serialization

        Returns:
            Dictionary representation of the server
        """
        return {
            "id": str(self.id),
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "server_type": self.server_type.value if self.server_type else None,
            "max_instances": self.max_instances,
            "current_instances": self.current_instances,
            "capacity_percentage": round(self.get_capacity_percentage(), 2),
            "is_available": self.is_available(),
            "is_full": self.is_full(),
            "swarm_service_id": self.swarm_service_id,
            "swarm_service_name": self.swarm_service_name,
            "node_placement": self.node_placement,
            "status": self.status.value if self.status else None,
            "health_status": self.health_status.value if self.health_status else None,
            "last_health_check": self.last_health_check.isoformat() if self.last_health_check else None,
            "health_check_failures": self.health_check_failures,
            "cpu_limit": self.cpu_limit,
            "memory_limit": self.memory_limit,
            "storage_path": self.storage_path,
            "allocated_storage_gb": self.allocated_storage_gb,
            "postgres_version": self.postgres_version,
            "postgres_image": self.postgres_image,
            "allocation_strategy": self.allocation_strategy.value if self.allocation_strategy else None,
            "priority": self.priority,
            "dedicated_to_customer_id": str(self.dedicated_to_customer_id) if self.dedicated_to_customer_id else None,
            "dedicated_to_instance_id": str(self.dedicated_to_instance_id) if self.dedicated_to_instance_id else None,
            "provisioned_by": self.provisioned_by,
            "provisioned_at": self.provisioned_at.isoformat() if self.provisioned_at else None,
            "last_allocated_at": self.last_allocated_at.isoformat() if self.last_allocated_at else None,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
        }

    def __repr__(self) -> str:
        """String representation for debugging"""
        return (
            f"<DBServer(name='{self.name}', type='{self.server_type.value if self.server_type else None}', "
            f"status='{self.status.value if self.status else None}', "
            f"instances={self.current_instances}/{self.max_instances})>"
        )
