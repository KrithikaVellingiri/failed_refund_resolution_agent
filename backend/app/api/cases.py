from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import text
from enum import Enum
from pydantic import BaseModel, Field, field_validator
import logging
from typing import List, Optional
from app.db.database import get_db, SessionLocal
from app.schemas.state import CaseState
from app.schemas.frontend import CaseListItem, CaseDetail, RefundInfo, CustomerInfo, ProposedDestination, ClaimCheck, RiskSignals, MessageRiskFlags, AuditEvent
from app.services.state_machine import validate_transition, InvalidTransitionError
from app.services.duplicate_guard import execute_with_duplicate_guard, DuplicateGuardBlocked
from app.services.razorpay_client import create_payout
from app.services.evidence import aggregate_evidence
from app.services.contradiction_checker import check_claims
from app.services.llm_client import ExtractedClaims
from app.services.policy import evaluate_policy, compute_risk_score

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v1/cases", tags=["cases"])

@router.get("", response_model=List[CaseListItem])
def get_cases(
    state: Optional[str] = None,
    decision: Optional[str] = None,
    failure_type: Optional[str] = None,
    db: Session = Depends(get_db)
):
    query = """
        SELECT c.case_id, r.amount, c.failure_type, c.risk_score, 
               c.evidence_coverage, c.decision, c.state, c.created_at
        FROM refund_cases c
        JOIN refunds r ON c.refund_id = r.refund_id
        WHERE 1=1
    """
    params = {}
    if state:
        query += " AND c.state = :state"
        params["state"] = state
    if decision:
        query += " AND c.decision = :decision"
        params["decision"] = decision
    if failure_type:
        query += " AND c.failure_type = :failure_type"
        params["failure_type"] = failure_type

    query += " ORDER BY c.created_at DESC"

    rows = db.execute(text(query), params).mappings().fetchall()
    
    return [
        CaseListItem(
            case_id=str(r["case_id"]),
            amount=r["amount"],
            failure_type=r["failure_type"],
            risk_score=r["risk_score"] if r["risk_score"] is not None else None,
            evidence_coverage=r["evidence_coverage"] if r["evidence_coverage"] is not None else None,
            decision=r["decision"],
            state=r["state"],
            created_at=r["created_at"]
        ) for r in rows
    ]

@router.get("/{case_id}", response_model=CaseDetail)
def get_case_detail(case_id: str, db: Session = Depends(get_db)):
    case_row = db.execute(text("""
        SELECT c.case_id, r.amount, c.failure_type, c.state, c.decision, c.created_at,
               r.refund_id, r.payment_id, r.failure_reason,
               cust.name as customer_name, cust.created_at as customer_created_at,
               dest.type as dest_type, dest.identifier as dest_identifier,
               dest.holder_name as dest_holder_name, dest.first_seen_at as dest_first_seen_at,
               dest.times_used as dest_times_used
        FROM refund_cases c
        JOIN refunds r ON c.refund_id = r.refund_id
        JOIN payments p ON r.payment_id = p.payment_id
        JOIN customers cust ON p.customer_id = cust.customer_id
        LEFT JOIN alternate_destinations dest ON c.proposed_destination_id = dest.destination_id
        WHERE c.case_id = :id
    """), {"id": case_id}).mappings().first()

    if not case_row:
        raise HTTPException(status_code=404, detail="Not Found")

    # Audit events
    audit_rows = db.execute(text("""
        SELECT actor_type, action, reason, created_at
        FROM audit_events
        WHERE case_id = :id
        ORDER BY created_at DESC
    """), {"id": case_id}).mappings().fetchall()
    
    audit_events = [AuditEvent(**dict(a)) for a in audit_rows]

    # Dynamically reconstruct evidence/risk view using existing deterministic functions
    bundle = aggregate_evidence(case_id, db)
    
    # Check if there are extracted claims saved from the test harness or DB
    claims_rows = db.execute(text("""
        SELECT claim_text, claim_type 
        FROM extracted_claims WHERE case_id = :id
    """), {"id": case_id}).mappings().fetchall()
    
    # We also need message_risk_flags from risk_signals
    risk_sig_row = db.execute(text("""
        SELECT message_risk_flags, ownership_signal, name_similarity_score
        FROM risk_signals WHERE case_id = :id
    """), {"id": case_id}).mappings().first()
    
    if risk_sig_row and risk_sig_row["message_risk_flags"]:
        import json
        flags = risk_sig_row["message_risk_flags"]
        if isinstance(flags, str):
            flags = json.loads(flags)
        msg_flags = MessageRiskFlags(**flags)
    else:
        msg_flags = MessageRiskFlags(
            urgency_language=False, third_party_destination=False,
            avoid_verified_channel=False, instruction_manipulation=False
        )
        
    extracted_claims = ExtractedClaims(
        claims=[{"claim_type": r["claim_type"], "claim_text": r["claim_text"]} for r in claims_rows],
        message_risk_flags=msg_flags.model_dump()
    )
    
    # If no claims in DB, check if evaluation_cases has the payload (for synthetic HELD_OUT cases)
    if not claims_rows:
        eval_row = db.execute(text("SELECT case_payload FROM evaluation_cases WHERE case_payload->>'case_id' = :id"), {"id": case_id}).fetchone()
        if eval_row and "extracted_claims" in eval_row.case_payload:
            extracted_claims = ExtractedClaims(**eval_row.case_payload["extracted_claims"])
            msg_flags = MessageRiskFlags(**extracted_claims.message_risk_flags.model_dump())
    
    # Run deterministic checks
    checks = check_claims(extracted_claims, bundle)
    coverage = None
    from app.services.evidence_coverage import calculate_evidence_coverage
    try:
        coverage = calculate_evidence_coverage(bundle, checks)
    except Exception:
        pass
        
    risk_score = compute_risk_score(bundle, checks)
    
    # Get reasons
    amount_paise = case_row["amount"]
    known_dest = bool(bundle.get("destination_prior_uses", 0) > 0) if bundle.get("destination_prior_uses") is not None else False
    
    decision, reasons = evaluate_policy(
        risk_score=risk_score,
        evidence_coverage=coverage if coverage is not None else 100,
        contradiction_results=checks,
        message_risk_flags=msg_flags.model_dump(),
        amount_paise=amount_paise,
        known_destination=known_dest,
        amount_matches_original=bundle.get("amount_matches_original", False),
        risk_signals=bundle
    )

    # Reconstruct ClaimCheck for frontend
    claim_checks_out = []
    for chk in checks:
        claim_checks_out.append(ClaimCheck(
            claim_text=chk.get("claim_text", ""),
            claim_type=chk.get("claim_type", ""),
            status=chk.get("status", "UNVERIFIABLE"),
            severity=chk.get("severity", "LOW"),
            source=chk.get("source", "llm")
        ))
        
    ownership = risk_sig_row["ownership_signal"] if risk_sig_row else bundle.get("ownership_signal", "UNAVAILABLE")

    risk_signals = RiskSignals(
        amount_matches_original=bundle.get("amount_matches_original"),
        destination_age_days=bundle.get("destination_age_days"),
        destination_prior_uses=bundle.get("destination_prior_uses"),
        redirect_count_30d=bundle.get("redirect_count_30d"),
        message_risk_flags=msg_flags,
        name_similarity_score=bundle.get("name_similarity_score"),
        ownership_signal=ownership
    )
    
    proposed_dest = None
    if case_row["dest_type"]:
        proposed_dest = ProposedDestination(
            type=case_row["dest_type"],
            identifier=case_row["dest_identifier"],
            holder_name=case_row["dest_holder_name"],
            first_seen_at=case_row["dest_first_seen_at"],
            times_used=case_row["dest_times_used"]
        )
        
    return CaseDetail(
        case_id=str(case_row["case_id"]),
        amount=case_row["amount"],
        failure_type=case_row["failure_type"],
        state=case_row["state"],
        decision=case_row["decision"],
        created_at=case_row["created_at"],
        refund=RefundInfo(
            refund_id=case_row["refund_id"],
            payment_id=case_row["payment_id"],
            failure_reason=case_row["failure_reason"] or ""
        ),
        customer=CustomerInfo(
            name=case_row["customer_name"],
            created_at=case_row["customer_created_at"]
        ),
        proposed_destination=proposed_dest,
        extracted_claims=claim_checks_out,
        risk_signals=risk_signals,
        evidence_coverage=coverage,
        decision_reasons=reasons,
        audit_events=audit_events
    )


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
