"""
Billing Service - Main Application
FastAPI microservice for handling billing operations with KillBill integration
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging
import os

from .routes import accounts, subscriptions, webhooks, payments, invoices, instances, plans
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
                'effective_date': row['effective_date']
            }
            for row in entitlements_rows
        }
        logger.info(f"Loaded entitlements for {len(app.state.plan_entitlements)} plans")
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

    # Always upload overdue configuration on startup to ensure it's up to date
    try:
        logger.info("Uploading overdue configuration...")

        # Read overdue.xml file
        overdue_xml_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "overdue.xml")
        if os.path.exists(overdue_xml_path):
            with open(overdue_xml_path, 'r') as f:
                overdue_xml = f.read()

            await app.state.killbill.upload_overdue_config(overdue_xml)
            logger.info("Successfully uploaded overdue configuration")
        else:
            logger.warning(f"Overdue.xml not found at {overdue_xml_path}")
    except Exception as e:
        logger.warning(f"Failed to upload overdue configuration: {e}")
        logger.info("Overdue configuration can be uploaded manually if needed")

    logger.info("Billing Service started successfully")
    yield
    
    # Shutdown
    logger.info("Shutting down Billing Service...")
    await close_db()

# Create FastAPI app
app = FastAPI(
    title="Billing Service",
    description="SaaS Odoo Billing Service with KillBill integration",
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

# Include routers
app.include_router(accounts.router, prefix="/api/billing/accounts", tags=["accounts"])
app.include_router(subscriptions.router, prefix="/api/billing/subscriptions", tags=["subscriptions"])
app.include_router(payments.router, prefix="/api/billing/payments", tags=["payments"])
app.include_router(invoices.router, prefix="/api/billing", tags=["invoices"])
app.include_router(instances.router, prefix="/api/billing/instances", tags=["instances"])
app.include_router(plans.router, prefix="/api/billing/plans", tags=["plans"])
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
