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
