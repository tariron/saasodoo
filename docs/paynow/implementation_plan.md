# Paynow Payment Integration - Complete Implementation Plan

## Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Implementation Steps](#implementation-steps)
4. [Testing Protocol](#testing-protocol)
5. [Troubleshooting](#troubleshooting)

---

## Overview

### Objective
Integrate Paynow payment gateway into the billing-service to support:
- **Mobile Money Payments** (EcoCash, OneMoney) - Direct USSD push to customer's phone
- **Card Payments** (Visa/Mastercard) - Redirect to Paynow payment page

### Key Characteristics
- **Immediate Response**: Paynow returns 200 OK immediately
- **Async Status**: Actual payment status arrives via webhook POST
- **Mobile Flow**: No redirect - customer approves on phone, frontend polls for status
- **Card Flow**: Redirect to Paynow → customer pays → redirect back to frontend

### Payment Flow
```
Frontend → Backend API → Paynow API
                ↓
        Create payment record (status='pending')
                ↓
        Return reference + poll_url to frontend
                ↓
        Frontend polls /status endpoint
                ↓
Paynow webhook arrives → Update payment → Update KillBill
                ↓
        Frontend poll sees status='paid'
```

---

## Architecture

### Database Strategy
**Extend existing `billing.payments` table** (lines 75-85 in `shared/configs/postgres/04-init-schemas.sql.template`)

Current columns:
- id, subscription_id, amount, currency, payment_method, payment_status, gateway_transaction_id, processed_at, created_at

Add Paynow-specific columns:
- paynow_reference (Paynow's internal reference)
- paynow_poll_url (URL to poll Paynow for status)
- paynow_browser_url (URL for card redirect)
- return_url (where to send customer after payment)
- phone (mobile number for EcoCash/OneMoney)
- paynow_status (Paynow's status string)
- webhook_received_at (when webhook arrived)

### API Endpoints

**Payment Initiation:**
```
POST /api/billing/payments/paynow/initiate
Request: {invoice_id, payment_method: "ecocash|onemoney|card", phone?, return_url?}
Response: {reference, payment_type: "mobile|redirect", status, poll_url, redirect_url?}
```

**Status Polling:**
```
GET /api/billing/payments/paynow/status/{payment_id}
Response: {status: "pending|paid|failed|cancelled", amount, payment_method, updated_at}
```

**Webhook Handler:**
```
POST /api/billing/webhooks/paynow
Paynow POST: reference=X&paynowreference=Y&amount=Z&status=Paid&hash=...
Response: 200 OK
```

---

## Implementation Steps

### STEP 1: Database Schema Extension

#### File to Modify: `shared/configs/postgres/04-init-schemas.sql.template`

Find the payments table (around line 75) and modify it:

```sql
-- Around line 75, replace the payments table definition:
CREATE TABLE IF NOT EXISTS payments (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    subscription_id UUID REFERENCES subscriptions(id),
    amount DECIMAL(10,2) NOT NULL,
    currency VARCHAR(3) DEFAULT 'USD',
    payment_method VARCHAR(50) NOT NULL,
    payment_status VARCHAR(50) DEFAULT 'pending',
    gateway_transaction_id VARCHAR(255),
    processed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,

    -- Paynow-specific fields
    paynow_reference VARCHAR(255),
    paynow_poll_url TEXT,
    paynow_browser_url TEXT,
    return_url TEXT,
    phone VARCHAR(20),
    paynow_status VARCHAR(50),
    webhook_received_at TIMESTAMP WITH TIME ZONE
);

-- Update indexes section (after line 94):
CREATE INDEX IF NOT EXISTS idx_payments_subscription_id ON payments(subscription_id);
CREATE INDEX IF NOT EXISTS idx_payments_status ON payments(payment_status);
CREATE INDEX IF NOT EXISTS idx_payments_paynow_ref ON payments(paynow_reference);
CREATE INDEX IF NOT EXISTS idx_payments_gateway_tx_id ON payments(gateway_transaction_id);
CREATE INDEX IF NOT EXISTS idx_payments_phone ON payments(phone);
```

#### Test Step 1:

```bash
# 1. Stop all containers
docker compose -f infrastructure/compose/docker-compose.ceph.yml down

# 2. Remove postgres volume (fresh start - dev only!)
docker volume rm saasodoo_postgres-data

# 3. Start postgres to initialize with new schema
docker compose -f infrastructure/compose/docker-compose.ceph.yml up -d postgres

# 4. Wait for postgres to initialize (watch logs)
docker logs -f saasodoo-postgres
# Wait for: "database system is ready to accept connections"
# Press Ctrl+C when done

# 5. Verify payments table has new columns
docker exec saasodoo-postgres psql -U billing_service -d billing -c "\d payments"

# Expected output: Should see columns including:
# - paynow_reference
# - paynow_poll_url
# - paynow_browser_url
# - return_url
# - phone
# - paynow_status
# - webhook_received_at

# 6. Verify indexes created
docker exec saasodoo-postgres psql -U billing_service -d billing -c "\di"

# Expected: Should see idx_payments_paynow_ref, idx_payments_gateway_tx_id, idx_payments_phone
```

**Success Criteria:**
- ✅ New columns visible in payments table
- ✅ Indexes created
- ✅ No errors in postgres logs

**If Test Fails:**
- Check syntax in 04-init-schemas.sql.template
- Verify postgres container logs: `docker logs saasodoo-postgres | grep ERROR`
- Ensure volume was actually removed: `docker volume ls | grep postgres`

---

### STEP 2: Environment Configuration

#### File to Modify: `infrastructure/compose/docker-compose.ceph.yml`

Find the `billing-service` section and add Paynow environment variables:

```yaml
  billing-service:
    build:
      context: ../../services/billing-service
      dockerfile: Dockerfile
    container_name: saasodoo-billing-service
    restart: unless-stopped
    environment:
      # ... existing environment variables ...

      # Paynow Configuration
      PAYNOW_INTEGRATION_ID: ${PAYNOW_INTEGRATION_ID}
      PAYNOW_INTEGRATION_KEY: ${PAYNOW_INTEGRATION_KEY}
      PAYNOW_RESULT_URL: http://billing-service:8004/api/billing/webhooks/paynow
      PAYNOW_BASE_URL: ${PAYNOW_BASE_URL:-https://www.paynow.co.zw}

      # ... rest of environment variables ...
```

#### File to Modify: `.env` (in project root)

Add these lines to your `.env` file:

```bash
# Paynow Payment Gateway Configuration
# Get these from your Paynow dashboard: Receive Payment Links → Edit Profile
PAYNOW_INTEGRATION_ID=1234
PAYNOW_INTEGRATION_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
PAYNOW_BASE_URL=https://www.paynow.co.zw

# Note: Integration starts in test mode by default
# After testing, request to go live in Paynow dashboard
```

#### Test Step 2:

```bash
# 1. Start billing-service with new environment variables
docker compose -f infrastructure/compose/docker-compose.ceph.yml up -d billing-service

# 2. Verify environment variables are set
docker exec saasodoo-billing-service env | grep PAYNOW

# Expected output:
# PAYNOW_INTEGRATION_ID=1234
# PAYNOW_INTEGRATION_KEY=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
# PAYNOW_RESULT_URL=http://billing-service:8004/api/billing/webhooks/paynow
# PAYNOW_BASE_URL=https://www.paynow.co.zw

# 3. Check billing-service logs for startup
docker logs saasodoo-billing-service --tail 50

# Expected: Service starts without errors
```

**Success Criteria:**
- ✅ All PAYNOW_* environment variables visible
- ✅ billing-service starts without errors
- ✅ No missing environment variable warnings in logs

**If Test Fails:**
- Verify `.env` file exists and has Paynow variables
- Check docker-compose.ceph.yml syntax (proper YAML indentation)
- Try: `docker compose -f infrastructure/compose/docker-compose.ceph.yml config` to validate YAML

---

### STEP 3: Paynow Client Utility

#### File to Create: `services/billing-service/app/utils/paynow_client.py`

```python
"""
Paynow Payment Gateway Client
Handles communication with Paynow API for payments
"""

import hashlib
import os
import logging
from typing import Dict, Optional, Literal
from urllib.parse import urlencode, parse_qs
import httpx

logger = logging.getLogger(__name__)


class PaynowClient:
    """Client for interacting with Paynow payment gateway"""

    def __init__(
        self,
        integration_id: str,
        integration_key: str,
        result_url: str,
        base_url: str = "https://www.paynow.co.zw"
    ):
        self.integration_id = integration_id
        self.integration_key = integration_key
        self.result_url = result_url
        self.base_url = base_url
        self.client = httpx.AsyncClient(timeout=30.0)

    def generate_hash(self, values: Dict[str, str]) -> str:
        """
        Generate SHA512 hash for Paynow message

        Args:
            values: Dictionary of key-value pairs (excluding 'hash' key)

        Returns:
            Uppercase hexadecimal SHA512 hash
        """
        # Concatenate all values (excluding hash key)
        concat_string = ""
        for key, value in values.items():
            if key.upper() != "HASH":
                concat_string += str(value)

        # Append integration key
        concat_string += self.integration_key

        # Generate SHA512 hash
        hash_bytes = hashlib.sha512(concat_string.encode('utf-8')).hexdigest()

        return hash_bytes.upper()

    def validate_hash(self, payload: Dict[str, str]) -> bool:
        """
        Validate hash from Paynow webhook/response

        Args:
            payload: Dictionary containing all fields including 'hash'

        Returns:
            True if hash is valid, False otherwise
        """
        if 'hash' not in payload:
            logger.error("No hash field in payload")
            return False

        received_hash = payload['hash']

        # Generate expected hash (excluding hash field)
        payload_without_hash = {k: v for k, v in payload.items() if k.upper() != 'HASH'}
        expected_hash = self.generate_hash(payload_without_hash)

        is_valid = received_hash.upper() == expected_hash.upper()

        if not is_valid:
            logger.error(f"Hash validation failed. Expected: {expected_hash}, Received: {received_hash}")

        return is_valid

    async def initiate_transaction(
        self,
        reference: str,
        amount: float,
        return_url: str,
        additional_info: str = "",
        auth_email: Optional[str] = None
    ) -> Dict:
        """
        Initiate standard transaction (card payments - redirect flow)

        Args:
            reference: Unique merchant reference
            amount: Amount to charge
            return_url: URL to redirect customer after payment
            additional_info: Optional additional information
            auth_email: Optional customer email

        Returns:
            Dict with status, browserurl, pollurl, hash
        """
        # Build request payload
        payload = {
            "id": self.integration_id,
            "reference": reference,
            "amount": f"{amount:.2f}",
            "additionalinfo": additional_info,
            "returnurl": return_url,
            "resulturl": self.result_url,
            "status": "Message"
        }

        # Add optional auth email
        if auth_email:
            payload["authemail"] = auth_email

        # Generate hash
        payload["hash"] = self.generate_hash(payload)

        # Send request
        url = f"{self.base_url}/interface/initiatetransaction"

        logger.info(f"Initiating Paynow transaction: {reference}")

        try:
            response = await self.client.post(
                url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            # Parse response (URL encoded)
            response_data = parse_qs(response.text)

            # Convert lists to single values
            result = {k: v[0] if isinstance(v, list) and len(v) > 0 else v
                     for k, v in response_data.items()}

            # Validate response hash
            if not self.validate_hash(result):
                logger.error("Invalid hash in Paynow response")
                return {"status": "Error", "error": "Invalid response hash"}

            logger.info(f"Paynow transaction initiated: {result.get('status')}")
            return result

        except Exception as e:
            logger.error(f"Error initiating Paynow transaction: {e}")
            return {"status": "Error", "error": str(e)}

    async def initiate_mobile_transaction(
        self,
        reference: str,
        amount: float,
        phone: str,
        method: Literal["ecocash", "onemoney"],
        auth_email: str,
        additional_info: str = ""
    ) -> Dict:
        """
        Initiate mobile money transaction (EcoCash/OneMoney - USSD push)

        Args:
            reference: Unique merchant reference
            amount: Amount to charge
            phone: Mobile number (e.g., 0771234567)
            method: Payment method (ecocash or onemoney)
            auth_email: Customer email (required for test mode)
            additional_info: Optional additional information

        Returns:
            Dict with status, pollurl, hash
        """
        # Build request payload
        payload = {
            "id": self.integration_id,
            "reference": reference,
            "amount": f"{amount:.2f}",
            "additionalinfo": additional_info,
            "returnurl": self.result_url,  # Not used but required
            "resulturl": self.result_url,
            "authemail": auth_email,
            "phone": phone,
            "method": method,
            "status": "Message"
        }

        # Generate hash
        payload["hash"] = self.generate_hash(payload)

        # Send request to mobile endpoint
        url = f"{self.base_url}/interface/remotetransaction"

        logger.info(f"Initiating Paynow mobile transaction: {reference} ({method} - {phone})")

        try:
            response = await self.client.post(
                url,
                data=payload,
                headers={"Content-Type": "application/x-www-form-urlencoded"}
            )

            # Parse response (URL encoded)
            response_data = parse_qs(response.text)

            # Convert lists to single values
            result = {k: v[0] if isinstance(v, list) and len(v) > 0 else v
                     for k, v in response_data.items()}

            # Validate response hash
            if not self.validate_hash(result):
                logger.error("Invalid hash in Paynow mobile response")
                return {"status": "Error", "error": "Invalid response hash"}

            logger.info(f"Paynow mobile transaction initiated: {result.get('status')}")
            return result

        except Exception as e:
            logger.error(f"Error initiating Paynow mobile transaction: {e}")
            return {"status": "Error", "error": str(e)}

    async def poll_transaction_status(self, poll_url: str) -> Dict:
        """
        Poll Paynow for transaction status

        Args:
            poll_url: Poll URL returned from initiate transaction

        Returns:
            Dict with reference, paynowreference, amount, status, hash
        """
        logger.info(f"Polling Paynow transaction status: {poll_url}")

        try:
            response = await self.client.post(poll_url)

            # Parse response (URL encoded)
            response_data = parse_qs(response.text)

            # Convert lists to single values
            result = {k: v[0] if isinstance(v, list) and len(v) > 0 else v
                     for k, v in response_data.items()}

            # Validate response hash
            if not self.validate_hash(result):
                logger.error("Invalid hash in Paynow poll response")
                return {"status": "Error", "error": "Invalid response hash"}

            logger.info(f"Paynow poll status: {result.get('status')}")
            return result

        except Exception as e:
            logger.error(f"Error polling Paynow transaction: {e}")
            return {"status": "Error", "error": str(e)}

    async def close(self):
        """Close HTTP client"""
        await self.client.aclose()


def get_paynow_client() -> PaynowClient:
    """Factory function to create Paynow client from environment variables"""
    return PaynowClient(
        integration_id=os.getenv("PAYNOW_INTEGRATION_ID"),
        integration_key=os.getenv("PAYNOW_INTEGRATION_KEY"),
        result_url=os.getenv("PAYNOW_RESULT_URL"),
        base_url=os.getenv("PAYNOW_BASE_URL", "https://www.paynow.co.zw")
    )
```

#### Test Step 3:

Create test file: `services/billing-service/tests/test_paynow_client.py`

```python
"""
Tests for Paynow client
"""

import pytest
from app.utils.paynow_client import PaynowClient


def test_hash_generation():
    """Test hash generation with Paynow example"""
    # Example from Paynow docs
    client = PaynowClient(
        integration_id="1201",
        integration_key="3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977",
        result_url="http://example.com/result"
    )

    values = {
        "id": "1201",
        "reference": "TEST REF",
        "amount": "99.99",
        "additionalinfo": "A test ticket transaction",
        "returnurl": "http://www.google.com/search?q=returnurl",
        "resulturl": "http://www.google.com/search?q=resulturl",
        "status": "Message"
    }

    expected_hash = "2A033FC38798D913D42ECB786B9B19645ADEDBDE788862032F1BD82CF3B92DEF84F316385D5B40DBB35F1A4FD7D5BFE73835174136463CDD48C9366B0749C689"

    generated_hash = client.generate_hash(values)

    assert generated_hash == expected_hash, f"Expected {expected_hash}, got {generated_hash}"


def test_hash_validation():
    """Test hash validation"""
    client = PaynowClient(
        integration_id="1201",
        integration_key="3e9fed89-60e1-4ce5-ab6e-6b1eb2d4f977",
        result_url="http://example.com/result"
    )

    # Valid payload with correct hash
    payload = {
        "status": "Ok",
        "browserurl": "https://staging.paynow.co.zw/Payment/ConfirmPayment/9510",
        "pollurl": "https://staging.paynow.co.zw/Interface/CheckPayment/?guid=c7ed41da-0159-46da-b428-69549f770413",
        "paynowreference": "9510",
        "hash": "750DD0B0DF374678707BB5AF915AF81C228B9058AD57BB7120569EC68BBB9C2EFC1B26C6375D2BC562AC909B3CD6B2AF1D42E1A5E479FFAC8F4FB3FDCE71DF4D"
    }

    assert client.validate_hash(payload) == True

    # Invalid hash
    payload["hash"] = "INVALID_HASH"
    assert client.validate_hash(payload) == False


if __name__ == "__main__":
    print("Testing hash generation...")
    test_hash_generation()
    print("✅ Hash generation test passed")

    print("Testing hash validation...")
    test_hash_validation()
    print("✅ Hash validation test passed")
```

Run tests:

```bash
# 1. Rebuild billing-service
docker compose -f infrastructure/compose/docker-compose.ceph.yml up -d --build billing-service

# 2. Enter container
docker exec -it saasodoo-billing-service bash

# 3. Run hash tests
python tests/test_paynow_client.py

# Expected output:
# Testing hash generation...
# ✅ Hash generation test passed
# Testing hash validation...
# ✅ Hash validation test passed

# 4. Exit container
exit
```

**Success Criteria:**
- ✅ Hash generation matches Paynow example
- ✅ Hash validation works correctly
- ✅ No import errors

**If Test Fails:**
- Verify file created: `ls -la services/billing-service/app/utils/paynow_client.py`
- Check syntax: `docker exec saasodoo-billing-service python -m py_compile app/utils/paynow_client.py`
- Check imports: `docker exec saasodoo-billing-service python -c "import hashlib, httpx"`

---

### STEP 4: Payment Initiation Routes

#### File to Modify: `services/billing-service/app/routes/payments.py`

Add these imports at the top (after existing imports):

```python
from typing import Literal, Optional
from datetime import datetime
import uuid

from ..utils.paynow_client import get_paynow_client
from ..utils.database import get_pool
```

Add Pydantic models (after existing models):

```python
class PaynowInitiateRequest(BaseModel):
    invoice_id: str
    payment_method: Literal["ecocash", "onemoney", "card"]
    phone: Optional[str] = None  # Required for ecocash/onemoney
    return_url: Optional[str] = None  # Required for card
    customer_email: str  # Required for all


class PaynowPaymentResponse(BaseModel):
    payment_id: str
    reference: str
    payment_type: Literal["mobile", "redirect"]
    status: str
    poll_url: str
    redirect_url: Optional[str] = None
    message: str
```

Add helper function (before endpoints):

```python
def map_paynow_status(paynow_status: str) -> str:
    """Map Paynow status to our payment_status"""
    status_map = {
        "Paid": "paid",
        "Awaiting Delivery": "paid",
        "Delivered": "paid",
        "Created": "pending",
        "Sent": "pending",
        "Cancelled": "cancelled",
        "Failed": "failed",
        "Disputed": "disputed",
        "Refunded": "refunded"
    }
    return status_map.get(paynow_status, "pending")
```

Add endpoints (at the end of the file):

```python
@router.post("/paynow/initiate", response_model=PaynowPaymentResponse)
async def initiate_paynow_payment(
    request: PaynowInitiateRequest,
    killbill: KillBillClient = Depends(get_killbill_client)
):
    """
    Initiate Paynow payment (mobile money or card)

    Mobile Money Flow (EcoCash/OneMoney):
    - Sends USSD push to customer's phone
    - Customer approves on phone
    - Frontend polls status endpoint

    Card Flow:
    - Returns redirect URL
    - Customer redirects to Paynow
    - Customer pays on Paynow page
    - Paynow redirects back to return_url
    """
    try:
        # Validate request
        if request.payment_method in ["ecocash", "onemoney"] and not request.phone:
            raise HTTPException(status_code=400, detail="Phone number required for mobile money payments")

        if request.payment_method == "card" and not request.return_url:
            raise HTTPException(status_code=400, detail="Return URL required for card payments")

        # Get invoice from KillBill
        invoice = await killbill.get_invoice_by_id(request.invoice_id)
        if not invoice:
            raise HTTPException(status_code=404, detail="Invoice not found")

        amount = float(invoice.get('balance', 0))
        if amount <= 0:
            raise HTTPException(status_code=400, detail="Invoice already paid or has zero balance")

        # Generate unique reference
        payment_id = str(uuid.uuid4())
        reference = f"INV_{request.invoice_id}_{payment_id[:8]}"

        # Initialize Paynow client
        paynow = get_paynow_client()

        # Initiate payment based on method
        if request.payment_method in ["ecocash", "onemoney"]:
            # Mobile money - USSD push
            paynow_response = await paynow.initiate_mobile_transaction(
                reference=reference,
                amount=amount,
                phone=request.phone,
                method=request.payment_method,
                auth_email=request.customer_email,
                additional_info=f"Invoice {request.invoice_id}"
            )
            payment_type = "mobile"

        else:
            # Card - redirect flow
            paynow_response = await paynow.initiate_transaction(
                reference=reference,
                amount=amount,
                return_url=request.return_url,
                auth_email=request.customer_email,
                additional_info=f"Invoice {request.invoice_id}"
            )
            payment_type = "redirect"

        # Check Paynow response
        if paynow_response.get('status') == 'Error':
            error_msg = paynow_response.get('error', 'Unknown error')
            logger.error(f"Paynow initiation failed: {error_msg}")
            raise HTTPException(status_code=500, detail=f"Payment initiation failed: {error_msg}")

        # Store payment in database
        pool = get_pool()
        async with pool.acquire() as conn:
            await conn.execute("""
                INSERT INTO payments (
                    id, subscription_id, amount, currency, payment_method, payment_status,
                    gateway_transaction_id, paynow_poll_url, paynow_browser_url,
                    return_url, phone, paynow_status, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
            """,
                payment_id,
                None,  # subscription_id - link if available
                amount,
                'USD',
                request.payment_method,
                'pending',
                reference,  # Our reference
                paynow_response.get('pollurl'),
                paynow_response.get('browserurl'),
                request.return_url,
                request.phone,
                paynow_response.get('status'),
                datetime.utcnow()
            )

        logger.info(f"Payment initiated: {payment_id} ({request.payment_method})")

        # Build response
        response_data = {
            "payment_id": payment_id,
            "reference": reference,
            "payment_type": payment_type,
            "status": "pending",
            "poll_url": f"/api/billing/payments/paynow/status/{payment_id}"
        }

        if payment_type == "redirect":
            response_data["redirect_url"] = paynow_response.get('browserurl')
            response_data["message"] = "Redirect customer to payment page"
        else:
            response_data["message"] = f"Payment request sent to {request.phone}. Please check your phone."

        return response_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error initiating Paynow payment: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/paynow/status/{payment_id}")
async def get_paynow_payment_status(payment_id: str):
    """
    Get current payment status - Frontend polls this endpoint

    Returns current status from database.
    If status is still pending after 30 seconds, polls Paynow for update.
    """
    try:
        pool = get_pool()

        # Get payment from database
        async with pool.acquire() as conn:
            payment = await conn.fetchrow("""
                SELECT id, gateway_transaction_id, amount, payment_method, payment_status,
                       paynow_reference, paynow_poll_url, paynow_status, phone,
                       created_at, webhook_received_at
                FROM payments
                WHERE id = $1
            """, payment_id)

        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")

        # Check if we should poll Paynow for update
        should_poll = (
            payment['payment_status'] == 'pending' and
            payment['paynow_poll_url'] and
            (datetime.utcnow() - payment['created_at']).total_seconds() > 30
        )

        if should_poll:
            # Poll Paynow for latest status
            paynow = get_paynow_client()
            paynow_status = await paynow.poll_transaction_status(payment['paynow_poll_url'])

            if paynow_status.get('status') not in ['Error']:
                # Update database with latest status
                new_status = paynow_status.get('status', 'pending')
                mapped_status = map_paynow_status(new_status)

                async with pool.acquire() as conn:
                    await conn.execute("""
                        UPDATE payments
                        SET payment_status = $1, paynow_status = $2, paynow_reference = $3
                        WHERE id = $4
                    """,
                        mapped_status,
                        new_status,
                        paynow_status.get('paynowreference'),
                        payment_id
                    )

                # Reload payment
                async with pool.acquire() as conn:
                    payment = await conn.fetchrow("""
                        SELECT id, gateway_transaction_id, amount, payment_method, payment_status,
                               paynow_reference, paynow_status, phone,
                               created_at, webhook_received_at
                        FROM payments
                        WHERE id = $1
                    """, payment_id)

        # Return current status
        return {
            "payment_id": str(payment['id']),
            "reference": payment['gateway_transaction_id'],
            "status": payment['payment_status'],
            "paynow_status": payment['paynow_status'],
            "amount": float(payment['amount']),
            "payment_method": payment['payment_method'],
            "phone": payment['phone'],
            "created_at": payment['created_at'].isoformat() if payment['created_at'] else None,
            "webhook_received": payment['webhook_received_at'] is not None
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting payment status: {e}")
        raise HTTPException(status_code=500, detail=str(e))
```

#### Test Step 4:

```bash
# 1. Rebuild billing-service
docker compose -f infrastructure/compose/docker-compose.ceph.yml up -d --build billing-service

# 2. Check service started
docker logs saasodoo-billing-service --tail 20

# 3. Start all other services (especially KillBill for invoice lookup)
docker compose -f infrastructure/compose/docker-compose.ceph.yml up -d

# 4. Wait for KillBill to be ready
docker logs -f saasodoo-killbill
# Wait for: "Listening for HTTP on /0.0.0.0:8080"

# 5. Create a test invoice in KillBill first (or use existing one)
# For now, we'll test the endpoint error handling

# 6. Test with invalid invoice (should get 404)
curl -X POST http://localhost:8004/api/billing/payments/paynow/initiate \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "non_existent_invoice",
    "payment_method": "ecocash",
    "phone": "0771111111",
    "customer_email": "test@example.com"
  }'

# Expected: {"detail": "Invoice not found"} (404 error)

# 7. Test validation (missing phone)
curl -X POST http://localhost:8004/api/billing/payments/paynow/initiate \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "test_invoice",
    "payment_method": "ecocash",
    "customer_email": "test@example.com"
  }'

# Expected: {"detail": "Phone number required for mobile money payments"}

# 8. Check logs for any errors
docker logs saasodoo-billing-service | grep -i error
```

**Success Criteria:**
- ✅ Billing-service starts without errors
- ✅ Endpoints respond (even with validation errors)
- ✅ Validation works correctly
- ✅ No Python syntax errors

**If Test Fails:**
- Check Python syntax: `docker exec saasodoo-billing-service python -m py_compile app/routes/payments.py`
- Check logs: `docker logs saasodoo-billing-service --tail 100`
- Verify imports exist: `docker exec saasodoo-billing-service python -c "from app.utils.paynow_client import get_paynow_client"`

---

### STEP 5: Webhook Handler

#### File to Modify: `services/billing-service/app/routes/webhooks.py`

Add to imports (at the top):

```python
from ..utils.paynow_client import get_paynow_client
from ..utils.database import get_pool
from urllib.parse import parse_qs
from datetime import datetime
```

Add webhook endpoint (after the existing killbill webhook):

```python
@router.post("/paynow")
async def handle_paynow_webhook(request: Request, response: Response):
    """
    Handle webhook from Paynow

    Paynow sends status updates as URL-encoded POST:
    reference=X&paynowreference=Y&amount=Z&status=Paid&hash=...

    We validate hash, update payment record, and update KillBill if paid
    """
    response.headers["Connection"] = "close"

    try:
        # Get raw body
        body = await request.body()
        body_str = body.decode('utf-8')

        logger.info(f"Received Paynow webhook: {body_str}")

        # Parse URL-encoded payload
        payload_lists = parse_qs(body_str)

        # Convert lists to single values
        payload = {k: v[0] if isinstance(v, list) and len(v) > 0 else v
                  for k, v in payload_lists.items()}

        logger.info(f"Parsed Paynow payload: {payload}")

        # Validate hash
        paynow = get_paynow_client()
        if not paynow.validate_hash(payload):
            logger.error("Invalid hash in Paynow webhook")
            raise HTTPException(status_code=400, detail="Invalid hash")

        # Extract fields
        reference = payload.get('reference')  # Our reference
        paynow_reference = payload.get('paynowreference')
        amount = payload.get('amount')
        paynow_status = payload.get('status')
        poll_url = payload.get('pollurl')

        if not reference:
            logger.error("No reference in Paynow webhook")
            raise HTTPException(status_code=400, detail="Missing reference")

        logger.info(f"Paynow webhook: {reference} → {paynow_status}")

        # Find payment by our reference (gateway_transaction_id)
        pool = get_pool()
        async with pool.acquire() as conn:
            payment = await conn.fetchrow("""
                SELECT id, payment_status, amount as payment_amount, subscription_id
                FROM payments
                WHERE gateway_transaction_id = $1
            """, reference)

        if not payment:
            logger.warning(f"Payment not found for reference: {reference}")
            # Return 200 to prevent retries
            return {"success": True, "message": "Payment not found"}

        payment_id = payment['id']

        # Map Paynow status to our status
        from .payments import map_paynow_status
        new_status = map_paynow_status(paynow_status)

        # Update payment in database
        async with pool.acquire() as conn:
            await conn.execute("""
                UPDATE payments
                SET payment_status = $1, paynow_status = $2, paynow_reference = $3,
                    webhook_received_at = $4, processed_at = $5
                WHERE id = $6
            """,
                new_status,
                paynow_status,
                paynow_reference,
                datetime.utcnow(),
                datetime.utcnow() if new_status == 'paid' else None,
                payment_id
            )

        logger.info(f"Updated payment {payment_id}: {new_status}")

        # If payment successful, update KillBill
        if new_status == 'paid':
            logger.info(f"Payment successful, updating KillBill for payment {payment_id}")

            # Extract invoice_id from reference (format: INV_invoice_id_xxxxx)
            parts = reference.split('_')
            invoice_id = parts[1] if len(parts) > 1 else None

            if invoice_id:
                try:
                    # Get KillBill client
                    killbill = _get_killbill_client()

                    # Record payment in KillBill
                    invoice = await killbill.get_invoice_by_id(invoice_id)
                    if invoice:
                        account_id = invoice.get('accountId')

                        # Create payment in KillBill
                        payment_data = {
                            "accountId": account_id,
                            "targetInvoiceId": invoice_id,
                            "purchasedAmount": float(amount)
                        }

                        kb_payment = await killbill.create_payment(payment_data)
                        logger.info(f"Created KillBill payment for invoice {invoice_id}")

                        # Instance provisioning will be triggered by KillBill's
                        # INVOICE_PAYMENT_SUCCESS webhook

                    else:
                        logger.warning(f"Invoice {invoice_id} not found in KillBill")

                except Exception as kb_error:
                    logger.error(f"Failed to update KillBill: {kb_error}")
                    # Don't fail the webhook - payment is recorded locally
            else:
                logger.warning(f"Could not extract invoice_id from reference: {reference}")

        return {"success": True, "message": "Webhook processed"}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing Paynow webhook: {e}")
        # Return 200 to prevent Paynow retries
        return {"success": False, "message": str(e)}
```

#### Test Step 5:

```bash
# 1. Rebuild billing-service
docker compose -f infrastructure/compose/docker-compose.ceph.yml up -d --build billing-service

# 2. Test webhook endpoint exists
curl -X POST http://localhost:8004/api/billing/webhooks/paynow \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "test=data"

# Expected: 400 error (no hash) or similar - confirms endpoint exists

# 3. Monitor logs for webhook processing
docker logs -f saasodoo-billing-service | grep -i paynow

# 4. Check endpoint is registered
docker exec saasodoo-billing-service python -c "
from app.main import app
for route in app.routes:
    if hasattr(route, 'path') and 'paynow' in route.path:
        print(f'{route.methods} {route.path}')
"

# Expected output should include:
# {'POST'} /api/billing/webhooks/paynow
# {'POST'} /api/billing/payments/paynow/initiate
# {'GET'} /api/billing/payments/paynow/status/{payment_id}
```

**Success Criteria:**
- ✅ Webhook endpoint accessible
- ✅ Endpoint responds (even with errors)
- ✅ Routes registered correctly
- ✅ No Python syntax errors

---

### STEP 6: KillBill Payment Recording

#### File to Modify: `services/billing-service/app/utils/killbill_client.py`

Add this method to the `KillBillClient` class:

```python
async def create_payment(self, payment_data: dict) -> dict:
    """
    Record payment in KillBill

    Args:
        payment_data: {
            "accountId": "account-uuid",
            "targetInvoiceId": "invoice-uuid",
            "purchasedAmount": 100.00
        }

    Returns:
        Payment object from KillBill
    """
    url = f"{self.base_url}/1.0/kb/accounts/{payment_data['accountId']}/payments"

    headers = self._get_headers()
    headers["Content-Type"] = "application/json"

    try:
        response = await self.client.post(
            url,
            json=payment_data,
            headers=headers,
            auth=(self.username, self.password)
        )

        if response.status_code in [200, 201]:
            logger.info(f"Payment recorded in KillBill for invoice {payment_data.get('targetInvoiceId')}")
            return response.json()
        else:
            logger.error(f"Failed to record payment in KillBill: {response.status_code} - {response.text}")
            return None

    except Exception as e:
        logger.error(f"Error recording payment in KillBill: {e}")
        raise
```

#### Test Step 6:

```bash
# 1. Rebuild billing-service
docker compose -f infrastructure/compose/docker-compose.ceph.yml up -d --build billing-service

# 2. Verify method exists
docker exec saasodoo-billing-service python -c "
from app.utils.killbill_client import KillBillClient
import inspect
print('create_payment method exists:', hasattr(KillBillClient, 'create_payment'))
sig = inspect.signature(KillBillClient.create_payment)
print('Method signature:', sig)
"

# Expected:
# create_payment method exists: True
# Method signature: (self, payment_data: dict) -> dict
```

**Success Criteria:**
- ✅ Method exists in KillBillClient
- ✅ No syntax errors
- ✅ Service starts successfully

---

### STEP 7: End-to-End Testing

Now we test the complete flow with Paynow test mode.

#### Prerequisites:
1. Paynow integration must be in test mode
2. You need your Paynow merchant account email
3. Create a test invoice in KillBill

#### Create Test Invoice:

```bash
# 1. Create KillBill account first
ACCOUNT_RESPONSE=$(docker exec saasodoo-killbill curl -s -X POST \
  -u admin:password \
  -H "X-Killbill-ApiKey: fresh-tenant" \
  -H "X-Killbill-ApiSecret: fresh-secret" \
  -H "Content-Type: application/json" \
  -H "X-Killbill-CreatedBy: test" \
  -d '{
    "name": "Test Customer",
    "email": "test@example.com",
    "currency": "USD",
    "externalKey": "test-customer-001"
  }' \
  "http://localhost:8080/1.0/kb/accounts")

echo "Account created: $ACCOUNT_RESPONSE"

ACCOUNT_ID=$(echo $ACCOUNT_RESPONSE | jq -r '.accountId')
echo "Account ID: $ACCOUNT_ID"

# 2. Create external charge (invoice item)
CHARGE_RESPONSE=$(docker exec saasodoo-killbill curl -s -X POST \
  -u admin:password \
  -H "X-Killbill-ApiKey: fresh-tenant" \
  -H "X-Killbill-ApiSecret: fresh-secret" \
  -H "Content-Type: application/json" \
  -H "X-Killbill-CreatedBy: test" \
  -d '[{
    "accountId": "'$ACCOUNT_ID'",
    "amount": 10.00,
    "currency": "USD",
    "description": "Test payment for Paynow"
  }]' \
  "http://localhost:8080/1.0/kb/invoiceItems/charges")

echo "Charge created: $CHARGE_RESPONSE"

# 3. Get invoice ID
INVOICE_ID=$(docker exec saasodoo-killbill curl -s -u admin:password \
  -H "X-Killbill-ApiKey: fresh-tenant" \
  -H "X-Killbill-ApiSecret: fresh-secret" \
  "http://localhost:8080/1.0/kb/accounts/$ACCOUNT_ID/invoices" | \
  jq -r '.[0].invoiceId')

echo "Invoice ID: $INVOICE_ID"
echo "Invoice URL: http://localhost:8081/1.0/kb/invoices/$INVOICE_ID"
```

#### Test 7A: Mobile Money Payment (Success)

```bash
#!/bin/bash
# Save as: test_mobile_payment.sh

echo "=== PAYNOW MOBILE MONEY TEST ==="
echo ""

# Use the invoice ID from above
INVOICE_ID="your-invoice-id-here"  # Replace with actual
PAYNOW_TEST_EMAIL="your-paynow-merchant-email@example.com"  # Replace with your Paynow email

echo "Step 1: Initiating EcoCash payment..."
PAYMENT_RESPONSE=$(curl -s -X POST http://localhost:8004/api/billing/payments/paynow/initiate \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "'$INVOICE_ID'",
    "payment_method": "ecocash",
    "phone": "0771111111",
    "customer_email": "'$PAYNOW_TEST_EMAIL'"
  }')

echo "Response: $PAYMENT_RESPONSE"
echo ""

# Check for errors
if echo "$PAYMENT_RESPONSE" | grep -q "detail"; then
  echo "❌ Error occurred:"
  echo "$PAYMENT_RESPONSE" | jq '.'
  exit 1
fi

# Extract payment_id
PAYMENT_ID=$(echo $PAYMENT_RESPONSE | jq -r '.payment_id')
echo "✅ Payment ID: $PAYMENT_ID"
echo "✅ Poll URL: $(echo $PAYMENT_RESPONSE | jq -r '.poll_url')"
echo ""

echo "Step 2: Checking payment in database..."
docker exec saasodoo-postgres psql -U billing_service -d billing \
  -c "SELECT id, payment_method, payment_status, paynow_status, phone FROM payments WHERE id = '$PAYMENT_ID';"
echo ""

echo "Step 3: Waiting for Paynow webhook (test mode: 5 seconds)..."
for i in {5..1}; do
  echo "  $i seconds remaining..."
  sleep 1
done
echo ""

echo "Step 4: Checking payment status via API..."
curl -s http://localhost:8004/api/billing/payments/paynow/status/$PAYMENT_ID | jq '.'
echo ""

echo "Step 5: Checking database after webhook..."
docker exec saasodoo-postgres psql -U billing_service -d billing \
  -c "SELECT id, payment_status, paynow_status, paynow_reference, webhook_received_at FROM payments WHERE id = '$PAYMENT_ID';"
echo ""

echo "Step 6: Checking KillBill invoice status..."
docker exec saasodoo-killbill curl -s -u admin:password \
  -H "X-Killbill-ApiKey: fresh-tenant" \
  -H "X-Killbill-ApiSecret: fresh-secret" \
  "http://localhost:8080/1.0/kb/invoices/$INVOICE_ID" | jq '{invoiceId, balance, status}'

echo ""
echo "=== TEST COMPLETE ==="
```

Make it executable and run:

```bash
chmod +x test_mobile_payment.sh
./test_mobile_payment.sh
```

#### Expected Results:

**After Step 1 (Initiate):**
- ✅ Payment created with status "pending"
- ✅ Phone number stored: 0771111111
- ✅ poll_url returned

**After Step 4 (After 5 seconds):**
- ✅ payment_status changed to "paid"
- ✅ paynow_status: "Paid"
- ✅ webhook_received_at: timestamp present
- ✅ paynow_reference: populated

**After Step 6 (KillBill):**
- ✅ Invoice balance: 0.00
- ✅ Invoice status might show as paid

#### Test 7B: Monitor Logs

While running the test, watch logs in another terminal:

```bash
# Terminal 2: Watch billing-service logs
docker logs -f saasodoo-billing-service

# Look for:
# - "Initiating Paynow mobile transaction"
# - "Received Paynow webhook"
# - "Payment successful, updating KillBill"
# - "Updated payment {id}: paid"
```

#### Test 7C: Test Failed Payment

```bash
# Use test number for insufficient balance
curl -X POST http://localhost:8004/api/billing/payments/paynow/initiate \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "'$INVOICE_ID'",
    "payment_method": "ecocash",
    "phone": "0774444444",
    "customer_email": "'$PAYNOW_TEST_EMAIL'"
  }' | jq '.'

# Expected: Should fail immediately with "Insufficient balance" error
```

#### Test 7D: Test Cancelled Payment

```bash
# Use test number for user cancellation
curl -X POST http://localhost:8004/api/billing/payments/paynow/initiate \
  -H "Content-Type: application/json" \
  -d '{
    "invoice_id": "'$INVOICE_ID'",
    "payment_method": "ecocash",
    "phone": "0773333333",
    "customer_email": "'$PAYNOW_TEST_EMAIL'"
  }' | jq '.'

# Payment will be created, but after 30 seconds webhook will mark as failed
# Check status after 35 seconds:
# curl http://localhost:8004/api/billing/payments/paynow/status/{payment_id} | jq '.'
```

**Success Criteria for End-to-End:**
- ✅ Payment initiated without errors
- ✅ Payment record created in database
- ✅ Paynow webhook received after 5 seconds
- ✅ Payment status updated to "paid"
- ✅ KillBill invoice marked as paid
- ✅ All logs show successful processing

**If Test Fails:**

1. **Payment initiation fails:**
   - Check Paynow credentials in `.env`
   - Verify `authemail` matches your Paynow account
   - Check billing-service logs for Paynow API errors

2. **Webhook not received:**
   - Paynow test mode should send webhook to `PAYNOW_RESULT_URL`
   - For local testing, webhook might not work (Paynow can't reach localhost)
   - Solution: Manually poll status endpoint, or use ngrok for public URL

3. **KillBill not updated:**
   - Check KillBill credentials
   - Verify invoice exists
   - Check logs for KillBill API errors

---

## Testing Protocol

### Test Phone Numbers (Paynow Test Mode)

**Mobile Money:**
- `0771111111` - ✅ Success (webhook after 5 seconds)
- `0772222222` - ⏳ Delayed Success (webhook after 30 seconds)
- `0773333333` - ❌ User Cancelled (failed after 30 seconds)
- `0774444444` - ❌ Insufficient Balance (immediate failure)

**Important:**
- Integration must be in test mode
- `authemail` field must match your Paynow merchant account email
- Only works with exact test numbers above

### Monitoring Commands

```bash
# Watch all billing-service logs
docker logs -f saasodoo-billing-service

# Watch only Paynow-related logs
docker logs -f saasodoo-billing-service | grep -i paynow

# Check recent payments
docker exec saasodoo-postgres psql -U billing_service -d billing \
  -c "SELECT id, payment_method, payment_status, paynow_status, phone, created_at FROM payments ORDER BY created_at DESC LIMIT 5;"

# Check specific payment details
docker exec saasodoo-postgres psql -U billing_service -d billing \
  -c "SELECT * FROM payments WHERE id = 'payment-id-here' \gx"

# Check KillBill invoice status
docker exec saasodoo-killbill curl -s -u admin:password \
  -H "X-Killbill-ApiKey: fresh-tenant" \
  -H "X-Killbill-ApiSecret: fresh-secret" \
  "http://localhost:8080/1.0/kb/invoices/invoice-id-here" | jq '.'
```

---

## Troubleshooting

### Issue: Hash Validation Fails

**Symptoms:** "Invalid hash" errors in logs

**Solutions:**
1. Verify `PAYNOW_INTEGRATION_KEY` matches Paynow dashboard exactly
2. Check no extra spaces/newlines in `.env`
3. Test hash generation with known example:

```bash
docker exec saasodoo-billing-service python tests/test_paynow_client.py
```

### Issue: Webhook Not Received (Local Development)

**Symptoms:** Payment stays "pending" forever

**Root Cause:** Paynow cannot reach `http://billing-service:8004` from internet

**Solutions:**

**Option 1: Use ngrok (Recommended for testing)**
```bash
# 1. Install ngrok: https://ngrok.com/download

# 2. Expose billing-service port
ngrok http 8004

# 3. Copy the https URL (e.g., https://abc123.ngrok.io)

# 4. Update .env:
PAYNOW_RESULT_URL=https://abc123.ngrok.io/api/billing/webhooks/paynow

# 5. Restart billing-service
docker compose -f infrastructure/compose/docker-compose.ceph.yml restart billing-service
```

**Option 2: Manual Polling (Fallback)**
```bash
# Status endpoint will poll Paynow if webhook not received
# Just keep calling status endpoint:
while true; do
  curl http://localhost:8004/api/billing/payments/paynow/status/$PAYMENT_ID | jq '.status'
  sleep 3
done
```

### Issue: Payment Initiation Returns Error

**Symptoms:** 500 error when calling `/paynow/initiate`

**Debug Steps:**

```bash
# 1. Check billing-service logs
docker logs saasodoo-billing-service --tail 100 | grep ERROR

# 2. Verify Paynow credentials
docker exec saasodoo-billing-service env | grep PAYNOW

# 3. Test Paynow connectivity
docker exec saasodoo-billing-service python -c "
import httpx
import os
response = httpx.get(os.getenv('PAYNOW_BASE_URL', 'https://www.paynow.co.zw'))
print(f'Paynow reachable: {response.status_code}')
"

# 4. Check database connection
docker exec saasodoo-postgres psql -U billing_service -d billing -c "SELECT 1;"
```

### Issue: Database Columns Missing

**Symptoms:** SQL error about missing column (paynow_reference, etc.)

**Solution:**

```bash
# 1. Check current payments table schema
docker exec saasodoo-postgres psql -U billing_service -d billing -c "\d payments"

# 2. If columns missing, recreate database:
docker compose -f infrastructure/compose/docker-compose.ceph.yml down
docker volume rm saasodoo_postgres-data
docker compose -f infrastructure/compose/docker-compose.ceph.yml up -d postgres

# 3. Wait for initialization and verify
docker logs -f saasodoo-postgres
# Wait for ready message, then:
docker exec saasodoo-postgres psql -U billing_service -d billing -c "\d payments"
```

### Issue: KillBill Payment Not Created

**Symptoms:** Payment marked as paid locally but KillBill invoice still unpaid

**Debug:**

```bash
# 1. Check if invoice exists
docker exec saasodoo-killbill curl -s -u admin:password \
  -H "X-Killbill-ApiKey: fresh-tenant" \
  -H "X-Killbill-ApiSecret: fresh-secret" \
  "http://localhost:8080/1.0/kb/invoices/$INVOICE_ID"

# 2. Check KillBill logs
docker logs saasodoo-killbill | grep -i error

# 3. Check billing-service logs for KillBill errors
docker logs saasodoo-billing-service | grep -i killbill

# 4. Verify KillBill credentials
docker exec saasodoo-billing-service python -c "
import os
print('KILLBILL_URL:', os.getenv('KILLBILL_URL'))
print('KILLBILL_API_KEY:', os.getenv('KILLBILL_API_KEY'))
"
```

### Issue: Test Mode Not Working

**Symptoms:** Error: "Merchant is in testing"

**Solution:**
- Ensure `authemail` in payment request matches your Paynow merchant account email
- Verify integration is in test mode in Paynow dashboard
- Check you're using exact test phone numbers (0771111111, etc.)

---

## Production Deployment Checklist

Before going live with real payments:

### Paynow Configuration
- [ ] Request integration to be set **live** in Paynow dashboard
- [ ] Verify live mode activated
- [ ] Update production credentials in `.env`
- [ ] Configure public `PAYNOW_RESULT_URL` (must be HTTPS and publicly accessible)
- [ ] Test webhook delivery to production URL

### Infrastructure
- [ ] Set up HTTPS/SSL certificates
- [ ] Configure firewall to allow Paynow webhook IPs
- [ ] Set up monitoring/alerting for failed payments
- [ ] Configure backup/redundancy for payment records
- [ ] Set up log aggregation for payment audit trail

### Testing
- [ ] Test with real small amount (e.g., $0.10)
- [ ] Verify webhook received in production
- [ ] Confirm KillBill integration works
- [ ] Test all payment methods (EcoCash, OneMoney, Card)
- [ ] Test failed payment handling
- [ ] Test timeout scenarios

### Operations
- [ ] Document customer support procedures
- [ ] Set up payment reconciliation process
- [ ] Configure proper logging/audit trail
- [ ] Implement payment retry logic (if needed)
- [ ] Set up refund process (if applicable)
- [ ] Train support team on payment troubleshooting

### Security
- [ ] Store credentials securely (secrets manager)
- [ ] Enable rate limiting on payment endpoints
- [ ] Implement fraud detection (if needed)
- [ ] Set up payment amount limits
- [ ] Regular security audits

---

## Summary

### What We Built

1. ✅ **Database Schema** - Extended payments table with Paynow fields
2. ✅ **Paynow Client** - Hash generation, API communication, webhook validation
3. ✅ **Payment Initiation** - Mobile money (USSD) and card (redirect) flows
4. ✅ **Webhook Handler** - Process Paynow status updates, update KillBill
5. ✅ **Status Polling** - Frontend can check payment status
6. ✅ **KillBill Integration** - Record payments against invoices

### Files Created/Modified

**Created:**
- `services/billing-service/app/utils/paynow_client.py`
- `services/billing-service/tests/test_paynow_client.py`

**Modified:**
- `shared/configs/postgres/04-init-schemas.sql.template`
- `infrastructure/compose/docker-compose.ceph.yml`
- `.env`
- `services/billing-service/app/routes/payments.py`
- `services/billing-service/app/routes/webhooks.py`
- `services/billing-service/app/utils/killbill_client.py`

### Payment Flow Recap

**Mobile Money (EcoCash/OneMoney):**
```
1. Frontend → POST /paynow/initiate {phone, method: "ecocash"}
2. Backend → Paynow API (USSD push to phone)
3. Customer → Approves on phone
4. Paynow → Webhook to backend
5. Backend → Updates payment + KillBill
6. Frontend polls /status → Gets "paid"
```

**Card Payment:**
```
1. Frontend → POST /paynow/initiate {return_url, method: "card"}
2. Backend → Returns redirect_url
3. Frontend → Redirects customer to Paynow
4. Customer → Pays on Paynow page
5. Paynow → Redirects to return_url + sends webhook
6. Backend → Updates payment + KillBill
7. Frontend → Shows success (from polling /status)
```

### Next Steps

1. ✅ Complete all test steps in order
2. ✅ Fix any issues found during testing
3. ✅ Test with real Paynow test account
4. ✅ Implement frontend payment UI (Phase 2)
5. ✅ Prepare for production deployment
6. ✅ Set up monitoring and alerting

### Support

For issues:
1. Check logs: `docker logs saasodoo-billing-service`
2. Check database: `docker exec saasodoo-postgres psql ...`
3. Review this document's troubleshooting section
4. Contact Paynow support: support@paynow.co.zw

---

**End of Implementation Plan**
