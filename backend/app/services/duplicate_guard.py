import logging
from typing import Callable, Any
from app.services.razorpay_client import get_refund, RazorpayError
from app.schemas.state import CaseState
from app.services.state_machine import validate_transition

logger = logging.getLogger(__name__)

class DuplicateGuardBlocked(Exception):
    """Raised when the duplicate guard fails closed (network error, timeout, malformed, unknown status)."""
    pass

def execute_with_duplicate_guard(
    refund_id: str, 
    current_state: CaseState, 
    payout_callable: Callable[[], Any], 
    transition_callback: Callable[[CaseState], None]
) -> Any:
    """
    Mandatory duplicate guard (Task 11A).
    Must be called immediately before payout.
    
    Args:
        refund_id: The Razorpay refund_id to check.
        current_state: The current state of the case (should be APPROVED).
        payout_callable: A callable that initiates the actual payout.
        transition_callback: A callback to transition the case's state.
        
    Returns:
        The result of payout_callable if safe to proceed. Returns None if blocked as duplicate.
        
    Raises:
        DuplicateGuardBlocked if the guard fails closed (network/malformed/unknown status).
    """
    try:
        live_refund = get_refund(refund_id)
    except RazorpayError as e:
        logger.error(f"Duplicate guard blocked due to API error: {e}")
        raise DuplicateGuardBlocked("Failed to verify original refund status") from e
    except Exception as e:
        logger.error(f"Duplicate guard blocked due to unexpected error: {e}")
        raise DuplicateGuardBlocked("Unexpected error verifying original refund") from e
        
    if not isinstance(live_refund, dict) or "status" not in live_refund:
        logger.error("Duplicate guard blocked due to malformed response")
        raise DuplicateGuardBlocked("Malformed response from Razorpay")
        
    status = live_refund.get("status")
    
    if status == "processed":
        logger.info(f"Duplicate refund detected for {refund_id}. Payout blocked.")
        
        # 2. If the live original refund status is `processed`:
        # - transition the case to `DUPLICATE_GUARD_TRIGGERED`
        validate_transition(current_state, CaseState.DUPLICATE_GUARD_TRIGGERED)
        transition_callback(CaseState.DUPLICATE_GUARD_TRIGGERED)
        
        # - then transition it to `RESOLVED`
        validate_transition(CaseState.DUPLICATE_GUARD_TRIGGERED, CaseState.RESOLVED)
        transition_callback(CaseState.RESOLVED)
        
        # - DO NOT call the alternate payout.
        return None
        
    if status not in ("pending", "failed"):
        logger.error(f"Duplicate guard blocked due to unknown status: {status}")
        raise DuplicateGuardBlocked(f"Unknown refund status: {status}")
        
    # 3. If the original refund is NOT `processed`:
    # allow the caller to continue toward the payout step.
    return payout_callable()
