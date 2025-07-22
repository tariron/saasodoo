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
        
        # Container name pattern: odoo_{database_name}_{instance_id.hex[:8]}
        self.container_pattern = re.compile(r'^odoo_([^_]+)_([a-f0-9]{8})$')
        
        # Event to status mapping
        self.event_status_map = {
            'start': InstanceStatus.RUNNING,
            'die': InstanceStatus.STOPPED,
            'kill': InstanceStatus.STOPPED,
            'stop': InstanceStatus.STOPPED,
            'restart': InstanceStatus.RUNNING,
            'pause': InstanceStatus.SUSPENDED,
            'unpause': InstanceStatus.RUNNING,
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
    
    def _is_saasodoo_container(self, container_name: str) -> Optional[Dict[str, str]]:
        """Check if container is a SaaS Odoo instance and extract metadata"""
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
    
    def _should_process_event(self, event_id: str, container_name: str) -> bool:
        """Check if event should be processed (deduplication)"""
        # Create unique event key
        event_key = f"{container_name}_{event_id}_{int(time.time() // 5)}"  # 5-second window
        
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
    
    def _process_container_event(self, event: Dict[str, Any]):
        """Process a single container event"""
        try:
            event_type = event.get('Action', '').lower()
            container_name = event.get('Actor', {}).get('Attributes', {}).get('name', '')
            event_id = event.get('id', '')
            
            if not container_name or not event_type:
                return
            
            # Check if this is a SaaS Odoo container
            container_info = self._is_saasodoo_container(container_name)
            if not container_info:
                return
            
            # Deduplication check
            if not self._should_process_event(event_id, container_name):
                return
            
            # Map event to status
            if event_type not in self.event_status_map:
                logger.debug("Untracked event type", event_type=event_type, container=container_name)
                return
            
            new_status = self.event_status_map[event_type]
            
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
            # Listen for container events only
            event_filters = {
                'type': 'container',
                'event': ['start', 'stop', 'die', 'kill', 'restart', 'pause', 'unpause']
            }
            
            logger.info("Starting Docker event stream", filters=event_filters)
            
            # Start event stream
            for event in self.client.events(decode=True, filters=event_filters):
                if self.stop_event.is_set():
                    logger.info("Stop event received, exiting monitor loop")
                    break
                
                self._process_container_event(event)
                
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
            
            # Check if update is needed
            if current_status == status:
                logger.debug("Instance status already up to date", 
                           instance_id=instance_id, 
                           status=status)
                return {"updated": False, "reason": "status_unchanged"}
            
            # Update instance status and container info
            await conn.execute("""
                UPDATE instances 
                SET status = $1, 
                    container_name = $2,
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
    """Reconcile database instance statuses with actual Docker container states"""
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
                SELECT id, status, database_name, container_name 
                FROM instances 
                WHERE status != 'terminated'
            """)
            
            total_checked = len(instances)
            updated_count = 0
            mismatched = []
            
            container_pattern = re.compile(r'^odoo_([^_]+)_([a-f0-9]{8})$')
            
            for instance in instances:
                instance_id = instance['id']
                db_status = instance['status']
                database_name = instance['database_name']
                
                # Generate expected container name
                expected_container_name = f"odoo_{database_name}_{instance_id.hex[:8]}"
                
                try:
                    # Check if container exists and get its status
                    container = client.containers.get(expected_container_name)
                    docker_status = container.status.lower()
                    
                    # Map Docker status to our status
                    status_map = {
                        'running': InstanceStatus.RUNNING.value,
                        'exited': InstanceStatus.STOPPED.value,
                        'stopped': InstanceStatus.STOPPED.value,
                        'paused': InstanceStatus.SUSPENDED.value,
                        'restarting': InstanceStatus.RESTARTING.value,
                        'dead': InstanceStatus.ERROR.value,
                    }
                    
                    expected_db_status = status_map.get(docker_status, InstanceStatus.ERROR.value)
                    
                    # Check for mismatch
                    if db_status != expected_db_status:
                        logger.info("Status mismatch detected", 
                                  instance_id=str(instance_id),
                                  db_status=db_status,
                                  docker_status=docker_status,
                                  expected_status=expected_db_status)
                        
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
                            'docker_status': docker_status
                        })
                
                except docker.errors.NotFound:
                    # Container doesn't exist but instance is not terminated
                    if db_status not in [InstanceStatus.STOPPED.value, InstanceStatus.ERROR.value]:
                        logger.warning("Container not found for active instance", 
                                     instance_id=str(instance_id),
                                     expected_container=expected_container_name,
                                     current_status=db_status)
                        
                        # Mark as stopped
                        await conn.execute("""
                            UPDATE instances 
                            SET status = $1, error_message = $2, updated_at = $3
                            WHERE id = $4
                        """, InstanceStatus.STOPPED.value, "Container not found", datetime.utcnow(), instance_id)
                        
                        updated_count += 1
                        mismatched.append({
                            'instance_id': str(instance_id),
                            'old_status': db_status,
                            'new_status': InstanceStatus.STOPPED.value,
                            'reason': 'container_not_found'
                        })
                
                except Exception as e:
                    logger.error("Error checking container status", 
                               instance_id=str(instance_id),
                               container=expected_container_name,
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