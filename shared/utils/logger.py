"""
Logging utilities for Odoo SaaS Kit

Provides centralized logging configuration and utilities.
"""

import os
import sys
import logging
import logging.config
from typing import Optional, Dict, Any
import yaml
from pathlib import Path

# Default logging configuration
DEFAULT_LOGGING_CONFIG = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'detailed': {
            'format': '%(asctime)s - %(name)s - %(levelname)s - %(module)s - %(funcName)s - %(lineno)d - %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
        'json': {
            'format': '{"timestamp": "%(asctime)s", "logger": "%(name)s", "level": "%(levelname)s", "module": "%(module)s", "function": "%(funcName)s", "line": %(lineno)d, "message": "%(message)s"}',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        }
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'level': 'INFO',
            'formatter': 'default',
            'stream': 'ext://sys.stdout'
        }
    },
    'loggers': {
        'root': {
            'level': 'INFO',
            'handlers': ['console'],
            'propagate': False
        },
        'odoo_saas': {
            'level': 'INFO',
            'handlers': ['console'],
            'propagate': False
        }
    }
}


def setup_logging(
    config_path: Optional[str] = None,
    log_level: Optional[str] = None,
    log_format: Optional[str] = None
) -> None:
    """
    Setup logging configuration
    
    Args:
        config_path: Path to logging configuration file
        log_level: Override log level
        log_format: Override log format ('default', 'detailed', 'json')
    """
    # Try to load configuration from file
    config = None
    
    if config_path and os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                if config_path.endswith('.yaml') or config_path.endswith('.yml'):
                    config = yaml.safe_load(f)
                else:
                    # Assume it's a Python dict file
                    import importlib.util
                    spec = importlib.util.spec_from_file_location("config", config_path)
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    config = module.LOGGING_CONFIG
        except Exception as e:
            print(f"Failed to load logging config from {config_path}: {e}")
            config = None
    
    # Try to load from shared configs
    if not config:
        shared_config_path = Path(__file__).parent.parent / "configs" / "logging.yml"
        if shared_config_path.exists():
            try:
                with open(shared_config_path, 'r') as f:
                    config = yaml.safe_load(f)
            except Exception as e:
                print(f"Failed to load shared logging config: {e}")
    
    # Use default config if no file found
    if not config:
        config = DEFAULT_LOGGING_CONFIG.copy()
    
    # Apply environment-specific overrides
    environment = os.getenv('ENVIRONMENT', 'development')
    if environment in config:
        env_config = config[environment]
        
        # Merge environment-specific handlers
        if 'handlers' in env_config:
            config['handlers'].update(env_config['handlers'])
        
        # Merge environment-specific loggers
        if 'loggers' in env_config:
            config['loggers'].update(env_config['loggers'])
    
    # Override log level if specified
    if log_level:
        log_level = log_level.upper()
        for logger_config in config['loggers'].values():
            logger_config['level'] = log_level
        for handler_config in config['handlers'].values():
            handler_config['level'] = log_level
    
    # Override log format if specified
    if log_format and log_format in config['formatters']:
        for handler_config in config['handlers'].values():
            handler_config['formatter'] = log_format
    
    # Create log directory if it doesn't exist
    log_file_path = os.getenv('LOG_FILE_PATH', '/var/log/odoo-saas')
    if log_file_path and not os.path.exists(log_file_path):
        try:
            os.makedirs(log_file_path, exist_ok=True)
        except PermissionError:
            # Fallback to current directory if can't create log directory
            log_file_path = './logs'
            os.makedirs(log_file_path, exist_ok=True)
            
            # Update file handlers to use fallback path
            for handler_config in config['handlers'].values():
                if 'filename' in handler_config:
                    filename = os.path.basename(handler_config['filename'])
                    handler_config['filename'] = os.path.join(log_file_path, filename)
    
    # Apply logging configuration
    try:
        logging.config.dictConfig(config)
        print(f"Logging configured successfully for environment: {environment}")
    except Exception as e:
        print(f"Failed to configure logging: {e}")
        # Fallback to basic configuration
        logging.basicConfig(
            level=getattr(logging, log_level or 'INFO'),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )


def get_logger(name: str) -> logging.Logger:
    """
    Get logger instance
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Logger instance
    """
    return logging.getLogger(name)


class StructuredLogger:
    """Structured logger for JSON logging"""
    
    def __init__(self, name: str):
        self.logger = logging.getLogger(name)
    
    def _log_structured(self, level: int, message: str, **kwargs):
        """Log structured message with additional fields"""
        extra_data = {
            'structured': True,
            **kwargs
        }
        self.logger.log(level, message, extra=extra_data)
    
    def debug(self, message: str, **kwargs):
        """Log debug message with structured data"""
        self._log_structured(logging.DEBUG, message, **kwargs)
    
    def info(self, message: str, **kwargs):
        """Log info message with structured data"""
        self._log_structured(logging.INFO, message, **kwargs)
    
    def warning(self, message: str, **kwargs):
        """Log warning message with structured data"""
        self._log_structured(logging.WARNING, message, **kwargs)
    
    def error(self, message: str, **kwargs):
        """Log error message with structured data"""
        self._log_structured(logging.ERROR, message, **kwargs)
    
    def critical(self, message: str, **kwargs):
        """Log critical message with structured data"""
        self._log_structured(logging.CRITICAL, message, **kwargs)


def get_structured_logger(name: str) -> StructuredLogger:
    """
    Get structured logger instance
    
    Args:
        name: Logger name
        
    Returns:
        StructuredLogger instance
    """
    return StructuredLogger(name)


class RequestLogger:
    """Logger for HTTP requests"""
    
    def __init__(self, name: str = "odoo_saas.requests"):
        self.logger = logging.getLogger(name)
    
    def log_request(
        self,
        method: str,
        url: str,
        status_code: int,
        response_time: float,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None
    ):
        """Log HTTP request"""
        self.logger.info(
            f"{method} {url} {status_code} {response_time:.3f}s",
            extra={
                'request_method': method,
                'request_url': url,
                'response_status': status_code,
                'response_time': response_time,
                'user_id': user_id,
                'ip_address': ip_address,
                'user_agent': user_agent,
                'event_type': 'http_request'
            }
        )


class AuditLogger:
    """Logger for audit events"""
    
    def __init__(self, name: str = "odoo_saas.audit"):
        self.logger = logging.getLogger(name)
    
    def log_user_action(
        self,
        user_id: str,
        action: str,
        resource: str,
        resource_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        ip_address: Optional[str] = None
    ):
        """Log user action for audit trail"""
        self.logger.info(
            f"User {user_id} performed {action} on {resource}",
            extra={
                'user_id': user_id,
                'action': action,
                'resource': resource,
                'resource_id': resource_id,
                'details': details or {},
                'ip_address': ip_address,
                'event_type': 'user_action'
            }
        )
    
    def log_system_event(
        self,
        event: str,
        component: str,
        details: Optional[Dict[str, Any]] = None,
        severity: str = 'info'
    ):
        """Log system event"""
        log_method = getattr(self.logger, severity.lower(), self.logger.info)
        log_method(
            f"System event: {event} in {component}",
            extra={
                'event': event,
                'component': component,
                'details': details or {},
                'event_type': 'system_event'
            }
        )


class PerformanceLogger:
    """Logger for performance metrics"""
    
    def __init__(self, name: str = "odoo_saas.performance"):
        self.logger = logging.getLogger(name)
    
    def log_performance(
        self,
        operation: str,
        duration: float,
        component: str,
        details: Optional[Dict[str, Any]] = None
    ):
        """Log performance metrics"""
        self.logger.info(
            f"Performance: {operation} took {duration:.3f}s in {component}",
            extra={
                'operation': operation,
                'duration': duration,
                'component': component,
                'details': details or {},
                'event_type': 'performance'
            }
        )


# Global logger instances
def get_request_logger() -> RequestLogger:
    """Get request logger instance"""
    return RequestLogger()


def get_audit_logger() -> AuditLogger:
    """Get audit logger instance"""
    return AuditLogger()


def get_performance_logger() -> PerformanceLogger:
    """Get performance logger instance"""
    return PerformanceLogger()


# Context manager for performance logging
class performance_timer:
    """Context manager for timing operations"""
    
    def __init__(self, operation: str, component: str, logger: Optional[PerformanceLogger] = None):
        self.operation = operation
        self.component = component
        self.logger = logger or get_performance_logger()
        self.start_time = None
    
    def __enter__(self):
        import time
        self.start_time = time.time()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        import time
        duration = time.time() - self.start_time
        self.logger.log_performance(self.operation, duration, self.component)


# Initialize logging on module import
def init_logging():
    """Initialize logging with environment variables"""
    config_path = os.getenv('LOGGING_CONFIG_PATH')
    log_level = os.getenv('LOG_LEVEL', 'INFO')
    log_format = os.getenv('LOG_FORMAT', 'default')
    
    setup_logging(config_path, log_level, log_format)


# Auto-initialize if not in test environment
if os.getenv('ENVIRONMENT') != 'testing':
    init_logging() 