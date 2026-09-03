from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
import hmac
import hashlib
import json
import httpx
from pydantic import BaseModel
import uuid
import time
import logging
from app.config import settings
from app.db.database import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/harness", tags=["harness"])

class HarnessRequest(BaseModel):
    payment_id: str = "pay_TEST123"
    refund_id: str = "rfnd_TEST123"
    amount: int = 10000

@router.post("/force_refund_failure")
async def force_refund_failure(req: HarnessRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    MANUAL TEST HARNESS:
    Generates a synthetic refund.failed webhook and forwards it to the real webhook receiver.
    NOT a real Razorpay endpoint.
    """
    if not settings.RAZORPAY_WEBHOOK_SECRET:
        raise HTTPException(status_code=500, detail="RAZORPAY_WEBHOOK_SECRET not configured")

    customer_id = str(uuid.uuid4())
    
    # 1. Create a dummy customer
    db.execute(
        text("INSERT INTO customers (customer_id, name, email) VALUES (:cid, 'Test User', 'test@example.com')"),
        {"cid": customer_id}
    )
    
    # 2. Create the prerequisite payment explicitly
    db.execute(
        text("""
            INSERT INTO payments (payment_id, customer_id, amount, status)
            VALUES (:pay_id, :cid, :amt, 'captured')
            ON CONFLICT (payment_id) DO NOTHING
        """),
        {"pay_id": req.payment_id, "cid": customer_id, "amt": req.amount}
    )
    db.commit()

    # 3. Generate byte-for-byte webhook payload
    payload = {
      "entity": "event",
      "account_id": "acc_TEST",
      "event": "refund.failed",
      "contains": ["refund"],
      "payload": {
        "refund": {
          "entity": {
            "id": req.refund_id,
            "entity": "refund",
            "amount": req.amount,
            "currency": "INR",
            "payment_id": req.payment_id,
            "status": "failed",
            "error_reason": "destination_unavailable",
            "error_description": "Bank account closed",
            "created_at": int(time.time())
          }
        }
      },
      "created_at": int(time.time())
    }
    
    raw_body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
    
    # 4. Sign it
    signature = hmac.new(
        settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
        raw_body,
        hashlib.sha256
    ).hexdigest()
    
    # 5. Forward to real webhook receiver in the background
    async def forward_webhook(body: bytes, sig: str):
        async with httpx.AsyncClient() as client:
            try:
                await client.post(
                    "http://127.0.0.1:8000/webhooks/razorpay",
                    content=body,
                    headers={"x-razorpay-signature": sig, "Content-Type": "application/json"}
                )
            except Exception as e:
                logger.error(f"Test harness failed to forward webhook: {e}")

    background_tasks.add_task(forward_webhook, raw_body, signature)
    
    return {
        "status": "synthetic webhook generated",
        "payment_id": req.payment_id,
        "refund_id": req.refund_id,
        "signature": signature
    }
