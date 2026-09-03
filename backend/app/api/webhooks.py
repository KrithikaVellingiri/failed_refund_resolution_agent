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
    failure_reason = refund_entity.get("error_reason") or refund_entity.get("error_description")
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
    
    db.commit()
    
    return {"status": "success"}
