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
