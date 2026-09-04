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
    if event not in ["refund.created", "refund.processed", "refund.failed", "refund.speed_changed"]:
        return {"status": "ignored", "event": event}
        
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
