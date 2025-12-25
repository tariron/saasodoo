"""
Kubernetes pod monitoring tasks for real-time instance status synchronization

This module implements comprehensive pod lifecycle monitoring that mirrors
the Docker Swarm event monitoring pattern:
- Tracks pod ready state transitions
- Queues health checks when pods first become ready
- Handles rolling updates and multiple pod scenarios
- Coordinates with lifecycle tasks for dual-path status updates
"""

import os
import re
import asyncio
import asyncpg
import json
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Set
from uuid import UUID
from threading import Thread, Event as ThreadEvent
import time

from kubernetes import client, watch
from kubernetes.client.rest import ApiException

from app.celery_config import celery_app
from app.models.instance import InstanceStatus
from app.utils.orchestrator_client import get_orchestrator_client
import structlog

logger = structlog.get_logger(__name__)

# Global monitoring state
_monitoring_active = False
_monitor_thread: Optional[Thread] = None
_stop_event = ThreadEvent()


class KubernetesPodMonitor:
    """
    Real-time Kubernetes pod event monitoring for instance status synchronization

    Implements a comprehensive state machine that:
    1. Tracks pod ready state transitions (detects when pods FIRST become ready)
    2. Queues health checks on ready transitions (regardless of event type)
    3. Handles rolling updates (checks for other pods before setting STOPPED)
    4. Coordinates with lifecycle tasks (dual-path status updates)
    5. Detects manual kubectl operations (like Docker Swarm manual scale)
    """

    def __init__(self):
        self.k8s_client = None
        self.core_v1 = None
        self.is_running = False
        self.stop_event = ThreadEvent()
        self.last_event_time = {}  # For deduplication
        self.processed_events: Set[str] = set()  # Event deduplication
        self.namespace = os.getenv('KUBERNETES_NAMESPACE', 'saasodoo')

        # Pod ready state tracking: {pod_uid: {'ready': bool, 'health_check_queued': bool}}
        # This tracks PREVIOUS state to detect transitions (like Docker event start/stop)
        self.pod_ready_state: Dict[str, Dict[str, Any]] = {}

        # Deployment name pattern: odoo-{database_name}-{instance_id.hex[:8]}
        self.deployment_pattern = re.compile(r'^odoo-([^-]+)-([a-f0-9]{8})')

    def _init_k8s_client(self):
        """Initialize Kubernetes client with error handling"""
        try:
            self.k8s_client = get_orchestrator_client()
            self.core_v1 = self.k8s_client.core_v1
            # Test connection by listing pods
            self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                limit=1
            )
            logger.info("Kubernetes client initialized successfully for monitoring")
        except Exception as e:
            logger.error("Failed to initialize Kubernetes client", error=str(e))
            raise

    def _is_saasodoo_pod(self, pod_name: str) -> Optional[Dict[str, str]]:
        """Check if pod is a SaaS Odoo instance and extract metadata"""
        # Pod names are like: odoo-dbname-abcd1234-5f6g7h8i
        match = self.deployment_pattern.match(pod_name)
        if match:
            database_name, instance_id_hex = match.groups()
            return {
                'database_name': database_name,
                'instance_id_hex': instance_id_hex,
                'pod_name': pod_name
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
                    WHERE id::text LIKE $1 || '%'
                    LIMIT 1
                """, instance_id_hex)
                return instance_id
            finally:
                await conn.close()
        except Exception as e:
            logger.error("Database query failed for instance hex", hex=instance_id_hex, error=str(e))
            return None

    async def _get_db_connection(self):
        """Create async database connection"""
        db_config = {
            'host': os.getenv('POSTGRES_HOST', 'postgres'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'database': os.getenv('INSTANCE_DB_NAME', 'instance'),
            'user': os.getenv('DB_SERVICE_USER', 'instance_service'),
            'password': os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me'),
        }
        return await asyncpg.connect(**db_config)

    def _get_other_running_pods_for_instance(self, instance_hex: str, exclude_pod: str) -> list:
        """
        Check if there are other Running/Pending pods for this instance
        This is critical for handling rolling updates and avoiding race conditions
        """
        try:
            all_pods = self.core_v1.list_namespaced_pod(
                namespace=self.namespace,
                label_selector=f"instance-id={instance_hex}"
            ).items

            # Filter out the excluded pod and check if any other pods are active
            other_active_pods = [
                p for p in all_pods
                if p.metadata.name != exclude_pod
                and p.status.phase in ['Running', 'Pending']
            ]

            return other_active_pods
        except Exception as e:
            logger.error("Error checking for other pods", error=str(e), exc_info=True)
            return []

    def _should_queue_health_check(self, pod_uid: str, is_ready: bool) -> bool:
        """
        Determine if we should queue a health check based on ready state transition

        This implements the key logic similar to Docker Swarm's task state checking:
        - Queue health check when pod FIRST becomes ready (False → True transition)
        - Only queue once per pod lifecycle
        - Works for both ADDED and MODIFIED events
        """
        previous_state = self.pod_ready_state.get(pod_uid, {})
        previous_ready = previous_state.get('ready', False)
        already_queued = previous_state.get('health_check_queued', False)

        # Update current state
        self.pod_ready_state[pod_uid] = {
            'ready': is_ready,
            'health_check_queued': already_queued or (not previous_ready and is_ready)
        }

        # Queue if: ready transitioned False→True AND not already queued
        should_queue = not previous_ready and is_ready and not already_queued

        if should_queue:
            logger.info("Pod ready state transition detected - will queue health check",
                       pod_uid=pod_uid,
                       previous_ready=previous_ready,
                       current_ready=is_ready)

        return should_queue

    def _process_pod_event(self, event: Dict[str, Any]):
        """
        Process a Kubernetes pod event with comprehensive state machine logic

        Event Flow:
        1. Parse pod metadata and extract instance ID
        2. Determine pod state (phase + ready)
        3. Check for ready state transitions → queue health check if needed
        4. Map pod state to instance status
        5. Queue database update task

        This mirrors Docker Swarm's event processing but handles Kubernetes complexity
        """
        try:
            event_type = event['type']  # ADDED, MODIFIED, DELETED
            pod = event['object']
            pod_name = pod.metadata.name
            pod_uid = pod.metadata.uid
            pod_phase = pod.status.phase

            # Extract readiness from conditions
            ready = False
            if pod.status.conditions:
                for condition in pod.status.conditions:
                    if condition.type == 'Ready':
                        ready = (condition.status == 'True')
                        break

            logger.info("POD EVENT RECEIVED",
                       event_type=event_type,
                       pod=pod_name,
                       phase=pod_phase,
                       ready=ready)

            # Check if this is a SaaS Odoo instance pod
            pod_info = self._is_saasodoo_pod(pod_name)
            if not pod_info:
                logger.debug("Pod is not a SaaS instance, ignoring", pod=pod_name)
                return

            logger.info("SaaS pod event detected",
                       pod=pod_name,
                       instance_hex=pod_info['instance_id_hex'],
                       phase=pod_phase,
                       ready=ready,
                       event_type=event_type)

            # Get full instance ID from database
            instance_id = self._get_instance_id_from_hex(pod_info['instance_id_hex'])
            if not instance_id:
                logger.error("Could not find instance for pod",
                           pod=pod_name,
                           hex=pod_info['instance_id_hex'])
                return

            logger.debug("Found instance ID from hex",
                        hex=pod_info['instance_id_hex'],
                        instance_id=instance_id)

            # ===== STATE MACHINE LOGIC =====
            # Maps pod state to instance status like Docker Swarm event mapping

            new_status = None
            health_check_info = None

            if event_type == 'DELETED':
                # Pod deleted - check for rolling update scenario
                other_pods = self._get_other_running_pods_for_instance(
                    pod_info['instance_id_hex'],
                    pod_name
                )

                if other_pods:
                    logger.info("Pod deleted but other pods exist - ignoring (rolling update)",
                               pod=pod_name,
                               instance_id=instance_id,
                               other_pods=[p.metadata.name for p in other_pods])
                    # Clean up ready state tracking for this pod
                    self.pod_ready_state.pop(pod_uid, None)
                    return

                # No other pods - this is a true shutdown
                new_status = InstanceStatus.STOPPED
                logger.info("Pod deleted and no other pods running - setting STOPPED",
                           pod=pod_name,
                           instance_id=instance_id)

                # Clean up ready state tracking
                self.pod_ready_state.pop(pod_uid, None)

            elif pod_phase == 'Running' and ready:
                # Pod running and ready - check for ready state transition
                new_status = InstanceStatus.STARTING

                # Check if we should queue health check (first time pod becomes ready)
                if self._should_queue_health_check(pod_uid, True):
                    # Construct service URL for health check
                    deployment_name = pod_name.rsplit('-', 2)[0]
                    service_name = f"{deployment_name}-service"
                    internal_url = f"http://{service_name}.{self.namespace}.svc.cluster.local:8069"

                    health_check_info = {
                        'instance_id': instance_id,
                        'internal_url': internal_url,
                        'expected_status': 'starting'
                    }

                    logger.info("Pod became ready - queueing health check",
                               pod=pod_name,
                               instance_id=instance_id,
                               internal_url=internal_url,
                               event_type=event_type)
                else:
                    logger.debug("Pod running and ready - setting STARTING",
                               pod=pod_name,
                               instance_id=instance_id,
                               event_type=event_type)

            elif pod_phase == 'Pending':
                # Pod is pending - set to STARTING (if not already)
                new_status = InstanceStatus.STARTING
                # Update ready state tracking
                self.pod_ready_state.setdefault(pod_uid, {})['ready'] = False
                logger.debug("Pod pending",
                           pod=pod_name,
                           instance_id=instance_id)

            elif pod_phase == 'Failed':
                # Pod failed - set to ERROR
                new_status = InstanceStatus.ERROR
                logger.warning("Pod failed",
                             pod=pod_name,
                             instance_id=instance_id)

            elif pod_phase == 'Succeeded':
                # Pod succeeded unexpectedly (shouldn't happen for long-running containers)
                # Treat as stopped
                logger.warning("Pod succeeded unexpectedly",
                             pod=pod_name,
                             instance_id=instance_id)
                # Don't update status - let DELETE event handle it
                return

            # Queue database update task if we have a new status
            if new_status:
                from app.tasks.monitoring import update_instance_status_from_event
                update_instance_status_from_event.delay(
                    instance_id=instance_id,
                    status=new_status.value,
                    event_type=event_type,
                    container_name=pod_name,
                    event_time=datetime.utcnow().isoformat()
                )

            # Queue health check task if needed (separate from status update)
            if health_check_info:
                from app.tasks.monitoring import perform_odoo_health_check_and_update
                perform_odoo_health_check_and_update.delay(
                    health_check_info['instance_id'],
                    health_check_info['internal_url'],
                    health_check_info['expected_status']
                )

        except Exception as e:
            logger.error("Error processing pod event", error=str(e), exc_info=True)

    def start_monitoring(self):
        """Start Kubernetes pod event monitoring in background thread"""
        if self.is_running:
            logger.warning("Monitoring already running")
            return

        try:
            self._init_k8s_client()
            self.is_running = True
            self.stop_event.clear()

            logger.info("Starting Kubernetes pod event monitoring")

            # Start monitoring thread
            monitor_thread = Thread(target=self._monitor_events, daemon=True)
            monitor_thread.start()

        except Exception as e:
            logger.error("Failed to start Kubernetes event monitoring", error=str(e))
            self.is_running = False
            raise

    def stop_monitoring(self):
        """Stop Kubernetes pod event monitoring"""
        if not self.is_running:
            return

        logger.info("Stopping Kubernetes pod event monitoring")
        self.is_running = False
        self.stop_event.set()

    def _monitor_events(self):
        """Main event monitoring loop using Kubernetes Watch API (runs in separate thread)"""
        try:
            logger.info("Kubernetes event monitor thread started")

            w = watch.Watch()
            for event in w.stream(
                self.core_v1.list_namespaced_pod,
                namespace=self.namespace,
                label_selector="app=odoo",
                timeout_seconds=0  # Never timeout, watch indefinitely
            ):
                if self.stop_event.is_set():
                    logger.info("Stop event received, exiting monitor loop")
                    w.stop()
                    break

                self._process_pod_event(event)

        except Exception as e:
            logger.error("Kubernetes event monitoring failed", error=str(e))
            self.is_running = False
        finally:
            logger.info("Kubernetes pod event monitoring stopped")


# Global monitor instance
_k8s_monitor = KubernetesPodMonitor()


@celery_app.task(bind=True)
def monitor_docker_events_task(self):
    """Celery task to start Kubernetes pod event monitoring"""
    try:
        global _monitoring_active, _monitor_thread, _stop_event

        if _monitoring_active:
            return {"status": "already_running", "message": "Kubernetes event monitoring is already active"}

        logger.info("Starting Kubernetes event monitoring task", task_id=self.request.id)

        _monitoring_active = True
        _stop_event.clear()

        # Start monitoring
        _k8s_monitor.start_monitoring()

        return {
            "status": "started",
            "message": "Kubernetes event monitoring started successfully",
            "task_id": self.request.id
        }

    except Exception as e:
        logger.error("Failed to start Kubernetes event monitoring task", error=str(e))
        _monitoring_active = False
        raise


@celery_app.task(bind=True)
def stop_docker_events_monitoring_task(self):
    """Celery task to stop Kubernetes pod event monitoring"""
    try:
        global _monitoring_active, _k8s_monitor

        if not _monitoring_active:
            return {"status": "not_running", "message": "Kubernetes event monitoring is not active"}

        logger.info("Stopping Kubernetes event monitoring task", task_id=self.request.id)

        _k8s_monitor.stop_monitoring()
        _monitoring_active = False

        return {
            "status": "stopped",
            "message": "Kubernetes event monitoring stopped successfully",
            "task_id": self.request.id
        }

    except Exception as e:
        logger.error("Failed to stop Kubernetes event monitoring task", error=str(e))
        raise


@celery_app.task(bind=True, max_retries=0)
def update_instance_status_from_event(
    self,
    instance_id: str,
    status: str,
    event_type: str,
    container_name: str,
    event_time: str
):
    """
    Update instance status from Kubernetes pod event

    This task is queued by the monitoring thread and performs the actual database update.
    It includes safety checks to prevent invalid status transitions.
    """
    try:
        logger.info("Updating instance status from pod event",
                   instance_id=instance_id,
                   status=status,
                   event_type=event_type,
                   container=container_name,
                   task_id=self.request.id)

        # Run async database update
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _update_instance_status_async(instance_id, status, event_type, container_name, event_time)
            )
            return result
        finally:
            loop.close()

    except Exception as e:
        logger.error("Failed to update instance status from event",
                    instance_id=instance_id,
                    error=str(e),
                    exc_info=True)
        raise


async def _update_instance_status_async(
    instance_id: str,
    status: str,
    event_type: str,
    container_name: str,
    event_time: str
) -> Dict[str, Any]:
    """
    Async implementation of instance status update with safety checks

    Safety Rules (preventing invalid transitions):
    1. Don't downgrade RUNNING → STARTING on ADDED events (monitoring restart scenario)
    2. Allow STARTING → STOPPED (pod deletion during startup)
    3. Allow any status → ERROR (failures can happen anytime)
    4. Timestamp-based conflict resolution if needed
    """
    conn = None
    try:
        # Connect to database
        db_config = {
            'host': os.getenv('POSTGRES_HOST', 'postgres'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'database': os.getenv('INSTANCE_DB_NAME', 'instance'),
            'user': os.getenv('DB_SERVICE_USER', 'instance_service'),
            'password': os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me'),
        }
        conn = await asyncpg.connect(**db_config)

        # Get current status
        current_status = await conn.fetchval(
            "SELECT status FROM instances WHERE id = $1",
            UUID(instance_id)
        )

        if not current_status:
            logger.error("Instance not found", instance_id=instance_id)
            return {"updated": False, "reason": "instance_not_found"}

        # Safety check: Prevent downgrade from RUNNING to STARTING on monitoring restart
        # This happens when monitoring restarts and receives ADDED events for existing running pods
        if current_status == 'running' and status == 'starting' and event_type == 'ADDED':
            logger.debug("Skipping downgrade from RUNNING to STARTING on ADDED event (existing pod)",
                       instance_id=instance_id,
                       container=container_name)
            return {"updated": False, "reason": "no_downgrade_from_running"}

        # Safety check: Don't update if status hasn't changed
        if current_status == status:
            logger.debug("Instance status already up to date",
                       instance_id=instance_id,
                       status=status)
            return {"updated": False, "reason": "status_unchanged"}

        # Perform update
        await conn.execute("""
            UPDATE instances
            SET status = $1, updated_at = NOW()
            WHERE id = $2
        """, status, UUID(instance_id))

        logger.info("Instance status updated from pod event",
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

    except Exception as e:
        logger.error("Database update failed", error=str(e), exc_info=True)
        raise
    finally:
        if conn:
            await conn.close()


@celery_app.task(bind=True, max_retries=0)
def perform_odoo_health_check_and_update(
    self,
    instance_id: str,
    internal_url: str,
    expected_current_status: str
):
    """
    Perform Odoo HTTP health check and update instance status to RUNNING if healthy

    This task is queued when a pod becomes ready for the first time.
    It waits up to 300 seconds for Odoo to respond, then updates status to RUNNING.

    This mirrors Docker Swarm's health check pattern but adapted for Kubernetes.
    """
    try:
        logger.info("Starting Odoo health check task",
                   instance_id=instance_id,
                   internal_url=internal_url,
                   task_id=self.request.id)

        # Run async health check
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            result = loop.run_until_complete(
                _perform_odoo_health_check_and_update(
                    instance_id, internal_url, expected_current_status
                )
            )
            logger.info("Odoo health check task completed",
                       instance_id=instance_id,
                       result=result,
                       task_id=self.request.id)
            return result
        finally:
            loop.close()

    except Exception as e:
        logger.error("Odoo health check task failed",
                    instance_id=instance_id,
                    error=str(e),
                    exc_info=True)
        raise


async def _perform_odoo_health_check_and_update(
    instance_id: str,
    internal_url: str,
    expected_current_status: str
) -> Dict[str, Any]:
    """
    Async implementation of Odoo health check with 300s timeout

    Waits for Odoo to respond with HTTP 200/302/303 (indicating it's serving requests).
    If healthy, updates instance status to RUNNING.
    If timeout, updates to ERROR.
    """
    import httpx

    logger.info("Performing Odoo health check",
               instance_id=instance_id,
               internal_url=internal_url,
               expected_status=expected_current_status)

    timeout = 300  # 5 minutes
    check_interval = 5  # Check every 5 seconds
    start_time = datetime.utcnow()
    health_check_passed = False

    async with httpx.AsyncClient() as client:
        while (datetime.utcnow() - start_time).seconds < timeout:
            try:
                response = await client.get(internal_url, timeout=10, follow_redirects=False)
                if response.status_code in [200, 302, 303]:
                    health_check_passed = True
                    elapsed = (datetime.utcnow() - start_time).seconds
                    logger.info("Odoo health check passed",
                               instance_id=instance_id,
                               status_code=response.status_code,
                               elapsed_seconds=elapsed)
                    break
            except Exception as check_error:
                logger.debug("Health check attempt failed, will retry",
                           instance_id=instance_id,
                           error=str(check_error))
                await asyncio.sleep(check_interval)
                continue

    # Connect to database and update status
    conn = None
    try:
        db_config = {
            'host': os.getenv('POSTGRES_HOST', 'postgres'),
            'port': int(os.getenv('POSTGRES_PORT', 5432)),
            'database': os.getenv('INSTANCE_DB_NAME', 'instance'),
            'user': os.getenv('DB_SERVICE_USER', 'instance_service'),
            'password': os.getenv('DB_SERVICE_PASSWORD', 'instance_service_secure_pass_change_me'),
        }
        conn = await asyncpg.connect(**db_config)

        # Get current status to verify it hasn't changed during health check
        current_status = await conn.fetchval(
            "SELECT status FROM instances WHERE id = $1",
            UUID(instance_id)
        )

        if current_status != expected_current_status:
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

        if health_check_passed:
            # Update to RUNNING
            await conn.execute("""
                UPDATE instances
                SET status = $1, updated_at = NOW()
                WHERE id = $2
            """, InstanceStatus.RUNNING.value, UUID(instance_id))

            logger.info("Instance status updated to RUNNING after health check",
                       instance_id=instance_id,
                       old_status=current_status)

            return {
                "success": True,
                "old_status": current_status,
                "new_status": InstanceStatus.RUNNING.value,
                "internal_url": internal_url
            }
        else:
            # Health check timeout - set to ERROR
            await conn.execute("""
                UPDATE instances
                SET status = $1,
                    error_message = $2,
                    updated_at = NOW()
                WHERE id = $3
            """, InstanceStatus.ERROR.value, f"Odoo health check timeout after {timeout}s", UUID(instance_id))

            logger.error("Odoo health check timeout - setting instance to ERROR",
                        instance_id=instance_id,
                        timeout=timeout)

            return {
                "success": False,
                "reason": "timeout",
                "old_status": current_status,
                "new_status": InstanceStatus.ERROR.value,
                "timeout": timeout
            }

    except Exception as e:
        logger.error("Failed to update instance status after health check",
                    instance_id=instance_id,
                    error=str(e),
                    exc_info=True)
        raise
    finally:
        if conn:
            await conn.close()
