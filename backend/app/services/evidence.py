from typing import Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import text
from datetime import datetime, timezone
from difflib import SequenceMatcher

def aggregate_evidence(case_id: str, db: Session) -> Dict[str, Any]:
    """
    Deterministic evidence aggregator for Task 6.
    Gathers structured evidence required for a Type 2 refund case.
    """
    # 1. Fetch case details
    case_query = text("""
        SELECT r.refund_id, r.payment_id, r.amount as refund_amount,
               rc.proposed_destination_id, p.amount as payment_amount, p.customer_id
        FROM refund_cases rc
        JOIN refunds r ON rc.refund_id = r.refund_id
        JOIN payments p ON r.payment_id = p.payment_id
        WHERE rc.case_id = :case_id
    """)
    case_row = db.execute(case_query, {"case_id": case_id}).fetchone()
    
    if not case_row:
        raise ValueError(f"Refund case {case_id} not found.")

    proposed_destination_id = case_row.proposed_destination_id
    customer_id = case_row.customer_id
    refund_amount = case_row.refund_amount
    payment_amount = case_row.payment_amount

    # Base bundle with missing evidence assumptions
    bundle: Dict[str, Any] = {
        "case_id": str(case_id),
        "destination_age_days": None,
        "destination_prior_uses": None,
        "redirect_count_30d": 0,
        "amount_matches_original": bool(refund_amount == payment_amount),
        "name_similarity_score": None,
        "ownership_signal": "UNAVAILABLE",
        "message_risk_flags": None  # LLM step intentionally omitted in Task 6
    }

    # Fetch customer for name matching
    customer_name = db.execute(
        text("SELECT name FROM customers WHERE customer_id = :cid"), 
        {"cid": customer_id}
    ).scalar()

    # 30-day redirect count
    # Count alternate destinations submitted by this customer in the last 30 days
    redirect_count = db.execute(
        text("""
            SELECT COUNT(*) FROM alternate_destinations 
            WHERE customer_id = :cid AND submitted_at >= NOW() - INTERVAL '30 days'
        """),
        {"cid": customer_id}
    ).scalar()
    bundle["redirect_count_30d"] = redirect_count

    # If no alternate destination is proposed yet, return missing evidence bundle
    if not proposed_destination_id:
        return bundle

    # Fetch alternate destination
    dest_row = db.execute(
        text("SELECT first_seen_at, times_used, holder_name FROM alternate_destinations WHERE destination_id = :did"),
        {"did": proposed_destination_id}
    ).fetchone()

    if dest_row:
        first_seen_at = dest_row.first_seen_at
        if first_seen_at.tzinfo is None:
            first_seen_at = first_seen_at.replace(tzinfo=timezone.utc)
            
        now_utc = datetime.now(timezone.utc)
        age_days = max(0, (now_utc - first_seen_at).days)
        
        bundle["destination_age_days"] = age_days
        bundle["destination_prior_uses"] = dest_row.times_used

        holder_name = dest_row.holder_name
        
        if holder_name and customer_name:
            # Deterministic similarity score
            score = SequenceMatcher(None, holder_name.lower(), customer_name.lower()).ratio()
            bundle["name_similarity_score"] = round(score, 3)
            
            # Synthetic Ownership Signal Logic (deterministic simulation of external API)
            if score > 0.8:
                bundle["ownership_signal"] = "VERIFIED_SYNTHETIC"
            else:
                bundle["ownership_signal"] = "MISMATCH_SYNTHETIC"

    return bundle
