"""
Configuration Management
Environment-based configuration for SMTP, database, and application settings
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import field_validator
import logging

logger = logging.getLogger(__name__)


class SMTPConfig(BaseSettings):
    """SMTP Configuration"""

    # Core SMTP settings
    smtp_host: str = "mailhog"
    smtp_port: int = 1025
    smtp_use_tls: bool = False
    smtp_use_ssl: bool = False
    smtp_timeout: int = 30

    # Authentication (optional)
    smtp_username: Optional[str] = None
    smtp_password: Optional[str] = None

    # Email defaults
    default_from_email: str = "noreply@saasodoo.com"
    default_from_name: str = "SaaSOdoo Platform"

    # Rate limiting
    max_emails_per_minute: int = 60
    max_emails_per_hour: int = 1000

    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0

    class Config:
        env_prefix = ""
        case_sensitive = False

    @field_validator('smtp_port')
    @classmethod
    def validate_smtp_port(cls, v):
        if not 1 <= v <= 65535:
            raise ValueError('SMTP port must be between 1 and 65535')
        return v

    @field_validator('smtp_timeout')
    @classmethod
    def validate_smtp_timeout(cls, v):
        if v < 1:
            raise ValueError('SMTP timeout must be at least 1 second')
        return v

    def is_production_mode(self) -> bool:
        """Check if running in production mode (based on SMTP config)"""
        return self.smtp_host != "mailhog" and self.smtp_port != 1025

    def log_config(self):
        """Log configuration (without sensitive data)"""
        logger.info(f"SMTP Host: {self.smtp_host}:{self.smtp_port}")
        logger.info(f"TLS: {self.smtp_use_tls}, SSL: {self.smtp_use_ssl}")
        logger.info(f"Authentication: {'Yes' if self.smtp_username else 'No'}")
        logger.info(f"From: {self.default_from_name} <{self.default_from_email}>")
        logger.info(f"Rate Limits: {self.max_emails_per_minute}/min, {self.max_emails_per_hour}/hour")
        logger.info(f"Mode: {'Production' if self.is_production_mode() else 'Development'}")


class DatabaseConfig(BaseSettings):
    """Database Configuration - uses service-specific credentials"""

    # Connection settings (use individual env vars to match other services)
    postgres_host: str = "postgres-cluster-rw.saasodoo.svc.cluster.local"
    postgres_port: int = 5432
    db_name: str = "communication"
    db_service_user: str = "notification_service"
    db_service_password: str = "notification_service_secure_pass_change_me"

    # Pool settings
    pool_size: int = 10
    max_overflow: int = 20
    pool_timeout: int = 30

    class Config:
        env_prefix = ""
        case_sensitive = False

    def get_database_url(self) -> str:
        """Build database URL from individual settings"""
        return f"postgresql://{self.db_service_user}:{self.db_service_password}@{self.postgres_host}:{self.postgres_port}/{self.db_name}"

    def log_config(self):
        """Log configuration (without sensitive data)"""
        logger.info(f"Database Host: {self.postgres_host}:{self.postgres_port}")
        logger.info(f"Database: {self.db_name}")
        logger.info(f"User: {self.db_service_user}")
        logger.info(f"Pool Size: {self.pool_size}, Max Overflow: {self.max_overflow}")


class AppConfig(BaseSettings):
    """Application Configuration"""

    # Service info
    service_name: str = "notification-service"
    service_version: str = "1.0.0"
    debug: bool = False

    # API settings
    api_prefix: str = "/api/v1"
    docs_url: str = "/docs"
    openapi_url: str = "/openapi.json"

    # Template settings
    templates_dir: str = "app/templates"
    default_template_language: str = "en"

    # Platform info
    platform_name: str = "SaaSOdoo Platform"
    support_email: str = "support@saasodoo.com"
    support_url: str = "https://support.saasodoo.com"

    class Config:
        env_prefix = "APP_"
        case_sensitive = False


# Global configuration instances
_smtp_config: Optional[SMTPConfig] = None
_db_config: Optional[DatabaseConfig] = None
_app_config: Optional[AppConfig] = None


def get_smtp_config() -> SMTPConfig:
    """Get SMTP configuration instance"""
    global _smtp_config
    if _smtp_config is None:
        _smtp_config = SMTPConfig()
    return _smtp_config


def get_db_config() -> DatabaseConfig:
    """Get database configuration instance"""
    global _db_config
    if _db_config is None:
        _db_config = DatabaseConfig()
    return _db_config


def get_app_config() -> AppConfig:
    """Get application configuration instance"""
    global _app_config
    if _app_config is None:
        _app_config = AppConfig()
    return _app_config


def validate_configuration():
    """Validate all configuration settings"""
    try:
        smtp_config = get_smtp_config()
        db_config = get_db_config()

        # Log SMTP config
        smtp_config.log_config()

        # Log DB config
        db_config.log_config()

        # Check required production settings
        if smtp_config.is_production_mode():
            if not smtp_config.smtp_username or not smtp_config.smtp_password:
                logger.warning("Production SMTP detected but credentials not provided")

        logger.info("Configuration validation completed")
        return True

    except Exception as e:
        logger.error(f"Configuration validation failed: {e}")
        raise
