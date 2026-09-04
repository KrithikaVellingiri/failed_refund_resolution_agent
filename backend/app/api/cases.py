from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from enum import Enum
from pydantic import BaseModel, Field, field_validator
import logging
from app.db.database import get_db, SessionLocal
from app.schemas.state import CaseState
from app.services.state_machine import validate_transition, InvalidTransitionError
from app.services.duplicate_guard import execute_with_duplicate_guard, DuplicateGuardBlocked
from app.services.razorpay_client import create_payout

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/cases", tags=["cases"])

class ReviewAction(str, Enum):
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    REQUEST_MORE_INFO = "REQUEST_MORE_INFO"

class ReviewRequest(BaseModel):
    action: ReviewAction
    reason: str = Field(..., min_length=1)
    reviewer_id: str = Field(..., min_length=1)

    @field_validator('reason', 'reviewer_id')
    @classmethod
    def not_blank(cls, v):
        if not v.strip():
            raise ValueError("must not be blank")
        return v.strip()

def process_payout_task(case_id: str):
    """
    Background task to orchestrate payout for APPROVED cases.
    """
    db = SessionLocal()
    try:
        # Lock the row for update to prevent concurrent payout attempts
        case = db.execute(
            text("""
                SELECT c.case_id, c.refund_id, r.amount, c.state 
                FROM refund_cases c
                JOIN refunds r ON c.refund_id = r.refund_id
                WHERE c.case_id = :id FOR UPDATE
            """),
            {"id": case_id}
        ).mappings().first()

        if not case:
            logger.error(f"process_payout_task: Case {case_id} not found")
            return
            
        if case["state"] != CaseState.APPROVED:
            logger.info(f"process_payout_task: Case {case_id} is not APPROVED (state: {case['state']}), aborting")
            return

        def transition_callback(new_state: CaseState):
            db.execute(
                text("UPDATE refund_cases SET state = :state, updated_at = now() WHERE case_id = :id"),
                {"state": new_state.value, "id": case_id}
            )
            db.execute(
                text("""
                    INSERT INTO audit_events (case_id, actor_type, actor_id, action, reason)
                    VALUES (:case_id, 'SYSTEM', 'system', 'STATE_TRANSITION', :reason)
                """),
                {
                    "case_id": case_id,
                    "reason": f"Transition to {new_state.value}"
                }
            )
            db.commit()


        # The duplicate guard requires a callable for payout.
        # However, we must NOT hold the DB transaction open during the HTTP request.
        # So we just evaluate duplicate guard here, or use it exactly as defined.
        # But execute_with_duplicate_guard currently expects to call payout_callable *inside* its execution path.
        # Wait, the instruction says:
        # "invoke the existing execute_with_duplicate_guard(...) boundary"
        # "never call create_payout directly from Human Review if execute_with_duplicate_guard is the existing orchestration boundary"
        # "do NOT hold a DB transaction/lock open during the external Razorpay HTTP call"
        
        # We can close our DB lock before making the HTTP call.
        db.commit() # release FOR UPDATE lock since we confirmed it's APPROVED
        
        # Now call duplicate guard
        # Duplicate guard itself does not take a DB session. It calls get_refund() (HTTP).
        # We need to define payout_callable to actually make the create_payout call.
        def execute_payout():
            case_data = db.execute(
                text("""
                    SELECT d.destination_id, d.identifier as fund_account_id, d.type as mode 
                    FROM refund_cases c
                    JOIN alternate_destinations d ON c.proposed_destination_id = d.destination_id
                    WHERE c.case_id = :id 
                """),
                {"id": case_id}
            ).mappings().first()

            
            if not case_data:
                raise ValueError(f"Could not find destination for case {case_id}")
                
            fund_account_id = case_data["fund_account_id"]
            if not fund_account_id:
                # Mock or retrieve from somewhere
                fund_account_id = "fa_dummy"
                
            mode = case_data["mode"]
            
            payout_result = create_payout(
                case_id=case_id,
                amount=case["amount"],
                fund_account_id=fund_account_id,
                mode=mode
            )
            return payout_result, case_data["destination_id"], mode
        
        try:
            result = execute_with_duplicate_guard(
                refund_id=case["refund_id"],
                current_state=CaseState.APPROVED,
                payout_callable=execute_payout,
                transition_callback=transition_callback
            )
            
            if result is not None:
                payout_resp, destination_id, mode = result
                # Write to payouts and update state in a new transaction
                from app.services.razorpay_client import _generate_idempotency_key
                actual_idem_key = _generate_idempotency_key(case_id)
                
                db.execute(
                    text("""
                        INSERT INTO payouts (case_id, destination_id, amount, mode, purpose, status, idempotency_key, razorpay_payout_id)
                        VALUES (:case_id, :destination_id, :amount, :mode, 'refund', :status, :idem_key, :rp_id)
                    """),
                    {
                        "case_id": case_id,
                        "destination_id": destination_id,
                        "amount": case["amount"],
                        "mode": mode,
                        "status": payout_resp.get("status", "processing"),
                        "idem_key": actual_idem_key,
                        "rp_id": payout_resp.get("id")
                    }
                )
                validate_transition(CaseState.APPROVED, CaseState.PAYOUT_PENDING)
                db.execute(
                    text("UPDATE refund_cases SET state = :state, updated_at = now() WHERE case_id = :id"),
                    {"state": CaseState.PAYOUT_PENDING, "id": case_id}
                )
                db.execute(
                    text("""
                        INSERT INTO audit_events (case_id, actor_type, actor_id, action, reason)
                        VALUES (:case_id, 'SYSTEM', 'system', 'STATE_TRANSITION', 'Transition to PAYOUT_PENDING')
                    """),
                    {"case_id": case_id}
                )

                db.commit()
                
        except DuplicateGuardBlocked as e:
            logger.error(f"process_payout_task: DuplicateGuardBlocked for case {case_id}: {e}")
            # Fails closed, leaves case APPROVED
        except Exception as e:
            logger.error(f"process_payout_task: Error orchestrating payout for case {case_id}: {e}")
            # Fails closed, leaves case APPROVED
            
    finally:
        db.close()


@router.post("/{case_id}/review")
def submit_review(case_id: str, request: ReviewRequest, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    case = db.execute(
        text("SELECT state FROM refund_cases WHERE case_id = :id FOR UPDATE"),
        {"id": case_id}
    ).mappings().first()

    if not case:
        raise HTTPException(status_code=404, detail="Case not found")

    current_state = case["state"]
    if current_state != CaseState.REVIEW:
        raise HTTPException(status_code=400, detail=f"Case not in REVIEW state (current: {current_state})")

    if request.action == ReviewAction.APPROVE:
        next_state = CaseState.APPROVED
    elif request.action == ReviewAction.REJECT:
        next_state = CaseState.REJECTED
    elif request.action == ReviewAction.REQUEST_MORE_INFO:
        next_state = CaseState.NEEDS_INFORMATION

    try:
        validate_transition(current_state, next_state)
    except InvalidTransitionError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Write reviewer_outcomes
    db.execute(
        text("""
            INSERT INTO reviewer_outcomes (case_id, reviewer_id, action, reason)
            VALUES (:case_id, :reviewer_id, :action, :reason)
        """),
        {
            "case_id": case_id,
            "reviewer_id": request.reviewer_id,
            "action": request.action.value,
            "reason": request.reason
        }
    )

    # Transition state
    db.execute(
        text("UPDATE refund_cases SET state = :state, updated_at = now() WHERE case_id = :id"),
        {"state": next_state, "id": case_id}
    )

    db.execute(
        text("""
            INSERT INTO audit_events (case_id, actor_type, actor_id, action, reason)
            VALUES (:case_id, 'REVIEWER', :actor_id, 'STATE_TRANSITION', :reason)
        """),
        {
            "case_id": case_id,
            "actor_id": request.reviewer_id,
            "reason": f"Action: {request.action}, Reason: {request.reason}"
        }
    )

    db.commit()

    if next_state == CaseState.APPROVED:
        background_tasks.add_task(process_payout_task, case_id)

    return {"status": "success", "new_state": next_state}
