"""
Configuration Management
Environment-based configuration for SMTP and application settings
"""

import os
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import validator
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
    default_from_email: str = "noreply@saasodoo.local"
    default_from_name: str = "SaaS Odoo Platform"
    
    # Rate limiting
    max_emails_per_minute: int = 60
    max_emails_per_hour: int = 1000
    
    class Config:
        env_prefix = ""
        case_sensitive = False
    
    @validator('smtp_port')
    def validate_smtp_port(cls, v):
        if not 1 <= v <= 65535:
            raise ValueError('SMTP port must be between 1 and 65535')
        return v
    
    @validator('smtp_timeout')
    def validate_smtp_timeout(cls, v):
        if v < 1:
            raise ValueError('SMTP timeout must be at least 1 second')
        return v
    
    def is_production_mode(self) -> bool:
        """Check if running in production mode (based on SMTP config)"""
        return self.smtp_host != "mailhog" and self.smtp_port != 1025
    
    def log_config(self):
        """Log configuration (without sensitive data)"""
        logger.info(f"📧 SMTP Host: {self.smtp_host}:{self.smtp_port}")
        logger.info(f"🔐 TLS: {self.smtp_use_tls}, SSL: {self.smtp_use_ssl}")
        logger.info(f"👤 Authentication: {'Yes' if self.smtp_username else 'No'}")
        logger.info(f"📨 From: {self.default_from_name} <{self.default_from_email}>")
        logger.info(f"⚡ Rate Limits: {self.max_emails_per_minute}/min, {self.max_emails_per_hour}/hour")
        logger.info(f"🏭 Mode: {'Production' if self.is_production_mode() else 'Development'}")

class DatabaseConfig(BaseSettings):
    """Database Configuration"""
    
    database_url: str = "postgresql://notification_service:notification_pass@postgres:5432/communication"
    pool_size: int = 10
    max_overflow: int = 20
    
    class Config:
        env_prefix = "DB_"
        case_sensitive = False

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
    
    class Config:
        env_prefix = "APP_"
        case_sensitive = False

# Global configuration instances
smtp_config = SMTPConfig()
db_config = DatabaseConfig()
app_config = AppConfig()

def get_smtp_config() -> SMTPConfig:
    """Get SMTP configuration instance"""
    return smtp_config

def get_db_config() -> DatabaseConfig:
    """Get database configuration instance"""
    return db_config

def get_app_config() -> AppConfig:
    """Get application configuration instance"""
    return app_config

def validate_configuration():
    """Validate all configuration settings"""
    try:
        # Validate SMTP config
        smtp_config.log_config()
        
        # Check required production settings
        if smtp_config.is_production_mode():
            if not smtp_config.smtp_username or not smtp_config.smtp_password:
                logger.warning("⚠️  Production SMTP detected but credentials not provided")
        
        logger.info("✅ Configuration validation completed")
        return True
        
    except Exception as e:
        logger.error(f"❌ Configuration validation failed: {e}")
        raise

# Validate configuration on import
validate_configuration()