import sys
import os
import json
import time
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))
from app.db.database import SessionLocal
from sqlalchemy import text
from app.services.evidence import aggregate_evidence
from app.services.policy import compute_risk_score, evaluate_policy
from app.services.evidence_coverage import calculate_evidence_coverage
from app.services.contradiction_checker import check_claims
from app.services.llm_client import ExtractedClaims, MessageRiskFlags

def simulate_decision(risk_score, reasons, review_thresh, reject_thresh):
    """
    Re-applies the policy engine's tier logic using alternative risk score thresholds.
    This explicitly preserves all deterministic safety rules (e.g. LLM flags, novelty)
    and only modifies the numeric risk thresholds.
    """
    if (risk_score >= reject_thresh or 
        "NAME_MISMATCH_BELOW_FLOOR" in reasons or 
        "REDIRECT_VELOCITY_HIGH" in reasons):
        return "REJECT"
        
    if (risk_score >= review_thresh or
        "OVER_AUTO_APPROVAL_LIMIT" in reasons or
        "INSUFFICIENT_EVIDENCE" in reasons or
        "LLM_MESSAGE_RISK" in reasons or
        "NEW_DESTINATION" in reasons or
        "AMOUNT_MISMATCH" in reasons):
        return "REVIEW"
        
    return "APPROVE"

def run_simulation():
    db = SessionLocal()
    cases = db.execute(text("SELECT eval_case_id, case_payload, ground_truth_label FROM evaluation_cases WHERE split = 'HELD_OUT'")).fetchall()
    
    # Pre-compute all evidence and baseline reasons to avoid duplicating policy execution
    evaluated_cases = []
    
    for row in cases:
        payload = row.case_payload
        gt = row.ground_truth_label
        case_id = payload["case_id"]
        
        bundle = aggregate_evidence(case_id, db)
        
        extracted_claims_data = payload.get("extracted_claims")
        if extracted_claims_data:
            extracted_claims = ExtractedClaims(**extracted_claims_data)
        else:
            extracted_claims = ExtractedClaims(
                claims=[],
                message_risk_flags=MessageRiskFlags(
                    urgency_language=False,
                    third_party_destination=False,
                    avoid_verified_channel=False,
                    instruction_manipulation=False
                )
            )
            
        checks = check_claims(extracted_claims, bundle)
        coverage = calculate_evidence_coverage(bundle, checks)
        risk_score = compute_risk_score(bundle, checks)
        
        case_row = db.execute(text("SELECT amount FROM refunds WHERE refund_id = (SELECT refund_id FROM refund_cases WHERE case_id = :cid)"), {"cid": case_id}).fetchone()
        amount_paise = case_row.amount
        known_dest = bool(bundle.get("destination_prior_uses", 0) > 0)
        
        # We run the baseline evaluate_policy just to extract the raw 'reasons' array
        # which contains the output of all deterministic safety checks.
        baseline_decision, reasons = evaluate_policy(
            risk_score=risk_score,
            evidence_coverage=coverage,
            contradiction_results=checks,
            message_risk_flags=extracted_claims.message_risk_flags.model_dump(),
            amount_paise=amount_paise,
            known_destination=known_dest,
            amount_matches_original=bundle.get("amount_matches_original", False),
            risk_signals=bundle
        )
        
        evaluated_cases.append({
            "case_id": case_id,
            "ground_truth": gt,
            "risk_score": risk_score,
            "reasons": reasons,
            "baseline_decision": baseline_decision
        })
        
    db.close()
    
    print("=== TASK 12C P1 THRESHOLD SIMULATOR ===")
    print("ASSUMPTION: one false approval costs 20x one review/operational cost unit.")
    print("COST FORMULA: Expected Cost = (Review Count * 1) + (False Approval Count * 20)")
    print()
    
    # Define configurations to test
    # Baseline is (31, 71)
    configs = [
        {"name": "Current Baseline", "review": 31, "reject": 71},
        {"name": "Ultra Conservative", "review": 10, "reject": 50},
        {"name": "Aggressive Auto-Approve", "review": 40, "reject": 71},
        {"name": "Very Aggressive Auto-Approve", "review": 50, "reject": 80},
    ]
    
    print(f"{'Configuration':<30} | {'APPROVE':<7} | {'REVIEW':<6} | {'REJECT':<6} | {'Auto %':<6} | {'FAR %':<5} | {'Rev %':<5} | {'Expected Cost'}")
    print("-" * 105)
    
    for cfg in configs:
        total = len(evaluated_cases)
        approve_c = 0
        review_c = 0
        reject_c = 0
        fp_far = 0
        
        for c in evaluated_cases:
            decision = simulate_decision(c["risk_score"], c["reasons"], cfg["review"], cfg["reject"])
            
            if decision == "APPROVE":
                approve_c += 1
                if c["ground_truth"] == "ADVERSARIAL":
                    fp_far += 1
            elif decision == "REVIEW":
                review_c += 1
            elif decision == "REJECT":
                reject_c += 1
                
        auto_rate = (approve_c + reject_c) / total * 100
        far_rate = fp_far / total * 100
        rev_rate = review_c / total * 100
        
        expected_cost = (review_c * 1) + (fp_far * 20)
        
        name_str = f"{cfg['name']} (Rev>={cfg['review']}, Rej>={cfg['reject']})"
        print(f"{name_str:<45} | {approve_c:<7} | {review_c:<6} | {reject_c:<6} | {auto_rate:5.1f}% | {far_rate:4.1f}% | {rev_rate:4.1f}% | {expected_cost}")

if __name__ == "__main__":
    run_simulation()
