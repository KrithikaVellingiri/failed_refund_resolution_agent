import sys
import os
import time
import json
import unittest

sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.db.database import SessionLocal
from sqlalchemy import text
from app.services.evidence import aggregate_evidence
from app.services.policy import compute_risk_score, evaluate_policy
from app.services.evidence_coverage import calculate_evidence_coverage
from app.services.contradiction_checker import check_claims
from app.services.llm_client import ExtractedClaims, MessageRiskFlags, Claim

class Metrics:
    def __init__(self):
        self.total = 0
        self.tp_precision = 0
        self.tp_recall = 0
        self.fp_far = 0
        self.fn_frr = 0
        self.total_reject = 0
        self.total_adversarial = 0
        self.total_legitimate = 0
        self.total_review = 0
        self.total_approve = 0
        self.total_latency = 0
        
        self.confusion_matrix = {
            "LEGITIMATE": {"APPROVE": 0, "REVIEW": 0, "REJECT": 0},
            "AMBIGUOUS": {"APPROVE": 0, "REVIEW": 0, "REJECT": 0},
            "ADVERSARIAL": {"APPROVE": 0, "REVIEW": 0, "REJECT": 0}
        }
        
        self.exceptions = []
    
    def add_case(self, ground_truth, predicted, latency_ms, case_id, reason_codes):
        self.total += 1
        self.total_latency += latency_ms
        self.confusion_matrix[ground_truth][predicted] += 1
        
        if ground_truth == "ADVERSARIAL":
            self.total_adversarial += 1
            if predicted == "REJECT":
                self.tp_recall += 1
            elif predicted == "APPROVE":
                self.fp_far += 1
                
        if predicted == "REJECT":
            self.total_reject += 1
            if ground_truth == "ADVERSARIAL":
                self.tp_precision += 1
                
        if ground_truth == "LEGITIMATE":
            self.total_legitimate += 1
            if predicted == "REJECT":
                self.fn_frr += 1
                
        if predicted == "REVIEW":
            self.total_review += 1
            
            # Check for exceptions (insufficient info / safety defaults)
            exception_reasons = []
            for r in ["INSUFFICIENT_EVIDENCE", "OWNERSHIP_UNAVAILABLE", "LLM_UNAVAILABLE"]:
                if r in reason_codes:
                    exception_reasons.append(r)
            if exception_reasons:
                self.exceptions.append({
                    "case_id": case_id,
                    "ground_truth": ground_truth,
                    "predicted": predicted,
                    "reason_codes": reason_codes,
                    "exception_reason": ", ".join(exception_reasons)
                })
                
        elif predicted == "APPROVE":
            self.total_approve += 1

    def print_report(self):
        print("\n--- DATASET SUMMARY ---")
        print(f"Total evaluated cases: {self.total}")
        print(f"LEGITIMATE: {self.total_legitimate}")
        print(f"AMBIGUOUS: {sum(self.confusion_matrix['AMBIGUOUS'].values())}")
        print(f"ADVERSARIAL: {self.total_adversarial}")

        print("\n--- DECISION DISTRIBUTION ---")
        print(f"APPROVE: {self.total_approve}")
        print(f"REVIEW: {self.total_review}")
        print(f"REJECT: {self.total_reject}")

        print("\n--- REQUIRED METRICS ---")
        
        # Precision: (ADVERSARIAL ∩ REJECT) / (Total REJECT)
        if self.total_reject == 0:
            precision_str = "N/A"
        else:
            precision_str = f"{100.0 * self.tp_precision / self.total_reject:.1f}% ({self.tp_precision} / {self.total_reject})"
        print(f"Precision: {precision_str}")
        
        # Recall: (ADVERSARIAL ∩ REJECT) / (Total ADVERSARIAL)
        if self.total_adversarial == 0:
            recall_str = "N/A"
        else:
            recall_str = f"{100.0 * self.tp_recall / self.total_adversarial:.1f}% ({self.tp_recall} / {self.total_adversarial})"
        print(f"Recall: {recall_str}")
        
        # FAR: (ADVERSARIAL ∩ APPROVE) / Total
        if self.total == 0:
            far_str = "N/A"
        else:
            far_str = f"{100.0 * self.fp_far / self.total:.1f}% ({self.fp_far} / {self.total})"
        print(f"False-Approval Rate (FAR): {far_str}")
        
        # FRR: (LEGITIMATE ∩ REJECT) / Total LEGITIMATE
        if self.total_legitimate == 0:
            frr_str = "N/A"
        else:
            frr_str = f"{100.0 * self.fn_frr / self.total_legitimate:.1f}% ({self.fn_frr} / {self.total_legitimate})"
        print(f"False-Rejection Rate (FRR): {frr_str}")
        
        # Review Rate: Total REVIEW / Total
        if self.total == 0:
            rr_str = "N/A"
        else:
            rr_str = f"{100.0 * self.total_review / self.total:.1f}% ({self.total_review} / {self.total})"
        print(f"Review Rate: {rr_str}")
        
        # Auto-Resolution Rate: (APPROVE + REJECT) / Total
        if self.total == 0:
            arr_str = "N/A"
        else:
            auto_res = self.total_approve + self.total_reject
            arr_str = f"{100.0 * auto_res / self.total:.1f}% ({auto_res} / {self.total})"
        print(f"Auto-Resolution Rate: {arr_str}")
        
        # Latency
        if self.total == 0:
            print("Average Latency: N/A")
        else:
            print(f"Average decision latency: {int(self.total_latency / self.total)} ms")

        print("\n--- CONFUSION MATRIX ---")
        print(f"{'':15} | APPROVE | REVIEW | REJECT")
        print("-" * 45)
        for gt in ["LEGITIMATE", "AMBIGUOUS", "ADVERSARIAL"]:
            counts = self.confusion_matrix[gt]
            print(f"{gt:15} | {counts['APPROVE']:7} | {counts['REVIEW']:6} | {counts['REJECT']:6}")

        print("\n--- EXCEPTION LIST ---")
        if not self.exceptions:
            print("No exceptions found.")
        else:
            for exc in self.exceptions:
                print(f"Case ID: {exc['case_id']}")
                print(f"  Ground Truth: {exc['ground_truth']}")
                print(f"  Predicted Decision: {exc['predicted']}")
                print(f"  Exception Reason: {exc['exception_reason']}")
                print(f"  Reason Codes: {exc['reason_codes']}")
                print()


def run_evaluation():
    db = SessionLocal()
    metrics = Metrics()
    
    cases = db.execute(text("SELECT eval_case_id, case_payload, ground_truth_label FROM evaluation_cases WHERE split = 'HELD_OUT'")).fetchall()
    
    for row in cases:
        payload = row.case_payload
        ground_truth = row.ground_truth_label
        
        if "case_id" not in payload:
            print(f"FAIL: Missing 'case_id' in payload for evaluation case {row.eval_case_id}")
            sys.exit(1)
            
        case_id = payload["case_id"]
        
        # 1. Reconstruct evidence
        start_time = time.perf_counter()
        
        try:
            bundle = aggregate_evidence(case_id, db)
        except Exception as e:
            print(f"FAIL: Error aggregating evidence for case {case_id}: {e}")
            sys.exit(1)
            
        # Reconstruct claims from cached payload
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
        
        # Run existing pipeline logic
        checks = check_claims(extracted_claims, bundle)
        coverage = calculate_evidence_coverage(bundle, checks)
        risk_score = compute_risk_score(bundle, checks)
        
        # Need amount_paise and prior_uses
        # bundle has refund_amount (which is actually paise in the db? the generator inserts random.randint(1000, 50000))
        # Wait, the generator inserted `amount` directly, assuming it's paise.
        case_row = db.execute(text("SELECT amount FROM refunds WHERE refund_id = (SELECT refund_id FROM refund_cases WHERE case_id = :cid)"), {"cid": case_id}).fetchone()
        amount_paise = case_row.amount if case_row else 0
        
        known_dest = bool(bundle.get("destination_prior_uses", 0) > 0) if bundle.get("destination_prior_uses") is not None else False
        
        decision, reasons = evaluate_policy(
            risk_score=risk_score,
            evidence_coverage=coverage,
            contradiction_results=checks,
            message_risk_flags=extracted_claims.message_risk_flags.model_dump(),
            amount_paise=amount_paise,
            known_destination=known_dest,
            amount_matches_original=bundle.get("amount_matches_original", False),
            risk_signals=bundle
        )
        
        end_time = time.perf_counter()
        latency_ms = int((end_time - start_time) * 1000)
        
        metrics.add_case(
            ground_truth=ground_truth,
            predicted=decision,
            latency_ms=latency_ms,
            case_id=case_id,
            reason_codes=reasons
        )
        
    metrics.print_report()
    db.close()


class TestMetrics(unittest.TestCase):
    def test_perfect_classification(self):
        m = Metrics()
        m.add_case("ADVERSARIAL", "REJECT", 10, "1", [])
        m.add_case("LEGITIMATE", "APPROVE", 10, "2", [])
        self.assertEqual(m.tp_precision, 1)
        self.assertEqual(m.tp_recall, 1)
        self.assertEqual(m.fp_far, 0)
        self.assertEqual(m.fn_frr, 0)
        
    def test_far_one_adversarial_approved(self):
        m = Metrics()
        m.add_case("ADVERSARIAL", "APPROVE", 10, "1", [])
        self.assertEqual(m.fp_far, 1)
        self.assertEqual(m.total, 1)
        
    def test_frr_one_legitimate_rejected(self):
        m = Metrics()
        m.add_case("LEGITIMATE", "REJECT", 10, "1", [])
        self.assertEqual(m.fn_frr, 1)
        self.assertEqual(m.total_legitimate, 1)
        
    def test_zero_reject_denominator_precision(self):
        m = Metrics()
        m.add_case("LEGITIMATE", "APPROVE", 10, "1", [])
        self.assertEqual(m.total_reject, 0) # precision should handle this without Exception
        
    def test_zero_adversarial_denominator_recall(self):
        m = Metrics()
        m.add_case("LEGITIMATE", "REJECT", 10, "1", [])
        self.assertEqual(m.total_adversarial, 0) # recall should handle this without Exception


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--test":
        sys.argv = [sys.argv[0]] # clean up args for unittest
        unittest.main()
    else:
        run_evaluation()
