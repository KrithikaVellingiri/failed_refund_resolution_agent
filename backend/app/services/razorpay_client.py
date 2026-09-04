import requests
from requests.auth import HTTPBasicAuth
from app.config import settings
import logging

logger = logging.getLogger(__name__)

class RazorpayError(Exception):
    pass

def refund_payment(payment_id: str, amount: int) -> dict:
    """
    Initiates a refund for a captured payment via Razorpay API.
    :param payment_id: The id of the payment to refund
    :param amount: Amount in paise
    """
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise ValueError("Razorpay credentials are not configured.")
        
    url = f"https://api.razorpay.com/v1/payments/{payment_id}/refund"
    payload = {
        "amount": amount
    }
    
    auth = HTTPBasicAuth(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    
    try:
        response = requests.post(url, json=payload, auth=auth, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        logger.error(f"Razorpay refund failed: {e.response.text}")
        raise RazorpayError(f"Razorpay API error: {e.response.text}") from e
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to communicate with Razorpay: {e}")
        raise RazorpayError(f"Network error: {str(e)}") from e

def get_refund(refund_id: str) -> dict:
    """
    Fetches the live status of a refund from Razorpay API.
    :param refund_id: The id of the refund to fetch
    """
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise ValueError("Razorpay credentials are not configured.")
        
    url = f"https://api.razorpay.com/v1/refunds/{refund_id}"
    auth = HTTPBasicAuth(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    
    try:
        response = requests.get(url, auth=auth, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        logger.error(f"Razorpay get refund failed: {e.response.text}")
        raise RazorpayError(f"Razorpay API error: {e.response.text}") from e
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to communicate with Razorpay: {e}")
        raise RazorpayError(f"Network error: {str(e)}") from e

import hashlib

# Policy cap (from Task 10)
AUTO_APPROVAL_LIMIT_PAISE = 1000000

class PayoutCapExceededError(ValueError):
    pass

class InvalidInputError(ValueError):
    pass

def _generate_idempotency_key(case_id: str) -> str:
    """
    Generates a deterministic 35-character idempotency key for Razorpay payouts.
    Only allows alphanumeric and hyphen.
    Uses SHA-256 to avoid truncation collisions.
    """
    if not case_id or not str(case_id).strip():
        raise InvalidInputError("Invalid case_id.")
        
    digest = hashlib.sha256(
        str(case_id).encode("utf-8")
    ).hexdigest()[:32]
    
    return f"po-{digest}"

def create_payout(case_id: str, amount: int, fund_account_id: str, mode: str) -> dict:
    """
    Initiates a RazorpayX payout (Task 11B).
    Must NOT be called without successfully passing the duplicate guard (Task 11A).
    """
    if amount <= 0:
        raise InvalidInputError("Amount must be positive.")
        
    # Enforce monetary cap BEFORE HTTP request
    if amount > AUTO_APPROVAL_LIMIT_PAISE:
        logger.error(f"Payout blocked: amount {amount} exceeds cap of {AUTO_APPROVAL_LIMIT_PAISE}.")
        raise PayoutCapExceededError(f"Amount {amount} exceeds cap of {AUTO_APPROVAL_LIMIT_PAISE}.")
        
    idempotency_key = _generate_idempotency_key(case_id)
    
    if not settings.RAZORPAY_KEY_ID or not settings.RAZORPAY_KEY_SECRET:
        raise ValueError("Razorpay credentials are not configured.")
        
    if not settings.RAZORPAYX_ACCOUNT_NUMBER:
        raise ValueError("RazorpayX account number is not configured.")
        
    url = "https://api.razorpay.com/v1/payouts"
    
    payload = {
        "account_number": settings.RAZORPAYX_ACCOUNT_NUMBER,
        "fund_account_id": fund_account_id,
        "amount": amount,
        "currency": "INR",
        "mode": mode.upper(),
        "purpose": "refund",
    }
    
    headers = {
        "X-Payout-Idempotency": idempotency_key
    }
    
    auth = HTTPBasicAuth(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET)
    
    try:
        response = requests.post(url, json=payload, headers=headers, auth=auth, timeout=10)
        response.raise_for_status()
        return response.json()
    except requests.exceptions.HTTPError as e:
        logger.error(f"Razorpay payout failed: {e.response.text}")
        raise RazorpayError(f"Razorpay API error: {e.response.text}") from e
    except requests.exceptions.RequestException as e:
        logger.error(f"Failed to communicate with Razorpay: {e}")
        raise RazorpayError(f"Network error: {str(e)}") from e
