from fastapi import FastAPI, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from app.db.database import get_db, engine
from app.config import settings
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Failed-Refund Resolution Agent")

@app.get("/health")
def health_check(db: Session = Depends(get_db)):
    try:
        # Check database connectivity
        db.execute(text("SELECT 1"))
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Database connection failed: {e}")
        raise HTTPException(status_code=503, detail="Database connection failed")

from app.api import webhooks, harness, refunds, cases, evaluations
app.include_router(webhooks.router)
app.include_router(harness.router)
app.include_router(refunds.router)
app.include_router(cases.router)
app.include_router(evaluations.router)
