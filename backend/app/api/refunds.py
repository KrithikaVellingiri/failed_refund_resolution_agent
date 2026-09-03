from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.database import get_db

router = APIRouter(prefix="/v1/refunds", tags=["refunds"])

@router.get("/{refund_id}")
def get_refund(refund_id: str, db: Session = Depends(get_db)):
    """
    Looks up a refund by its ID. Used for the duplicate-guard flow later.
    """
    row = db.execute(
        text("SELECT refund_id, payment_id, amount, status, failure_reason FROM refunds WHERE refund_id = :id"),
        {"id": refund_id}
    ).mappings().first()
    
    if not row:
        raise HTTPException(status_code=404, detail="Refund not found")
        
    return dict(row)
