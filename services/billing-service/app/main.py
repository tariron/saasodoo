"""
Billing Service - Main Application
FastAPI microservice for handling billing operations with KillBill integration
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os

from .routes import accounts, subscriptions, webhooks, payments, invoices, instances, plans, trial
from .utils.database import init_db, close_db, get_all_current_entitlements
from .utils.killbill_client import KillBillClient

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan management"""
    # Startup
    logger.info("Starting Billing Service...")
    await init_db()

    # Load current plan entitlements from database
    try:
        entitlements_rows = await get_all_current_entitlements()
        app.state.plan_entitlements = {
            row['plan_name']: {
                'cpu_limit': float(row['cpu_limit']),
                'memory_limit': row['memory_limit'],
                'storage_limit': row['storage_limit'],
                'description': row['description'],
                'effective_date': row['effective_date'],
                'db_type': row.get('db_type', 'shared')  # NEW: Include db_type for database allocation
            }
            for row in entitlements_rows
        }
        logger.info(f"Loaded entitlements for {len(app.state.plan_entitlements)} plans (with db_type)")
        # DEBUG: Log premium-monthly specifically
        if 'premium-monthly' in app.state.plan_entitlements:
            logger.info(f"DEBUG premium-monthly cache: {app.state.plan_entitlements['premium-monthly']}")
    except Exception as e:
        logger.error(f"Failed to load plan entitlements: {e}")
        app.state.plan_entitlements = {}

    # Initialize KillBill client
    app.state.killbill = KillBillClient(
        base_url=os.getenv("KILLBILL_URL", "http://killbill:8080"),
        api_key=os.getenv("KILLBILL_API_KEY", "fresh-tenant"),
        api_secret=os.getenv("KILLBILL_API_SECRET", "fresh-secret"),
        username=os.getenv("KILLBILL_USERNAME", "admin"),
        password=os.getenv("KILLBILL_PASSWORD", "password")
    )

    # Check KillBill health before proceeding - fail fast if not ready
    logger.info("Checking KillBill health...")
    health = await app.state.killbill.health_check()
    if health["status"] != "healthy":
        raise Exception(f"KillBill is not ready: {health.get('error', 'Unknown error')}")
    logger.info("KillBill is healthy and ready")

    # Check and create KillBill tenant if needed
    try:
        tenant_exists = await app.state.killbill.check_tenant_exists()
        if not tenant_exists:
            logger.info("KillBill tenant does not exist, creating...")
            await app.state.killbill.create_tenant()
            logger.info("Successfully created KillBill tenant")
        else:
            logger.info("KillBill tenant already exists")
    except Exception as e:
        logger.error(f"Failed to check/create tenant: {e}")
        logger.warning("Continuing without tenant verification")

    # Register webhook with KillBill
    try:
        webhook_url = os.getenv("KILLBILL_NOTIFICATION_URL", "http://billing-service:8004/api/billing/webhooks/killbill")
        await app.state.killbill.register_webhook(webhook_url)
        logger.info(f"Successfully registered webhook: {webhook_url}")
    except Exception as e:
        logger.warning(f"Failed to register webhook during startup: {e}")
        logger.info("Webhook registration can be done manually if needed")

    # Upload overdue configuration if not already configured
    try:
        existing_overdue = await app.state.killbill.get_overdue_config()
        if existing_overdue:
            logger.info("Overdue configuration already exists, skipping upload")
        else:
            logger.info("Uploading overdue configuration...")
            overdue_xml_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "overdue.xml")
            if os.path.exists(overdue_xml_path):
                with open(overdue_xml_path, 'r') as f:
                    overdue_xml = f.read()
                await app.state.killbill.upload_overdue_config(overdue_xml)
                logger.info("Successfully uploaded overdue configuration")
            else:
                logger.warning(f"Overdue.xml not found at {overdue_xml_path}")
    except Exception as e:
        logger.warning(f"Failed to check/upload overdue configuration: {e}")
        logger.info("Overdue configuration can be uploaded manually if needed")

    # Upload catalog configuration if not already configured
    try:
        existing_plans = await app.state.killbill.get_catalog_plans()
        if existing_plans:
            logger.info(f"Catalog already exists with {len(existing_plans)} plans, skipping upload")
        else:
            logger.info("Uploading catalog configuration...")
            catalog_xml_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "killbill_catalog.xml")
            if os.path.exists(catalog_xml_path):
                with open(catalog_xml_path, 'r') as f:
                    catalog_xml = f.read()
                await app.state.killbill.upload_catalog_config(catalog_xml)
                logger.info("Successfully uploaded catalog configuration")
            else:
                logger.warning(f"killbill_catalog.xml not found at {catalog_xml_path}")
    except Exception as e:
        logger.warning(f"Failed to check/upload catalog configuration: {e}")
        logger.info("Catalog configuration can be uploaded manually if needed")

    logger.info("Billing Service started successfully")
    yield
    
    # Shutdown
    logger.info("Shutting down Billing Service...")
    await app.state.killbill.close()
    await close_db()

# Create FastAPI app
app = FastAPI(
    title="Billing Service",
    description="SaaS Odoo Billing Service with KillBill integration",
    version="1.0.0",
    lifespan=lifespan
)

# CORS Configuration from environment
def get_cors_origins():
    origins = os.getenv("CORS_ALLOWED_ORIGINS", "")
    if origins:
        return [o.strip() for o in origins.split(",") if o.strip()]
    return ["http://localhost:3000"]  # Development fallback

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_cors_origins(),
    allow_credentials=os.getenv("CORS_ALLOW_CREDENTIALS", "true").lower() == "true",
    allow_methods=os.getenv("CORS_ALLOWED_METHODS", "GET,POST,PUT,DELETE,OPTIONS").split(","),
    allow_headers=os.getenv("CORS_ALLOWED_HEADERS", "Authorization,Content-Type").split(","),
)

# Include routers
app.include_router(accounts.router, prefix="/api/billing/accounts", tags=["accounts"])
app.include_router(subscriptions.router, prefix="/api/billing/subscriptions", tags=["subscriptions"])
app.include_router(payments.router, prefix="/api/billing/payments", tags=["payments"])
app.include_router(invoices.router, prefix="/api/billing", tags=["invoices"])
app.include_router(instances.router, prefix="/api/billing/instances", tags=["instances"])
app.include_router(plans.router, prefix="/api/billing/plans", tags=["plans"])
app.include_router(trial.router, prefix="/api/billing/trial-eligibility", tags=["trial"])
app.include_router(webhooks.router, prefix="/api/billing/webhooks", tags=["webhooks"])

@app.get("/")
async def root():
    """Root endpoint"""
    return {"service": "billing-service", "status": "running", "version": "1.0.0"}

@app.get("/health")
async def health_check():
    """Health check endpoint"""
    try:
        # Test KillBill connection
        killbill_status = await app.state.killbill.health_check()
        
        return {
            "status": "healthy",
            "service": "billing-service",
            "killbill": killbill_status
        }
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service unhealthy")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8004)
