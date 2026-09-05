from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import text
from typing import List, Any, Dict, Optional
from pydantic import BaseModel
from datetime import datetime
import json
from app.db.database import get_db

router = APIRouter(prefix="/v1/evaluations", tags=["evaluations"])

class EvaluationRunItem(BaseModel):
    run_id: str
    timestamp: datetime
    dataset_version: str
    policy_version: str
    model_version: Optional[str]

    class Config:
        from_attributes = True

class EvaluationRunDetail(BaseModel):
    run_id: str
    timestamp: datetime
    dataset_version: str
    policy_version: str
    model_version: Optional[str]
    metrics: Dict[str, Any]

    class Config:
        from_attributes = True


@router.get("", response_model=List[EvaluationRunItem])
def list_evaluation_runs(db: Session = Depends(get_db)):
    rows = db.execute(text("""
        SELECT eval_run_id, created_at, dataset_version, policy_version, model_version
        FROM evaluation_runs
        ORDER BY created_at DESC
    """)).mappings().fetchall()
    
    return [
        EvaluationRunItem(
            run_id=str(r["eval_run_id"]),
            timestamp=r["created_at"],
            dataset_version=r["dataset_version"],
            policy_version=r["policy_version"],
            model_version=r["model_version"]
        ) for r in rows
    ]

@router.get("/{run_id}", response_model=EvaluationRunDetail)
def get_evaluation_run(run_id: str, db: Session = Depends(get_db)):
    row = db.execute(text("""
        SELECT eval_run_id, created_at, dataset_version, policy_version, model_version, metrics
        FROM evaluation_runs
        WHERE eval_run_id = :id
    """), {"id": run_id}).mappings().first()
    
    if not row:
        raise HTTPException(status_code=404, detail="Run not found")
        
    metrics = row["metrics"] if row["metrics"] else {}
    if isinstance(metrics, str):
        metrics = json.loads(metrics)
        
    return EvaluationRunDetail(
        run_id=str(row["eval_run_id"]),
        timestamp=row["created_at"],
        dataset_version=row["dataset_version"],
        policy_version=row["policy_version"],
        model_version=row["model_version"],
        metrics=metrics
    )
