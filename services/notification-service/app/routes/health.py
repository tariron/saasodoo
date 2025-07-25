"""
Health Check Routes
Service health monitoring endpoints
"""

from fastapi import APIRouter, HTTPException
from datetime import datetime
import os
import logging
import asyncio
import aiosmtplib
from email.mime.text import MIMEText

router = APIRouter()
logger = logging.getLogger(__name__)

@router.get("/")
async def health_check():
    """Basic health check"""
    return {
        "status": "healthy",
        "service": "notification-service",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0"
    }

@router.get("/detailed")
async def detailed_health_check():
    """Detailed health check including SMTP connectivity"""
    health_status = {
        "status": "healthy",
        "service": "notification-service",
        "timestamp": datetime.utcnow().isoformat(),
        "version": "1.0.0",
        "components": {}
    }
    
    # Check SMTP connectivity
    try:
        smtp_health = await check_smtp_connectivity()
        health_status["components"]["smtp"] = smtp_health
    except Exception as e:
        logger.error(f"SMTP health check failed: {e}")
        health_status["components"]["smtp"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"
    
    # Check environment configuration
    try:
        config_health = check_configuration()
        health_status["components"]["configuration"] = config_health
    except Exception as e:
        logger.error(f"Configuration check failed: {e}")
        health_status["components"]["configuration"] = {
            "status": "unhealthy",
            "error": str(e)
        }
        health_status["status"] = "degraded"
    
    return health_status

async def check_smtp_connectivity():
    """Check SMTP server connectivity"""
    smtp_host = os.getenv('SMTP_HOST', 'mailhog')
    smtp_port = int(os.getenv('SMTP_PORT', '1025'))
    smtp_use_tls = os.getenv('SMTP_USE_TLS', 'false').lower() == 'true'
    smtp_username = os.getenv('SMTP_USERNAME')
    
    try:
        # Create SMTP connection
        smtp = aiosmtplib.SMTP(hostname=smtp_host, port=smtp_port, use_tls=smtp_use_tls)
        
        # Test connection with timeout
        await asyncio.wait_for(smtp.connect(), timeout=10.0)
        
        # Test authentication if credentials provided
        if smtp_username:
            smtp_password = os.getenv('SMTP_PASSWORD')
            if smtp_password:
                await smtp.login(smtp_username, smtp_password)
        
        await smtp.quit()
        
        return {
            "status": "healthy",
            "host": smtp_host,
            "port": smtp_port,
            "tls": smtp_use_tls,
            "authenticated": bool(smtp_username)
        }
        
    except asyncio.TimeoutError:
        raise Exception(f"SMTP connection timeout to {smtp_host}:{smtp_port}")
    except Exception as e:
        raise Exception(f"SMTP connection failed: {str(e)}")

def check_configuration():
    """Check environment configuration"""
    required_vars = ['SMTP_HOST', 'SMTP_PORT']
    optional_vars = ['SMTP_USE_TLS', 'SMTP_USERNAME', 'SMTP_PASSWORD']
    
    config = {}
    missing_required = []
    
    # Check required variables
    for var in required_vars:
        value = os.getenv(var)
        if value:
            config[var] = value
        else:
            missing_required.append(var)
    
    # Check optional variables
    for var in optional_vars:
        value = os.getenv(var)
        if value:
            config[var] = "***" if "PASSWORD" in var else value
    
    if missing_required:
        raise Exception(f"Missing required environment variables: {missing_required}")
    
    return {
        "status": "healthy",
        "config": config
    }