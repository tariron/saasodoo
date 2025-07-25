"""
Billing Service - Instance Routes
Handles frontend instance creation with billing integration
"""

from fastapi import APIRouter, HTTPException, Depends, Request
from typing import Dict, Any, Optional, List
import logging
from pydantic import BaseModel, Field, validator
from uuid import UUID

from ..utils.killbill_client import KillBillClient

logger = logging.getLogger(__name__)

router = APIRouter()

class CreateInstanceWithSubscriptionRequest(BaseModel):
    """Request to create instance with billing subscription"""
    customer_id: str = Field(..., description="Customer UUID")
    plan_name: str = Field(default="basic-immediate", description="Billing plan (basic-immediate, standard-immediate, etc.)")
    
    # Instance identification for reactivation
    instance_id: Optional[str] = Field(None, description="Existing instance ID to reactivate (for terminated instance recovery)")
    
    # Instance configuration
    name: str = Field(..., min_length=1, max_length=100, description="Instance display name")
    description: Optional[str] = Field(None, max_length=500, description="Instance description")
    admin_email: str = Field(..., description="Odoo admin email")
    admin_password: str = Field(..., min_length=8, description="Odoo admin password")
    subdomain: Optional[str] = Field(None, min_length=3, max_length=50, description="Custom subdomain")
    database_name: str = Field(..., min_length=1, max_length=50, description="Database name")
    
    # Instance settings
    odoo_version: str = Field(default="17.0", description="Odoo version")
    instance_type: str = Field(default="production", description="Instance type (development, staging, production)")
    demo_data: bool = Field(default=False, description="Install demo data")
    
    # Resource limits
    cpu_limit: float = Field(default=1.0, ge=0.1, le=8.0, description="CPU limit in cores")
    memory_limit: str = Field(default="1G", description="Memory limit (e.g., 512M, 1G, 2G)")
    storage_limit: str = Field(default="10G", description="Storage limit (e.g., 5G, 10G, 20G)")
    
    # Additional settings
    custom_addons: List[str] = Field(default_factory=list, description="Custom addon names")
    phase_type: Optional[str] = Field(None, description="Target phase type: TRIAL or EVERGREEN")
    
    @validator('admin_password')
    def validate_admin_password(cls, v):
        """Validate admin password strength"""
        if len(v) < 8:
            raise ValueError('Admin password must be at least 8 characters long')
        if not any(c.isupper() for c in v):
            raise ValueError('Admin password must contain at least one uppercase letter')
        if not any(c.islower() for c in v):
            raise ValueError('Admin password must contain at least one lowercase letter')
        if not any(c.isdigit() for c in v):
            raise ValueError('Admin password must contain at least one digit')
        return v

    @validator('subdomain')
    def validate_subdomain(cls, v):
        """Validate subdomain format"""
        if v is not None:
            if not v.replace('-', '').isalnum():
                raise ValueError('Subdomain must contain only alphanumeric characters and hyphens')
            if v.startswith('-') or v.endswith('-'):
                raise ValueError('Subdomain cannot start or end with a hyphen')
        return v.lower() if v else None

class CreateInstanceWithSubscriptionResponse(BaseModel):
    """Response for instance+subscription creation"""
    success: bool
    subscription_id: str
    subscription: Dict[str, Any]
    invoice: Optional[Dict[str, Any]] = None
    message: str
    instance_config: Dict[str, Any]

def get_killbill_client(request: Request) -> KillBillClient:
    """Dependency to get KillBill client"""
    return request.app.state.killbill

@router.post("/", response_model=CreateInstanceWithSubscriptionResponse)
async def create_instance_with_subscription(
    instance_data: CreateInstanceWithSubscriptionRequest,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """Create a subscription with instance configuration for payment-required instances"""
    try:
        logger.info(f"Creating instance+subscription for customer {instance_data.customer_id}")
        
        # Validate customer has KillBill account
        account = await killbill.get_account_by_external_key(instance_data.customer_id)
        if not account:
            raise HTTPException(status_code=404, detail="Customer billing account not found")
        
        account_id = account.get("accountId")
        
        # Prepare instance configuration to store in subscription metadata
        instance_config = {
            "name": instance_data.name,
            "description": instance_data.description or f"Instance for {instance_data.plan_name} plan",
            "admin_email": instance_data.admin_email,
            "admin_password": instance_data.admin_password,
            "subdomain": instance_data.subdomain,
            "database_name": instance_data.database_name,
            "odoo_version": instance_data.odoo_version,
            "instance_type": instance_data.instance_type,
            "demo_data": str(instance_data.demo_data).lower(),
            "cpu_limit": str(instance_data.cpu_limit),
            "memory_limit": instance_data.memory_limit,
            "storage_limit": instance_data.storage_limit,
            "custom_addons": ",".join(instance_data.custom_addons) if instance_data.custom_addons else ""
        }
        
        # Only check trial eligibility if user is requesting a trial
        if instance_data.phase_type == "TRIAL":
            logger.info(f"Checking trial eligibility for customer {instance_data.customer_id}")
            
            # Get existing subscriptions for trial eligibility check
            existing_subscriptions = await killbill.get_account_subscriptions(account_id)
            
            # Count existing trial subscriptions
            trial_count = 0
            for sub in existing_subscriptions:
                sub_phase = sub.get('phaseType', '')
                if sub_phase == 'TRIAL':
                    trial_count += 1
            
            if trial_count > 0:
                logger.warning(f"Trial eligibility check failed - customer {instance_data.customer_id} has {trial_count} existing trial subscriptions")
                raise HTTPException(
                    status_code=400, 
                    detail=f"Trial limit exceeded. You already have {trial_count} active trial subscription(s). Only one trial per customer is allowed."
                )
            
            logger.info(f"Trial eligibility check passed - customer {instance_data.customer_id} has no existing trials")
        else:
            logger.info(f"Skipping trial eligibility check for customer {instance_data.customer_id} - not requesting trial phase")
        
        logger.info(f"Creating KillBill subscription with plan {instance_data.plan_name}")
        
        # Create KillBill subscription (this will generate an invoice for immediate payment)
        subscription = await killbill.create_subscription(
            account_id=account_id,
            plan_name=instance_data.plan_name,
            billing_period="MONTHLY",
            phase_type=instance_data.phase_type
        )
        
        subscription_id = subscription.get("subscriptionId")
        if not subscription_id:
            raise HTTPException(status_code=500, detail="Failed to create subscription - no ID returned")
        
        logger.info(f"Created subscription {subscription_id}, adding instance metadata")
        
        # Store instance configuration in subscription custom fields
        try:
            metadata = {
                "instance_admin_email": instance_data.admin_email,
                "instance_admin_password": instance_data.admin_password,
                "instance_subdomain": instance_data.subdomain or "",
                "instance_name": instance_data.name,
                "instance_description": instance_data.description or "",
                "instance_database_name": instance_data.database_name,
                "instance_odoo_version": instance_data.odoo_version,
                "instance_type": instance_data.instance_type,
                "instance_demo_data": str(instance_data.demo_data).lower(),
                "instance_cpu_limit": str(instance_data.cpu_limit),
                "instance_memory_limit": instance_data.memory_limit,
                "instance_storage_limit": instance_data.storage_limit,
                "instance_custom_addons": ",".join(instance_data.custom_addons) if instance_data.custom_addons else ""
            }
            
            # Add target instance ID if this is for reactivating an existing instance
            if instance_data.instance_id:
                metadata["target_instance_id"] = instance_data.instance_id
                logger.info(f"Storing target_instance_id {instance_data.instance_id} for subscription {subscription_id}")
            
            await killbill._add_subscription_metadata(subscription_id, metadata)
            logger.info(f"Successfully stored instance configuration in subscription {subscription_id} metadata")
        except Exception as meta_error:
            logger.error(f"Failed to store instance metadata: {meta_error}")
            # Don't fail the entire operation for metadata issues, but log it
        
        # Get the generated invoice for payment
        invoice = None
        try:
            account_invoices = await killbill._make_request("GET", f"/1.0/kb/accounts/{account_id}/invoices")
            if account_invoices:
                # Get the most recent invoice (last in list)
                latest_invoice = account_invoices[-1]
                invoice_id = latest_invoice.get("invoiceId")
                if invoice_id:
                    invoice = await killbill.get_invoice_by_id(invoice_id)
                    logger.info(f"Retrieved invoice {invoice_id} for subscription {subscription_id}")
        except Exception as invoice_error:
            logger.warning(f"Could not retrieve invoice for subscription {subscription_id}: {invoice_error}")
        
        response_data = {
            "success": True,
            "subscription_id": subscription_id,
            "subscription": subscription,
            "invoice": invoice,
            "message": f"Subscription created for {instance_data.plan_name} plan. Pay the invoice to activate your instance.",
            "instance_config": instance_config
        }
        
        logger.info(f"Successfully created subscription {subscription_id} with instance configuration for customer {instance_data.customer_id}")
        return response_data
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to create instance+subscription for customer {instance_data.customer_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to create instance subscription: {str(e)}")