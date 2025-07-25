"""
Notification Service
Email and notification management service
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import logging
import os
from contextlib import asynccontextmanager

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    logger.info("🚀 Notification Service starting up...")
    
    # Validate environment configuration
    smtp_host = os.getenv('SMTP_HOST', 'mailhog')
    smtp_port = os.getenv('SMTP_PORT', '1025')
    logger.info(f"📧 SMTP configured: {smtp_host}:{smtp_port}")
    
    yield
    
    logger.info("📧 Notification Service shutting down...")

# Create FastAPI app
app = FastAPI(
    title="Notification Service",
    description="Email and notification management service for SaaS Odoo Platform",
    version="1.0.0",
    lifespan=lifespan
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Import and include routers
from app.routes import emails, templates, health

app.include_router(health.router, prefix="/health", tags=["Health"])
app.include_router(emails.router, prefix="/api/v1/emails", tags=["Emails"])
app.include_router(templates.router, prefix="/api/v1/templates", tags=["Templates"])

@app.get("/")
async def root():
    """Root endpoint"""
    return {
        "service": "notification-service",
        "status": "running",
        "version": "1.0.0"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", "5000")),
        reload=True
    )