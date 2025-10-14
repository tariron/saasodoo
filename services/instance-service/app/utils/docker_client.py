"""
Centralized Docker client wrapper for instance service
"""

import docker
import time
import re
from typing import Dict, Any, Optional, List
from datetime import datetime
import structlog

logger = structlog.get_logger(__name__)


class DockerClientWrapper:
    """Centralized Docker client with error handling and retry logic"""
    
    def __init__(self, max_retries: int = 3, retry_delay: float = 1.0):
        self.client = None
        self.max_retries = max_retries
        self.retry_delay = retry_delay
        self._last_connection_check = 0
        self._connection_check_interval = 30  # seconds
        
        # Container name pattern
        self.container_pattern = re.compile(r'^odoo_([^_]+)_([a-f0-9]{8})$')
        
    def _ensure_connection(self):
        """Ensure Docker client is connected with retry logic"""
        current_time = time.time()
        
        # Check if we need to verify connection
        if (self.client is None or 
            current_time - self._last_connection_check > self._connection_check_interval):
            
            for attempt in range(self.max_retries):
                try:
                    if self.client is None:
                        self.client = docker.from_env()
                    
                    # Test connection
                    self.client.ping()
                    self._last_connection_check = current_time
                    
                    if attempt > 0:
                        logger.info("Docker client reconnected successfully", attempt=attempt + 1)
                    
                    return
                    
                except Exception as e:
                    if attempt == self.max_retries - 1:
                        logger.error("Failed to connect to Docker after all retries", 
                                   error=str(e), 
                                   attempts=self.max_retries)
                        raise
                    else:
                        logger.warning("Docker connection failed, retrying", 
                                     error=str(e), 
                                     attempt=attempt + 1, 
                                     max_retries=self.max_retries)
                        time.sleep(self.retry_delay * (2 ** attempt))  # Exponential backoff
    
    def get_container(self, container_name: str) -> Optional[docker.models.containers.Container]:
        """Get container by name with error handling"""
        try:
            self._ensure_connection()
            return self.client.containers.get(container_name)
        except docker.errors.NotFound:
            logger.debug("Container not found", container=container_name)
            return None
        except Exception as e:
            logger.error("Failed to get container", container=container_name, error=str(e))
            raise
    
    def list_saasodoo_containers(self) -> List[Dict[str, Any]]:
        """List all SaaS Odoo containers with metadata"""
        try:
            self._ensure_connection()
            
            # Get all containers (including stopped ones)
            all_containers = self.client.containers.list(all=True)
            saasodoo_containers = []
            
            for container in all_containers:
                if self.is_saasodoo_container(container.name):
                    container_info = self.extract_container_metadata(container.name)
                    if container_info:
                        container_info.update({
                            'container_id': container.id,
                            'status': container.status,
                            'created': container.attrs.get('Created', ''),
                            'labels': container.labels or {}
                        })
                        saasodoo_containers.append(container_info)
            
            logger.debug("Found SaaS Odoo containers", count=len(saasodoo_containers))
            return saasodoo_containers
            
        except Exception as e:
            logger.error("Failed to list SaaS Odoo containers", error=str(e))
            raise
    
    def is_saasodoo_container(self, container_name: str) -> bool:
        """Check if container follows SaaS Odoo naming pattern"""
        return bool(self.container_pattern.match(container_name))
    
    def extract_container_metadata(self, container_name: str) -> Optional[Dict[str, str]]:
        """Extract metadata from SaaS Odoo container name"""
        match = self.container_pattern.match(container_name)
        if match:
            database_name, instance_id_hex = match.groups()
            return {
                'container_name': container_name,
                'database_name': database_name,
                'instance_id_hex': instance_id_hex
            }
        return None
    
    def get_container_status(self, container_name: str) -> Optional[str]:
        """Get container status with error handling"""
        try:
            container = self.get_container(container_name)
            if container:
                container.reload()  # Refresh status
                return container.status.lower()
            return None
        except Exception as e:
            logger.error("Failed to get container status", container=container_name, error=str(e))
            return None
    
    def get_container_info(self, container_name: str) -> Optional[Dict[str, Any]]:
        """Get comprehensive container information"""
        try:
            container = self.get_container(container_name)
            if not container:
                return None
            
            container.reload()  # Refresh data
            
            # Get network information
            networks = container.attrs.get('NetworkSettings', {}).get('Networks', {})
            network_info = {}
            for network_name, network_data in networks.items():
                network_info[network_name] = {
                    'ip_address': network_data.get('IPAddress'),
                    'gateway': network_data.get('Gateway'),
                    'mac_address': network_data.get('MacAddress')
                }
            
            # Get port bindings
            port_bindings = {}
            ports = container.attrs.get('NetworkSettings', {}).get('Ports', {})
            for internal_port, bindings in ports.items():
                if bindings:
                    port_bindings[internal_port] = bindings[0].get('HostPort')
            
            return {
                'container_id': container.id,
                'name': container.name,
                'status': container.status.lower(),
                'state': container.attrs.get('State', {}),
                'created': container.attrs.get('Created'),
                'started_at': container.attrs.get('State', {}).get('StartedAt'),
                'finished_at': container.attrs.get('State', {}).get('FinishedAt'),
                'network_info': network_info,
                'port_bindings': port_bindings,
                'labels': container.labels or {},
                'image': container.image.tags[0] if container.image.tags else container.image.id,
                'command': container.attrs.get('Config', {}).get('Cmd', []),
                'environment': container.attrs.get('Config', {}).get('Env', [])
            }
            
        except Exception as e:
            logger.error("Failed to get container info", container=container_name, error=str(e))
            return None
    
    def start_container(self, container_name: str, timeout: int = 30) -> Dict[str, Any]:
        """Start container with timeout and status verification"""
        try:
            container = self.get_container(container_name)
            if not container:
                raise ValueError(f"Container {container_name} not found")
            
            logger.info("Starting container", container=container_name)
            
            if container.status.lower() == 'running':
                logger.info("Container is already running", container=container_name)
                return self._get_start_result(container)
            
            # Start container
            container.start()
            
            # Wait for container to be running
            start_time = time.time()
            while time.time() - start_time < timeout:
                container.reload()
                if container.status.lower() == 'running':
                    logger.info("Container started successfully", container=container_name)
                    return self._get_start_result(container)
                time.sleep(1)
            
            raise TimeoutError(f"Container {container_name} failed to start within {timeout} seconds")
            
        except Exception as e:
            logger.error("Failed to start container", container=container_name, error=str(e))
            raise
    
    def stop_container(self, container_name: str, timeout: int = 30) -> bool:
        """Stop container gracefully with timeout"""
        try:
            container = self.get_container(container_name)
            if not container:
                logger.warning("Container not found for stop", container=container_name)
                return True  # Consider success if container doesn't exist
            
            logger.info("Stopping container", container=container_name)
            
            if container.status.lower() in ['stopped', 'exited']:
                logger.info("Container is already stopped", container=container_name)
                return True
            
            # Stop container gracefully
            container.stop(timeout=timeout)
            
            # Verify stopped status
            container.reload()
            logger.info("Container stopped successfully", 
                       container=container_name, 
                       status=container.status)
            
            return True
            
        except Exception as e:
            logger.error("Failed to stop container", container=container_name, error=str(e))
            raise
    
    def restart_container(self, container_name: str, timeout: int = 30) -> Dict[str, Any]:
        """Restart container with timeout and status verification"""
        try:
            container = self.get_container(container_name)
            if not container:
                raise ValueError(f"Container {container_name} not found")
            
            logger.info("Restarting container", container=container_name)
            
            # Restart container
            container.restart(timeout=timeout)
            
            # Wait for container to be running
            start_time = time.time()
            while time.time() - start_time < timeout:
                container.reload()
                if container.status.lower() == 'running':
                    logger.info("Container restarted successfully", container=container_name)
                    return self._get_start_result(container)
                time.sleep(1)
            
            raise TimeoutError(f"Container {container_name} failed to restart within {timeout} seconds")
            
        except Exception as e:
            logger.error("Failed to restart container", container=container_name, error=str(e))
            raise
    
    def _get_start_result(self, container) -> Dict[str, Any]:
        """Get standardized start result"""
        container.reload()
        
        # Get network IP
        networks = container.attrs.get('NetworkSettings', {}).get('Networks', {})
        internal_ip = None
        for network_data in networks.values():
            if network_data.get('IPAddress'):
                internal_ip = network_data['IPAddress']
                break
        
        # Get port mappings
        port_bindings = {}
        ports = container.attrs.get('NetworkSettings', {}).get('Ports', {})
        for internal_port, bindings in ports.items():
            if bindings:
                port_bindings[internal_port] = bindings[0].get('HostPort')
        
        return {
            'container_id': container.id,
            'container_name': container.name,
            'status': container.status.lower(),
            'internal_ip': internal_ip,
            'port_bindings': port_bindings,
            'started_at': container.attrs.get('State', {}).get('StartedAt'),
            'external_url': self._generate_external_url(container.name, port_bindings)
        }
    
    def _generate_external_url(self, container_name: str, port_bindings: Dict[str, str]) -> Optional[str]:
        """Generate external URL for container if port 8069 is mapped"""
        # Check if Odoo port (8069) is mapped
        for internal_port, external_port in port_bindings.items():
            if '8069' in internal_port and external_port:
                # Extract database name from container name for subdomain
                metadata = self.extract_container_metadata(container_name)
                if metadata:
                    # Generate URL based on container metadata
                    # This could be customized based on your domain setup
                    subdomain = metadata['database_name']
                    return f"http://{subdomain}.localhost:{external_port}"
        
        return None
    
    def get_container_logs(self, container_name: str, tail: int = 100) -> Optional[str]:
        """Get container logs with error handling"""
        try:
            container = self.get_container(container_name)
            if not container:
                return None
            
            logs = container.logs(tail=tail, timestamps=True).decode('utf-8')
            return logs
            
        except Exception as e:
            logger.error("Failed to get container logs", container=container_name, error=str(e))
            return None
    
    def container_health_check(self, container_name: str) -> Dict[str, Any]:
        """Perform health check on container"""
        try:
            container = self.get_container(container_name)
            if not container:
                return {
                    'healthy': False,
                    'status': 'not_found',
                    'message': 'Container not found'
                }
            
            container.reload()
            
            # Check container status
            if container.status.lower() != 'running':
                return {
                    'healthy': False,
                    'status': container.status.lower(),
                    'message': f'Container is {container.status.lower()}'
                }
            
            # Check if container has been running for at least 10 seconds
            state = container.attrs.get('State', {})
            started_at = state.get('StartedAt')
            if started_at:
                try:
                    from datetime import datetime
                    start_time = datetime.fromisoformat(started_at.replace('Z', '+00:00'))
                    uptime = (datetime.now(start_time.tzinfo) - start_time).total_seconds()
                    
                    if uptime < 10:
                        return {
                            'healthy': False,
                            'status': 'starting',
                            'message': f'Container recently started ({uptime:.1f}s ago)',
                            'uptime': uptime
                        }
                except Exception:
                    pass  # Ignore datetime parsing errors
            
            # Container appears healthy
            return {
                'healthy': True,
                'status': 'running',
                'message': 'Container is running normally',
                'restart_count': state.get('RestartCount', 0),
                'pid': state.get('Pid'),
                'started_at': started_at
            }
            
        except Exception as e:
            logger.error("Container health check failed", container=container_name, error=str(e))
            return {
                'healthy': False,
                'status': 'error',
                'message': f'Health check failed: {str(e)}'
            }
    
    def update_container_resources(self, container_name: str, cpu_limit: float, memory_bytes: int) -> bool:
        """Update container resource limits (CPU and memory) with zero downtime

        Args:
            container_name: Name of the container to update
            cpu_limit: CPU limit in cores (e.g., 4.0 for 4 CPUs)
            memory_bytes: Memory limit in bytes

        Returns:
            True if successful, False otherwise
        """
        try:
            self._ensure_connection()
            container = self.client.containers.get(container_name)

            # Update container resources
            # For update(), we need to use cpu_period and cpu_quota (not nano_cpus)
            # cpu_period: default is 100000 microseconds (100ms)
            # cpu_quota: cpu_limit * cpu_period (e.g., 4.0 CPUs * 100000 = 400000)
            container.update(
                cpu_period=100000,
                cpu_quota=int(cpu_limit * 100000),
                mem_limit=memory_bytes,
                memswap_limit=memory_bytes  # Set memswap = memory (no swap)
            )

            logger.info("Successfully updated container resources",
                       container=container_name,
                       cpu_limit=cpu_limit,
                       memory_mb=memory_bytes // (1024 * 1024))
            return True

        except docker.errors.NotFound:
            logger.error("Container not found for resource update", container=container_name)
            return False
        except Exception as e:
            logger.error("Failed to update container resources",
                        container=container_name,
                        error=str(e))
            return False

    def cleanup_orphaned_containers(self) -> List[str]:
        """Remove containers that don't have corresponding database entries"""
        # This would require database access, so it's a placeholder for now
        # Implementation would involve:
        # 1. Get all SaaS Odoo containers
        # 2. Query database for corresponding instances
        # 3. Remove containers that don't have database entries
        # 4. Return list of cleaned up container names

        logger.info("Orphaned container cleanup not implemented yet")
        return []


# Global instance for reuse
_docker_client = DockerClientWrapper()


def get_docker_client() -> DockerClientWrapper:
    """Get the global Docker client instance"""
    return _docker_client