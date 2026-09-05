from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.orm import Session
from sqlalchemy import text
import hmac
import hashlib
import json
import logging
from app.config import settings
from app.db.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhooks", tags=["webhooks"])

def verify_razorpay_signature(raw_body: bytes, signature: str) -> bool:
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        logger.error("RAZORPAY_WEBHOOK_SECRET is not set")
        return False
    if not signature:
        return False
        
    expected_signature = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
        raw_body,
        hashlib.sha256
    ).hexdigest()
    
    return hmac.compare_digest(expected_signature, signature)

@router.post("/razorpay")
async def razorpay_webhook(request: Request, db: Session = Depends(get_db)):
    raw_body = await request.body()
    signature = request.headers.get("x-razorpay-signature", "")
    
    if not verify_razorpay_signature(raw_body, signature):
        raise HTTPException(status_code=400, detail="Invalid webhook signature")
        
    try:
        payload = json.loads(raw_body)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")
        
    event = payload.get("event")
    refund_events = ["refund.created", "refund.processed", "refund.failed", "refund.speed_changed"]
    payout_events = ["payout.processed", "payout.failed", "payout.reversed"]
    
    if event not in refund_events and event not in payout_events:
        return {"status": "ignored", "event": event}
        
    if event in payout_events:
        return handle_payout_webhook(event, payload, db)
        
    return handle_refund_webhook(event, payload, db)

def handle_payout_webhook(event: str, payload: dict, db: Session):
    payout_entity = payload.get("payload", {}).get("payout", {}).get("entity", {})
    if not payout_entity:
        raise HTTPException(status_code=400, detail="Missing payout entity in payload")
        
    payout_id = payout_entity.get("id")
    if not payout_id:
        raise HTTPException(status_code=400, detail="Missing payout_id")
        
    # Find the corresponding payout row and lock the case for update
    row = db.execute(
        text("""
            SELECT p.case_id, p.status as current_payout_status, c.state as current_case_state
            FROM payouts p
            JOIN refund_cases c ON p.case_id = c.case_id
            WHERE p.razorpay_payout_id = :payout_id
            FOR UPDATE OF c
        """),
        {"payout_id": payout_id}
    ).mappings().first()
    
    if not row:
        # Ignore payout events for unknown payouts (could be unrelated to this system)
        return {"status": "ignored", "reason": "unknown payout_id"}
        
    case_id = row["case_id"]
    current_case_state = row["current_case_state"]
    current_payout_status = row["current_payout_status"]
    
    new_payout_status = event.split(".")[1] # processed, failed, reversed
    
    # If the payout is already in the target status (idempotency), do nothing
    if current_payout_status == new_payout_status:
        db.commit()
        return {"status": "success", "note": "idempotent"}
        
    if current_case_state != "PAYOUT_PENDING":
        # Ignore or log if it's arriving late or out of order, but don't transition
        db.commit()
        return {"status": "ignored", "reason": f"case state is {current_case_state}"}
        
    # Update payouts table
    db.execute(
        text("UPDATE payouts SET status = :status, updated_at = now() WHERE razorpay_payout_id = :payout_id"),
        {"status": new_payout_status, "payout_id": payout_id}
    )
    
    from app.schemas.state import CaseState
    from app.services.state_machine import validate_transition
    
    if new_payout_status == "processed":
        validate_transition(CaseState(current_case_state), CaseState.PAYOUT_SUCCESS)
        validate_transition(CaseState.PAYOUT_SUCCESS, CaseState.RESOLVED)
        
        db.execute(
            text("UPDATE refund_cases SET state = 'RESOLVED', updated_at = now() WHERE case_id = :case_id"),
            {"case_id": case_id}
        )
        db.execute(
            text("""
                INSERT INTO audit_events (case_id, actor_type, actor_id, action, reason)
                VALUES (:case_id, 'SYSTEM', 'system', 'STATE_TRANSITION', 'Payout processed, case resolved')
            """),
            {"case_id": case_id}
        )
    elif new_payout_status in ("failed", "reversed"):
        validate_transition(CaseState(current_case_state), CaseState.PAYOUT_FAILED)
        
        db.execute(
            text("UPDATE refund_cases SET state = 'PAYOUT_FAILED', updated_at = now() WHERE case_id = :case_id"),
            {"case_id": case_id}
        )
        db.execute(
            text("""
                INSERT INTO audit_events (case_id, actor_type, actor_id, action, reason)
                VALUES (:case_id, 'SYSTEM', 'system', 'STATE_TRANSITION', :reason)
            """),
            {"case_id": case_id, "reason": f"Payout {new_payout_status}"}
        )
        
    db.commit()
    return {"status": "success"}

def handle_refund_webhook(event: str, payload: dict, db: Session):
    refund_entity = payload.get("payload", {}).get("refund", {}).get("entity", {})
    if not refund_entity:
        raise HTTPException(status_code=400, detail="Missing refund entity in payload")
        
    refund_id = refund_entity.get("id")
    payment_id = refund_entity.get("payment_id")
    amount = refund_entity.get("amount")
    status = refund_entity.get("status")
    error_reason = refund_entity.get("error_reason")
    error_description = refund_entity.get("error_description")
    failure_reason = error_reason or error_description
    speed_requested = refund_entity.get("speed_requested")
    speed_processed = refund_entity.get("speed_processed")
    
    if not refund_id or not payment_id:
        raise HTTPException(status_code=400, detail="Missing refund_id or payment_id")

    import logging
    logger = logging.getLogger(__name__)

    # Check if payment exists safely
    payment_exists = db.execute(
        text("SELECT 1 FROM payments WHERE payment_id = :payment_id"),
        {"payment_id": payment_id}
    ).scalar()
    
    if not payment_exists:
        logger.error(f"Payment {payment_id} not found for refund {refund_id}")
        raise HTTPException(status_code=404, detail="Payment record not found")

    # Upsert refund record
    db.execute(
        text("""
            INSERT INTO refunds (refund_id, payment_id, amount, status, failure_reason, speed_requested, speed_processed, updated_at)
            VALUES (:id, :pay_id, :amt, :status, :reason, :sr, :sp, now())
            ON CONFLICT (refund_id) DO UPDATE SET
                status = EXCLUDED.status,
                failure_reason = COALESCE(EXCLUDED.failure_reason, refunds.failure_reason),
                speed_requested = COALESCE(EXCLUDED.speed_requested, refunds.speed_requested),
                speed_processed = COALESCE(EXCLUDED.speed_processed, refunds.speed_processed),
                updated_at = now();
        """),
        {
            "id": refund_id,
            "pay_id": payment_id,
            "amt": amount,
            "status": status,
            "reason": failure_reason,
            "sr": speed_requested,
            "sp": speed_processed
        }
    )
    
    # Task 4: Classifier Integration
    if status == "failed":
        from app.services.classifier import classify_refund_failure, FailureType
        
        f_type, c_source = classify_refund_failure(error_reason, error_description)
        
        # 1. Create case directly in REFUND_FAILED state
        # DO NOTHING on conflict, so we don't recreate a case for a retry
        db.execute(
            text("""
                INSERT INTO refund_cases (refund_id, failure_type, classification_source, state)
                VALUES (:refund_id, :failure_type, :classification_source, 'REFUND_FAILED')
                ON CONFLICT (refund_id) DO NOTHING
                RETURNING case_id
            """),
            {"refund_id": refund_id, "failure_type": f_type.value, "classification_source": c_source.value}
        )
        
        # We only advance the state if we actually created it or if we are actively transitioning it now
        # For simplicity, we just try to progress it if it is still in REFUND_FAILED
        db.execute(
            text("""
                UPDATE refund_cases 
                SET state = 'CLASSIFIED', updated_at = now()
                WHERE refund_id = :refund_id AND state = 'REFUND_FAILED'
            """),
            {"refund_id": refund_id}
        )
        
        if f_type == FailureType.TYPE_2_DESTINATION_UNAVAILABLE:
            db.execute(
                text("""
                    UPDATE refund_cases 
                    SET state = 'AWAITING_ALTERNATE', updated_at = now()
                    WHERE refund_id = :refund_id AND state = 'CLASSIFIED'
                """),
                {"refund_id": refund_id}
            )
        
    db.commit()
    
    return {"status": "success"}
