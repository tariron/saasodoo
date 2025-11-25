"""
Docker event monitoring tasks for real-time instance status synchronization
"""

import os
import re
import asyncio
import asyncpg
import docker
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Set
from uuid import UUID
from threading import Thread, Event as ThreadEvent
import time

from app.celery_config import celery_app
from app.models.instance import InstanceStatus
import structlog

logger = structlog.get_logger(__name__)

# Global monitoring state
_monitoring_active = False
_monitor_thread: Optional[Thread] = None
_stop_event = ThreadEvent()


class DockerEventMonitor:
    """Real-time Docker event monitoring for instance status synchronization"""
    
    def __init__(self):
        self.client = None
        self.is_running = False
        self.stop_event = ThreadEvent()
        self.last_event_time = {}  # For deduplication
        self.processed_events: Set[str] = set()  # Event deduplication
        
        # Service name pattern for Swarm: odoo-{database_name}-{instance_id.hex[:8]}
        self.service_pattern = re.compile(r'^odoo-([^-]+)-([a-f0-9]{8})$')
        # Deprecated: Old container pattern (keep for compatibility)
        self.container_pattern = re.compile(r'^odoo_([^_]+)_([a-f0-9]{8})$')

        # Service event to status mapping (Swarm mode)
        self.service_event_map = {
            'create': InstanceStatus.CREATING,
            'remove': InstanceStatus.TERMINATED,
            # 'update' requires checking task states - handled separately
        }

        # Legacy container event mapping (deprecated)
        self.event_status_map = {
            'start': InstanceStatus.RUNNING,
            'die': InstanceStatus.STOPPED,
            'kill': InstanceStatus.STOPPED,
            'stop': InstanceStatus.STOPPED,
            'restart': InstanceStatus.RUNNING,
            'pause': InstanceStatus.PAUSED,
            'unpause': InstanceStatus.RUNNING,
            'destroy': InstanceStatus.CONTAINER_MISSING,
        }
    
    def _init_docker_client(self):
        """Initialize Docker client with error handling"""
        try:
            self.client = docker.from_env()
            # Test connection
            self.client.ping()
            logger.info("Docker client initialized successfully")
        except Exception as e:
            logger.error("Failed to initialize Docker client", error=str(e))
            raise
    
    def _is_saasodoo_service(self, service_name: str) -> Optional[Dict[str, str]]:
        """Check if service is a SaaS Odoo instance and extract metadata"""
        match = self.service_pattern.match(service_name)
        if match:
            database_name, instance_id_hex = match.groups()
            return {
                'database_name': database_name,
                'instance_id_hex': instance_id_hex,
                'service_name': service_name
            }
        return None

    def _is_saasodoo_container(self, container_name: str) -> Optional[Dict[str, str]]:
        """DEPRECATED: Check if container is a SaaS Odoo instance (legacy)"""
        match = self.container_pattern.match(container_name)
        if match:
            database_name, instance_id_hex = match.groups()
            return {
                'database_name': database_name,
                'instance_id_hex': instance_id_hex,
                'container_name': container_name
            }
        return None
    
    def _get_instance_id_from_hex(self, instance_id_hex: str) -> Optional[str]:
        """Convert hex instance ID back to full UUID by querying database"""
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop.run_until_complete(self._query_instance_id_by_hex(instance_id_hex))
        except Exception as e:
            logger.error("Failed to get instance ID from hex", hex=instance_id_hex, error=str(e))
            return None
        finally:
            loop.close()
    
    async def _query_instance_id_by_hex(self, instance_id_hex: str) -> Optional[str]:
        """Query database for full instance ID using hex prefix"""
        try:
            conn = await self._get_db_connection()
            try:
                # Query for instance where UUID starts with the hex prefix
                instance_id = await conn.fetchval("""
                    SELECT id::text FROM instances 
                    WHERE id::text LIKE $1 
                    LIMIT 1
                """, f"%{instance_id_hex}%")
                
                if instance_id:
                    logger.debug("Found instance ID from hex", hex=instance_id_hex, instance_id=instance_id)
                    return instance_id
                else:
                    logger.warning("No instance found for hex prefix", hex=instance_id_hex)
                    return None
            finally:
                await conn.close()
        except Exception as e:
            logger.error("Database query failed for hex lookup", hex=instance_id_hex, error=str(e))
            return None
    
    async def _get_db_connection(self):
        """Get database connection using existing patterns"""
        db_config = {
            'host': os.getenv('POSTGRES_HOST', 'postgres'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'database': os.getenv('POSTGRES_DB', 'instance'),
            'user': os.getenv('DB_SERVICE_USER', 'instance_service'),
            'password': os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me'),
        }
        return await asyncpg.connect(**db_config)
    
    def _should_process_event(self, event_id: str, container_name: str, event_type: str) -> bool:
        """Check if event should be processed (deduplication)"""
        # Create unique event key
        event_key = f"{container_name}_{event_type}_{event_id}_{int(time.time() // 5)}"  # 5-second window
        
        if event_key in self.processed_events:
            logger.debug("Duplicate event ignored", event_key=event_key)
            return False
        
        # Add to processed events and clean old ones
        self.processed_events.add(event_key)
        
        # Clean events older than 60 seconds
        current_time = int(time.time() // 5)
        self.processed_events = {
            key for key in self.processed_events 
            if int(key.split('_')[-1]) > current_time - 12  # 60 seconds / 5 = 12 intervals
        }
        
        return True
    
    def _process_service_event(self, event: Dict[str, Any]):
        """Process a Docker Swarm service event"""
        try:
            event_type = event.get('Action', '').lower()
            service_name = event.get('Actor', {}).get('Attributes', {}).get('name', '')
            event_id = event.get('id', '')

            # LOG ALL SERVICE EVENTS
            logger.info("SERVICE EVENT RECEIVED",
                       event_type=event_type,
                       service=service_name,
                       event_id=event_id[:8] if event_id else 'none')

            if not service_name or not event_type:
                logger.debug("Event missing name/type", event_type=event_type, service=service_name)
                return

            # Check if this is a SaaS Odoo service
            service_info = self._is_saasodoo_service(service_name)
            if not service_info:
                logger.debug("Event ignored - not SaaS service",
                            event_type=event_type,
                            service=service_name)
                return

            logger.info("SaaS service event detected",
                       event_type=event_type,
                       service=service_name,
                       instance_hex=service_info['instance_id_hex'])

            # Deduplication check
            if not self._should_process_event(event_id, service_name, event_type):
                logger.debug("Event deduplicated",
                            event_type=event_type,
                            service=service_name,
                            event_id=event_id[:8] if event_id else 'none')
                return

            logger.info("Event passed deduplication",
                       event_type=event_type,
                       service=service_name)

            # Get full instance ID
            instance_id = self._get_instance_id_from_hex(service_info['instance_id_hex'])
            if not instance_id:
                logger.warning("Could not resolve instance ID from service",
                             service=service_name,
                             hex=service_info['instance_id_hex'])
                return

            # Handle service events
            if event_type == 'create':
                new_status = InstanceStatus.CREATING
                logger.info("Service created - setting status to CREATING",
                           service=service_name,
                           instance_id=instance_id)
                update_instance_status_from_event.delay(
                    instance_id,
                    new_status.value,
                    event_type,
                    service_name,
                    event.get('time', datetime.utcnow().isoformat())
                )

            elif event_type == 'remove':
                new_status = InstanceStatus.TERMINATED
                logger.info("Service removed - setting status to TERMINATED",
                           service=service_name,
                           instance_id=instance_id)
                update_instance_status_from_event.delay(
                    instance_id,
                    new_status.value,
                    event_type,
                    service_name,
                    event.get('time', datetime.utcnow().isoformat())
                )

            elif event_type == 'update':
                # Service update → check task states to determine status
                # IMPORTANT: Non-blocking - queues a separate task with 2-second delay for state settling
                logger.info("Service updated - queueing targeted state check",
                           service=service_name,
                           instance_id=instance_id)
                check_service_task_state_and_health.apply_async(
                    args=[instance_id, service_name],
                    countdown=2  # 2-second delay to let Docker Swarm state settle
                )

        except Exception as e:
            logger.error("Failed to process service event", error=str(e), event=event)

    def _process_container_event(self, event: Dict[str, Any]):
        """DEPRECATED: Process container event (legacy compatibility)"""
        try:
            event_type = event.get('Action', '').lower()
            container_name = event.get('Actor', {}).get('Attributes', {}).get('name', '')
            event_id = event.get('id', '')

            # LOG ALL EVENTS - including destroy events
            logger.info("CONTAINER EVENT RECEIVED (DEPRECATED)",
                       event_type=event_type,
                       container=container_name,
                       event_id=event_id[:8] if event_id else 'none')

            if not container_name or not event_type:
                logger.debug("Event missing name/type", event_type=event_type, container=container_name)
                return

            # Check if this is a SaaS Odoo container
            container_info = self._is_saasodoo_container(container_name)
            if not container_info:
                logger.debug("Event ignored - not SaaS container",
                            event_type=event_type,
                            container=container_name)
                return

            logger.info("SaaS container event detected",
                       event_type=event_type,
                       container=container_name,
                       instance_hex=container_info['instance_id_hex'])

            # Deduplication check
            if not self._should_process_event(event_id, container_name, event_type):
                logger.debug("Event deduplicated",
                            event_type=event_type,
                            container=container_name,
                            event_id=event_id[:8] if event_id else 'none')
                return

            logger.info("Event passed deduplication",
                       event_type=event_type,
                       container=container_name)

            # Map event to status
            if event_type not in self.event_status_map:
                logger.warning("Unknown container event type",
                              event_type=event_type,
                              container=container_name,
                              available_events=list(self.event_status_map.keys()))
                return

            new_status = self.event_status_map[event_type]
            logger.info("Event mapped to status",
                       event_type=event_type,
                       container=container_name,
                       new_status=new_status.value)

            logger.info("Processing container event",
                       event_type=event_type,
                       container=container_name,
                       new_status=new_status.value,
                       instance_hex=container_info['instance_id_hex'])

            # Get full instance ID
            instance_id = self._get_instance_id_from_hex(container_info['instance_id_hex'])
            if not instance_id:
                logger.warning("Could not resolve instance ID from container",
                             container=container_name,
                             hex=container_info['instance_id_hex'])
                return

            # Schedule database update task
            update_instance_status_from_event.delay(
                instance_id,
                new_status.value,
                event_type,
                container_name,
                event.get('time', datetime.utcnow().isoformat())
            )
            
            # For kill events, schedule a delayed check to see if container was actually destroyed
            if event_type == 'kill':
                check_container_destroyed.apply_async(
                    args=[instance_id, container_name],
                    countdown=3  # Wait 3 seconds after kill event
                )
            
        except Exception as e:
            logger.error("Failed to process container event", error=str(e), event=event)
    
    def start_monitoring(self):
        """Start Docker event monitoring"""
        if self.is_running:
            logger.warning("Event monitoring is already running")
            return
        
        try:
            self._init_docker_client()
            self.is_running = True
            self.stop_event.clear()
            
            logger.info("Starting Docker event monitoring")
            
            # Start monitoring in separate thread
            monitor_thread = Thread(target=self._monitor_events, daemon=True)
            monitor_thread.start()
            
        except Exception as e:
            logger.error("Failed to start Docker event monitoring", error=str(e))
            self.is_running = False
            raise
    
    def stop_monitoring(self):
        """Stop Docker event monitoring"""
        if not self.is_running:
            return
        
        logger.info("Stopping Docker event monitoring")
        self.is_running = False
        self.stop_event.set()
    
    def _monitor_events(self):
        """Main event monitoring loop (runs in separate thread)"""
        try:
            # Listen for service events (Swarm mode)
            event_filters = {
                'type': 'service',
                'event': ['create', 'update', 'remove']
            }

            logger.info("Starting Docker Swarm service event stream", filters=event_filters)

            # Start event stream
            for event in self.client.events(decode=True, filters=event_filters):
                if self.stop_event.is_set():
                    logger.info("Stop event received, exiting monitor loop")
                    break

                self._process_service_event(event)
                
        except Exception as e:
            logger.error("Docker event monitoring failed", error=str(e))
            self.is_running = False
        finally:
            logger.info("Docker event monitoring stopped")


# Global monitor instance
_docker_monitor = DockerEventMonitor()


@celery_app.task(bind=True)
def monitor_docker_events_task(self):
    """Celery task to start Docker event monitoring"""
    try:
        global _monitoring_active, _monitor_thread, _stop_event
        
        if _monitoring_active:
            return {"status": "already_running", "message": "Docker event monitoring is already active"}
        
        logger.info("Starting Docker event monitoring task", task_id=self.request.id)
        
        _monitoring_active = True
        _stop_event.clear()
        
        # Start monitoring
        _docker_monitor.start_monitoring()
        
        return {
            "status": "started", 
            "message": "Docker event monitoring started successfully",
            "task_id": self.request.id
        }
        
    except Exception as e:
        logger.error("Failed to start Docker event monitoring task", error=str(e))
        _monitoring_active = False
        raise


@celery_app.task(bind=True)
def stop_docker_events_monitoring_task(self):
    """Celery task to stop Docker event monitoring"""
    try:
        global _monitoring_active, _docker_monitor
        
        if not _monitoring_active:
            return {"status": "not_running", "message": "Docker event monitoring is not active"}
        
        logger.info("Stopping Docker event monitoring task", task_id=self.request.id)
        
        _docker_monitor.stop_monitoring()
        _monitoring_active = False
        
        return {
            "status": "stopped", 
            "message": "Docker event monitoring stopped successfully",
            "task_id": self.request.id
        }
        
    except Exception as e:
        logger.error("Failed to stop Docker event monitoring task", error=str(e))
        raise


@celery_app.task(bind=True)
def check_service_task_state_and_health(self, instance_id: str, service_name: str):
    """
    Check Docker service task states and queue health check if needed

    This task is triggered by service 'update' events and determines
    whether the service is running, stopped, or in another state.

    IMPORTANT: This task does NOT block on health checks. Instead, it queues
    a separate health check task if the service is being scaled up.
    """
    try:
        logger.info("Checking service task state",
                   instance_id=instance_id,
                   service_name=service_name,
                   task_id=self.request.id)

        result = asyncio.run(_check_service_task_state_and_health(instance_id, service_name))

        logger.info("Service task state check completed",
                   instance_id=instance_id,
                   result=result,
                   task_id=self.request.id)

        return result
    except Exception as e:
        logger.error("Failed to check service task state",
                    instance_id=instance_id,
                    service_name=service_name,
                    error=str(e),
                    task_id=self.request.id)
        raise


async def _check_service_task_state_and_health(instance_id: str, service_name: str) -> Dict[str, Any]:
    """
    Analyze service task states and queue health check if upscale detected

    Rules:
    - If running tasks > 0 AND current_status in [starting, restarting, stopped] → queue health check task
    - If running tasks == 0 AND current_status == stopping → set to stopped immediately
    - If failed tasks > 0 AND no running tasks → set to error immediately
    - Otherwise → no change (avoid interfering with update/restore operations)

    IMPORTANT: Does NOT perform health check directly - queues separate task
    IMPORTANT: Handles manual DevOps operations (stopped → starting)
    """
    try:
        # Get current instance and network info from DB
        conn = await _get_db_connection()
        try:
            instance_row = await conn.fetchrow(
                "SELECT status, internal_url, database_name FROM instances WHERE id = $1",
                UUID(instance_id)
            )

            if not instance_row:
                logger.warning("Instance not found", instance_id=instance_id)
                return {"updated": False, "reason": "instance_not_found"}

            current_status = instance_row['status']
            internal_url = instance_row['internal_url']
            database_name = instance_row['database_name']

            # Skip if instance is terminated (final state)
            if current_status == 'terminated':
                return {"updated": False, "reason": "instance_terminated"}

            # Get Docker service and task states
            client = docker.from_env()
            service = client.services.get(service_name)

            # Filter for running tasks only to reduce payload size
            tasks = service.tasks(filters={'desired-state': 'running'})

            # Tasks in these states indicate the service is being/is scaled up
            # Docker task lifecycle: new → pending → assigned → preparing → starting → running
            active_task_states = ['preparing', 'starting', 'running']
            running_tasks = [t for t in tasks if t['Status']['State'] == 'running']
            active_tasks = [t for t in tasks if t['Status']['State'] in active_task_states]
            failed_tasks = [t for t in tasks if t['Status']['State'] == 'failed']

            # Also get all tasks to check for failures/shutdown
            all_tasks = service.tasks()
            all_failed_tasks = [t for t in all_tasks if t['Status']['State'] == 'failed']

            # Determine target status based on task states and current status
            target_status = None
            should_queue_health_check = False

            # Rule 1: Upscale detected from lifecycle operation (starting/restarting)
            # Check for active tasks (preparing/starting/running), not just running tasks
            if len(active_tasks) > 0 and current_status in ['starting', 'restarting']:
                # Don't update to RUNNING yet - queue health check task instead
                should_queue_health_check = True
                logger.info("Detected upscale from lifecycle operation - queueing health check",
                          instance_id=instance_id,
                          current_status=current_status,
                          active_tasks=len(active_tasks),
                          running_tasks=len(running_tasks))

            # Rule 1b: Manual DevOps scale-up detected (stopped → starting)
            elif len(active_tasks) > 0 and current_status == 'stopped':
                # First transition to 'starting' to indicate manual operation detected
                logger.info("Manual DevOps scale-up detected",
                          instance_id=instance_id,
                          running_tasks=len(running_tasks))

                await conn.execute("""
                    UPDATE instances
                    SET status = $1, updated_at = $2
                    WHERE id = $3
                """, InstanceStatus.STARTING.value, datetime.utcnow(), UUID(instance_id))

                # Queue health check to transition from starting → running
                should_queue_health_check = True

            # Rule 2: Transition from stopping to stopped
            elif len(running_tasks) == 0 and current_status == 'stopping':
                target_status = InstanceStatus.STOPPED.value
                logger.info("Transitioning to STOPPED",
                          instance_id=instance_id,
                          current_status=current_status)

            # Rule 3: Detect failures
            elif len(all_failed_tasks) > 0 and len(running_tasks) == 0:
                target_status = InstanceStatus.ERROR.value
                error_msg = f"Service tasks failed: {len(all_failed_tasks)} failed tasks"
                logger.error("Service failure detected",
                           instance_id=instance_id,
                           failed_tasks=len(all_failed_tasks))

            # Rule 4: No change for other states (update, restore, maintenance, etc.)
            else:
                logger.debug("No status update needed",
                           instance_id=instance_id,
                           current_status=current_status,
                           active_tasks=len(active_tasks),
                           running_tasks=len(running_tasks),
                           failed_tasks=len(failed_tasks))
                return {
                    "updated": False,
                    "reason": "no_transition_needed",
                    "current_status": current_status,
                    "active_tasks": len(active_tasks),
                    "running_tasks": len(running_tasks)
                }

            # Queue health check task if upscale detected
            if should_queue_health_check:
                # Use Docker Swarm internal DNS name (more reliable than IP scraping)
                # Format: service_name is already "odoo-{database_name}-{instance_id_hex}"
                # Docker's internal DNS resolver handles routing to the correct task
                internal_url = f'http://{service_name}:8069'

                logger.info("Using Docker Swarm DNS for health check",
                          instance_id=instance_id,
                          service_name=service_name,
                          internal_url=internal_url)

                # Queue health check task (non-blocking)
                logger.info("Queueing Odoo health check task",
                          instance_id=instance_id,
                          internal_url=internal_url)

                perform_odoo_health_check_and_update.delay(
                    instance_id,
                    internal_url,
                    current_status
                )

                return {
                    "updated": False,
                    "reason": "health_check_queued",
                    "current_status": current_status,
                    "internal_url": internal_url
                }

            # Update database with target status (atomic update with state validation)
            if target_status and target_status != current_status:
                # For STOPPED transitions: only if currently stopping
                # For ERROR transitions: allow from any non-terminated state
                if target_status == InstanceStatus.STOPPED.value:
                    valid_states = ['stopping']
                elif target_status == InstanceStatus.ERROR.value:
                    valid_states = ['starting', 'restarting', 'stopping', 'running', 'stopped']
                else:
                    valid_states = [current_status]  # Should not happen

                result = await conn.execute("""
                    UPDATE instances
                    SET status = $1, updated_at = $2, last_health_check = $3
                    WHERE id = $4 AND status = ANY($5)
                """, target_status, datetime.utcnow(), datetime.utcnow(), UUID(instance_id), valid_states)

                # Check if update actually occurred
                if result == 'UPDATE 0':
                    logger.warning("Status update blocked - instance state changed",
                                 instance_id=instance_id,
                                 expected_status=current_status,
                                 target_status=target_status)
                    return {
                        "updated": False,
                        "reason": "state_changed_race_condition",
                        "target_status": target_status
                    }

                logger.info("Instance status updated from Docker event",
                          instance_id=instance_id,
                          old_status=current_status,
                          new_status=target_status)

                return {
                    "updated": True,
                    "old_status": current_status,
                    "new_status": target_status,
                    "active_tasks": len(active_tasks),
                    "running_tasks": len(running_tasks)
                }

            return {
                "updated": False,
                "reason": "status_unchanged",
                "current_status": current_status
            }

        finally:
            await conn.close()

    except docker.errors.NotFound:
        logger.warning("Service not found", service_name=service_name)
        return {"updated": False, "reason": "service_not_found"}
    except Exception as e:
        logger.error("Error checking service task state", error=str(e))
        raise


@celery_app.task(bind=True)
def perform_odoo_health_check_and_update(self, instance_id: str, internal_url: str, expected_current_status: str):
    """
    Perform Odoo HTTP health check and update status to RUNNING if successful

    This task is queued when Docker event monitor detects service upscale.
    It runs asynchronously without blocking the event monitoring stream.

    Args:
        instance_id: Instance UUID
        internal_url: Odoo internal URL for health check
        expected_current_status: Expected current status (for validation)
    """
    try:
        logger.info("Starting Odoo health check task",
                   instance_id=instance_id,
                   internal_url=internal_url,
                   task_id=self.request.id)

        result = asyncio.run(_perform_odoo_health_check_and_update(
            instance_id,
            internal_url,
            expected_current_status
        ))

        logger.info("Odoo health check task completed",
                   instance_id=instance_id,
                   result=result,
                   task_id=self.request.id)

        return result

    except Exception as e:
        logger.error("Odoo health check task failed",
                    instance_id=instance_id,
                    error=str(e),
                    task_id=self.request.id)
        # Mark instance as error on health check failure
        asyncio.run(_update_instance_status_to_error(
            instance_id,
            f"Health check failed: {str(e)}"
        ))
        raise


async def _perform_odoo_health_check_and_update(
    instance_id: str,
    internal_url: str,
    expected_current_status: str
) -> Dict[str, Any]:
    """
    Perform HTTP health check and update instance status to RUNNING

    Waits up to 300 seconds for Odoo to respond with HTTP 200/302/303.
    Only updates status if current status matches expected (prevents race conditions).
    """
    import httpx

    logger.info("Performing Odoo health check",
               instance_id=instance_id,
               internal_url=internal_url,
               expected_status=expected_current_status)

    # Perform HTTP health check with retry
    timeout = 300  # 300 seconds (5 minutes)
    check_interval = 5  # Check every 5 seconds
    start_time = datetime.utcnow()
    health_check_passed = False

    async with httpx.AsyncClient() as client:
        while (datetime.utcnow() - start_time).seconds < timeout:
            try:
                response = await client.get(internal_url, timeout=10)
                if response.status_code in [200, 302, 303]:
                    health_check_passed = True
                    logger.info("Odoo health check passed",
                              instance_id=instance_id,
                              status_code=response.status_code,
                              elapsed_seconds=(datetime.utcnow() - start_time).seconds)
                    break
            except Exception as check_error:
                logger.debug("Health check attempt failed, will retry",
                           instance_id=instance_id,
                           error=str(check_error),
                           elapsed_seconds=(datetime.utcnow() - start_time).seconds)

            await asyncio.sleep(check_interval)

    if not health_check_passed:
        logger.error("Odoo health check failed - timeout",
                    instance_id=instance_id,
                    internal_url=internal_url,
                    timeout_seconds=timeout)
        # Update to ERROR status
        await _update_instance_status_to_error(
            instance_id,
            f"Odoo health check timeout after {timeout}s"
        )
        return {
            "success": False,
            "reason": "health_check_timeout",
            "timeout_seconds": timeout
        }

    # Health check passed - update status to RUNNING
    # But first verify current status hasn't changed unexpectedly
    conn = await _get_db_connection()
    try:
        current_status = await conn.fetchval(
            "SELECT status FROM instances WHERE id = $1",
            UUID(instance_id)
        )

        if not current_status:
            logger.warning("Instance not found during health check update",
                         instance_id=instance_id)
            return {"success": False, "reason": "instance_not_found"}

        # Only update if still in expected transitional state
        if current_status not in ['starting', 'restarting']:
            logger.warning("Instance status changed during health check, not updating",
                         instance_id=instance_id,
                         expected_status=expected_current_status,
                         actual_status=current_status)
            return {
                "success": False,
                "reason": "status_changed",
                "expected_status": expected_current_status,
                "actual_status": current_status
            }

        # Update to RUNNING (atomic - only if still in transitional state)
        result = await conn.execute("""
            UPDATE instances
            SET status = $1, updated_at = $2, last_health_check = $3
            WHERE id = $4 AND status IN ('starting', 'restarting')
        """, InstanceStatus.RUNNING.value, datetime.utcnow(), datetime.utcnow(), UUID(instance_id))

        # Check if update was blocked by race condition
        if result == 'UPDATE 0':
            # Re-check current status
            actual_status = await conn.fetchval(
                "SELECT status FROM instances WHERE id = $1",
                UUID(instance_id)
            )
            logger.warning("Health check status update blocked - state changed during check",
                         instance_id=instance_id,
                         expected_states=['starting', 'restarting'],
                         actual_status=actual_status)
            return {
                "success": False,
                "reason": "status_changed_race_condition",
                "actual_status": actual_status
            }

        logger.info("Instance status updated to RUNNING after health check",
                   instance_id=instance_id,
                   old_status=current_status)

        return {
            "success": True,
            "old_status": current_status,
            "new_status": InstanceStatus.RUNNING.value,
            "internal_url": internal_url
        }

    finally:
        await conn.close()


async def _update_instance_status_to_error(instance_id: str, error_message: str):
    """Update instance status to ERROR with error message"""
    conn = await _get_db_connection()
    try:
        await conn.execute("""
            UPDATE instances
            SET status = $1, error_message = $2, updated_at = $3
            WHERE id = $4
        """, InstanceStatus.ERROR.value, error_message, datetime.utcnow(), UUID(instance_id))

        logger.error("Instance status updated to ERROR",
                    instance_id=instance_id,
                    error_message=error_message)
    finally:
        await conn.close()


async def _get_db_connection():
    """
    Get database connection using existing patterns

    NOTE: For production with high event volume, consider implementing
    a connection pool at Celery worker initialization to reuse connections
    across tasks instead of opening/closing per task.

    Example with asyncpg.create_pool:
    # In celery worker init:
    # db_pool = await asyncpg.create_pool(...)
    # Then use: conn = await db_pool.acquire()
    """
    db_config = {
        'host': os.getenv('POSTGRES_HOST', 'postgres'),
        'port': int(os.getenv('POSTGRES_PORT', 5432)),
        'database': os.getenv('POSTGRES_DB', 'instance'),
        'user': os.getenv('DB_SERVICE_USER', 'instance_service'),
        'password': os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me'),
    }
    return await asyncpg.connect(**db_config)


@celery_app.task(bind=True)
def update_instance_status_from_event(self, instance_id: str, status: str, event_type: str, container_name: str, event_time: str):
    """Update instance status based on Docker event"""
    try:
        logger.info("Updating instance status from Docker event", 
                   instance_id=instance_id, 
                   status=status, 
                   event_type=event_type,
                   container=container_name,
                   task_id=self.request.id)
        
        result = asyncio.run(_update_instance_status_from_event(
            instance_id, status, event_type, container_name, event_time
        ))
        
        logger.info("Instance status updated successfully", 
                   instance_id=instance_id, 
                   status=status,
                   updated=result.get('updated', False))
        
        return result
        
    except Exception as e:
        logger.error("Failed to update instance status from event", 
                    instance_id=instance_id, 
                    error=str(e))
        raise


async def _update_instance_status_from_event(instance_id: str, status: str, event_type: str, container_name: str, event_time: str) -> Dict[str, Any]:
    """Update instance status in database from Docker event"""
    try:
        # Get database connection
        db_config = {
            'host': os.getenv('POSTGRES_HOST', 'postgres'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'database': os.getenv('POSTGRES_DB', 'instance'),
            'user': os.getenv('DB_SERVICE_USER', 'instance_service'),
            'password': os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me'),
        }
        
        conn = await asyncpg.connect(**db_config)
        try:
            # Get current instance status
            current_status = await conn.fetchval(
                "SELECT status FROM instances WHERE id = $1",
                UUID(instance_id)
            )
            
            if not current_status:
                logger.warning("Instance not found for status update", instance_id=instance_id)
                return {"updated": False, "reason": "instance_not_found"}

            # CRITICAL: Never overwrite TERMINATED status - it's a final state set by subscription cancellation
            if current_status == 'terminated':
                logger.info("Skipping Docker event status update - instance is TERMINATED (final state)",
                           instance_id=instance_id,
                           attempted_status=status,
                           event_type=event_type)
                return {"updated": False, "reason": "instance_terminated"}

            # Check if update is needed
            if current_status == status:
                logger.debug("Instance status already up to date",
                           instance_id=instance_id,
                           status=status)
                return {"updated": False, "reason": "status_unchanged"}
            
            # Update instance status and service info
            await conn.execute("""
                UPDATE instances
                SET status = $1,
                    service_name = $2,
                    updated_at = $3,
                    last_health_check = $4,
                    error_message = NULL
                WHERE id = $5
            """, status, container_name, datetime.utcnow(), datetime.utcnow(), UUID(instance_id))
            
            # Log status change
            logger.info("Instance status updated from Docker event", 
                       instance_id=instance_id,
                       old_status=current_status,
                       new_status=status,
                       event_type=event_type,
                       container=container_name)
            
            return {
                "updated": True,
                "old_status": current_status,
                "new_status": status,
                "event_type": event_type,
                "container_name": container_name,
                "event_time": event_time
            }
            
        finally:
            await conn.close()
            
    except Exception as e:
        logger.error("Database update failed for Docker event", 
                    instance_id=instance_id, 
                    error=str(e))
        raise


@celery_app.task(bind=True)
def reconcile_instance_statuses_task(self):
    """Periodic task to reconcile database vs Docker container states"""
    try:
        logger.info("Starting instance status reconciliation", task_id=self.request.id)
        
        result = asyncio.run(_reconcile_instance_statuses())
        
        logger.info("Instance status reconciliation completed", 
                   total_checked=result.get('total_checked', 0),
                   updated_count=result.get('updated_count', 0),
                   mismatched=result.get('mismatched', []))
        
        return result
        
    except Exception as e:
        logger.error("Instance status reconciliation failed", error=str(e))
        raise


async def _reconcile_instance_statuses() -> Dict[str, Any]:
    """Reconcile database instance statuses with actual Docker Swarm service states"""
    try:
        # Initialize Docker client
        client = docker.from_env()

        # Get database connection
        db_config = {
            'host': os.getenv('POSTGRES_HOST', 'postgres'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'database': os.getenv('POSTGRES_DB', 'instance'),
            'user': os.getenv('DB_SERVICE_USER', 'instance_service'),
            'password': os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me'),
        }

        conn = await asyncpg.connect(**db_config)
        try:
            # Get all non-terminated instances
            instances = await conn.fetch("""
                SELECT id, status, database_name, service_name
                FROM instances
                WHERE status != 'terminated'
            """)

            total_checked = len(instances)
            updated_count = 0
            mismatched = []

            for instance in instances:
                instance_id = instance['id']
                db_status = instance['status']
                database_name = instance['database_name']

                # Generate expected service name (hyphen-separated for Swarm)
                expected_service_name = f"odoo-{database_name}-{instance_id.hex[:8]}"

                try:
                    # Check if service exists and get its task status
                    service = client.services.get(expected_service_name)
                    tasks = service.tasks()

                    # Find running tasks
                    running_tasks = [t for t in tasks if t['Status']['State'] == 'running']
                    failed_tasks = [t for t in tasks if t['Status']['State'] == 'failed']
                    shutdown_tasks = [t for t in tasks if t['Status']['State'] == 'shutdown']

                    # Determine expected status based on task states
                    if running_tasks:
                        expected_db_status = InstanceStatus.RUNNING.value
                    elif failed_tasks:
                        expected_db_status = InstanceStatus.ERROR.value
                    elif shutdown_tasks or not tasks:
                        expected_db_status = InstanceStatus.STOPPED.value
                    else:
                        # Tasks exist but none running/failed/shutdown (preparing/starting)
                        expected_db_status = InstanceStatus.STARTING.value

                    # Check for mismatch
                    if db_status != expected_db_status:
                        # Never override TERMINATED status - it's intentionally set
                        if db_status == InstanceStatus.TERMINATED.value:
                            logger.info("Skipping status update for terminated instance",
                                      instance_id=str(instance_id),
                                      db_status=db_status,
                                      task_status=expected_db_status)
                            continue

                        logger.info("Status mismatch detected",
                                  instance_id=str(instance_id),
                                  db_status=db_status,
                                  expected_status=expected_db_status,
                                  running_tasks=len(running_tasks),
                                  failed_tasks=len(failed_tasks))

                        # Update database status
                        await conn.execute("""
                            UPDATE instances
                            SET status = $1, updated_at = $2, last_health_check = $3
                            WHERE id = $4
                        """, expected_db_status, datetime.utcnow(), datetime.utcnow(), instance_id)

                        updated_count += 1
                        mismatched.append({
                            'instance_id': str(instance_id),
                            'old_status': db_status,
                            'new_status': expected_db_status,
                            'running_tasks': len(running_tasks),
                            'failed_tasks': len(failed_tasks)
                        })

                except docker.errors.NotFound:
                    # Service doesn't exist but instance is not terminated or already marked as missing
                    if db_status not in [InstanceStatus.CONTAINER_MISSING.value]:
                        logger.warning("Service not found for active instance",
                                     instance_id=str(instance_id),
                                     expected_service=expected_service_name,
                                     current_status=db_status)

                        # Mark as container missing
                        await conn.execute("""
                            UPDATE instances
                            SET status = $1, error_message = $2, updated_at = $3
                            WHERE id = $4
                        """, InstanceStatus.CONTAINER_MISSING.value, "Service not found", datetime.utcnow(), instance_id)

                        updated_count += 1
                        mismatched.append({
                            'instance_id': str(instance_id),
                            'old_status': db_status,
                            'new_status': InstanceStatus.CONTAINER_MISSING.value,
                            'reason': 'service_not_found'
                        })

                except Exception as e:
                    logger.error("Error checking service status",
                               instance_id=str(instance_id),
                               service=expected_service_name,
                               error=str(e))
            
            return {
                'total_checked': total_checked,
                'updated_count': updated_count,
                'mismatched': mismatched,
                'timestamp': datetime.utcnow().isoformat()
            }
            
        finally:
            await conn.close()
    
    except Exception as e:
        logger.error("Status reconciliation failed", error=str(e))
        raise


@celery_app.task(bind=True)
def check_container_destroyed(self, instance_id: str, container_name: str):
    """Check if container was actually destroyed after a kill event"""
    try:
        logger.info("Checking if container was destroyed", 
                   instance_id=instance_id, 
                   container=container_name,
                   task_id=self.request.id)
        
        result = asyncio.run(_check_container_destroyed(instance_id, container_name))
        
        logger.info("Container destroy check completed", 
                   instance_id=instance_id, 
                   container=container_name,
                   result=result)
        
        return result
        
    except Exception as e:
        logger.error("Failed to check container destruction", 
                    instance_id=instance_id, 
                    container=container_name,
                    error=str(e))
        raise


async def _check_container_destroyed(instance_id: str, container_name: str) -> Dict[str, Any]:
    """Check if container still exists and update status accordingly"""
    try:
        import docker
        
        client = docker.from_env()
        
        try:
            # Try to get the container
            container = client.containers.get(container_name)
            logger.info("Container still exists after kill", 
                       instance_id=instance_id,
                       container=container_name,
                       status=container.status)
            
            return {
                "container_exists": True,
                "container_status": container.status,
                "action": "no_change"
            }
            
        except docker.errors.NotFound:
            # Container doesn't exist - it was destroyed
            logger.info("Container was destroyed after kill event", 
                       instance_id=instance_id,
                       container=container_name)
            
            # Update instance status to CONTAINER_MISSING
            await _update_instance_status_from_event(
                instance_id, 
                InstanceStatus.CONTAINER_MISSING.value, 
                "destroy", 
                container_name, 
                datetime.utcnow().isoformat()
            )
            
            return {
                "container_exists": False,
                "action": "updated_to_container_missing"
            }
            
    except Exception as e:
        logger.error("Error checking container destruction", 
                    instance_id=instance_id,
                    container=container_name,
                    error=str(e))
        raise