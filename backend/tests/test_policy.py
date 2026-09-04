import unittest
from app.services.policy import compute_risk_score, evaluate_policy

class TestPolicyAndRisk(unittest.TestCase):
    
    # --- RISK SCORE TESTS ---

    def test_zero_risk_baseline(self):
        signals = {}
        contradictions = []
        score = compute_risk_score(signals, contradictions)
        self.assertEqual(score, 0.0)

    def test_name_mismatch_contribution(self):
        signals = {"name_similarity_score": 0.8} # 10 * (1 - 0.8) = 2.0
        score = compute_risk_score(signals, [])
        self.assertAlmostEqual(score, 2.0)
        
    def test_maximum_name_contribution(self):
        signals = {"name_similarity_score": 0.0} # 10 * (1 - 0) = 10.0
        score = compute_risk_score(signals, [])
        self.assertEqual(score, 10.0)

    def test_redirect_threshold_boundary(self):
        # redirect_count_30d > 1 is threshold
        score_1 = compute_risk_score({"redirect_count_30d": 1}, [])
        self.assertEqual(score_1, 0.0)
        
        score_2 = compute_risk_score({"redirect_count_30d": 2}, [])
        self.assertEqual(score_2, 20.0)

    def test_novelty_threshold_boundary(self):
        # age < 7 is novel
        score_7 = compute_risk_score({"destination_age_days": 7}, [])
        self.assertEqual(score_7, 0.0)
        
        score_6 = compute_risk_score({"destination_age_days": 6}, [])
        self.assertEqual(score_6, 15.0)

    def test_high_contradiction(self):
        contradictions = [{"status": "CONTRADICTED", "severity": "HIGH"}]
        score = compute_risk_score({}, contradictions)
        self.assertEqual(score, 40.0)

    def test_medium_contradiction(self):
        contradictions = [{"status": "CONTRADICTED", "severity": "MEDIUM"}]
        score = compute_risk_score({}, contradictions)
        self.assertEqual(score, 20.0)

    def test_low_contradiction(self):
        contradictions = [{"status": "CONTRADICTED", "severity": "LOW"}]
        score = compute_risk_score({}, contradictions)
        self.assertEqual(score, 10.0)

    def test_multiple_contradictions(self):
        contradictions = [
            {"status": "CONTRADICTED", "severity": "HIGH"},
            {"status": "CONTRADICTED", "severity": "MEDIUM"}
        ]
        score = compute_risk_score({}, contradictions)
        self.assertEqual(score, 60.0)

    def test_contradiction_cap_at_80(self):
        contradictions = [
            {"status": "CONTRADICTED", "severity": "HIGH"},
            {"status": "CONTRADICTED", "severity": "HIGH"},
            {"status": "CONTRADICTED", "severity": "HIGH"}
        ] # 3 * 40 = 120, capped at 80
        score = compute_risk_score({}, contradictions)
        self.assertEqual(score, 80.0)

    def test_urgency_flag(self):
        signals = {"message_risk_flags": {"urgency_language": True}}
        score = compute_risk_score(signals, [])
        self.assertEqual(score, 15.0)

    def test_third_party_flag(self):
        signals = {"message_risk_flags": {"third_party_destination": True}}
        score = compute_risk_score(signals, [])
        self.assertEqual(score, 15.0)

    def test_both_llm_flags(self):
        signals = {"message_risk_flags": {"urgency_language": True, "third_party_destination": True}}
        score = compute_risk_score(signals, [])
        self.assertEqual(score, 30.0)

    def test_unknown_llm_flags_ignored(self):
        signals = {"message_risk_flags": {"unknown_flag": True}}
        score = compute_risk_score(signals, [])
        self.assertEqual(score, 0.0)

    def test_score_clamped_at_100(self):
        signals = {
            "name_similarity_score": 0.0,      # 10
            "redirect_count_30d": 5,           # 20
            "destination_age_days": 1,         # 15
            "message_risk_flags": {"urgency_language": True, "third_party_destination": True} # 30
        } # Subtotal 75
        contradictions = [{"status": "CONTRADICTED", "severity": "HIGH"}] # +40 -> 115
        score = compute_risk_score(signals, contradictions)
        self.assertEqual(score, 100.0)

    def test_missing_evidence_does_not_become_contradiction(self):
        # A claim check exists but is UNVERIFIABLE due to missing evidence
        contradictions = [{"status": "UNVERIFIABLE"}]
        score = compute_risk_score({}, contradictions)
        self.assertEqual(score, 0.0)
        
    def test_deterministic_repeated_calculation(self):
        signals = {"redirect_count_30d": 5}
        score_1 = compute_risk_score(signals, [])
        score_2 = compute_risk_score(signals, [])
        self.assertEqual(score_1, score_2)

    # --- POLICY TESTS ---
    def get_base_args(self):
        return {
            "risk_score": 0.0,
            "evidence_coverage": 100.0,
            "contradiction_results": [],
            "message_risk_flags": {},
            "amount_paise": 500000, # ₹5,000 (Below 10k)
            "known_destination": True,
            "amount_matches_original": True,
            "risk_signals": {}
        }

    def test_score_0_all_approval_conditions_approve(self):
        args = self.get_base_args()
        decision, reasons = evaluate_policy(**args)
        self.assertEqual(decision, "APPROVE")
        self.assertIn("KNOWN_DESTINATION", reasons)
        self.assertIn("AMOUNT_MATCH", reasons)
        self.assertIn("EVIDENCE_SUFFICIENT", reasons)

    def test_score_30_all_approval_conditions_approve(self):
        args = self.get_base_args()
        args["risk_score"] = 30.0
        decision, reasons = evaluate_policy(**args)
        self.assertEqual(decision, "APPROVE")

    def test_score_31_review(self):
        args = self.get_base_args()
        args["risk_score"] = 31.0
        decision, reasons = evaluate_policy(**args)
        self.assertEqual(decision, "REVIEW")

    def test_score_70_review(self):
        args = self.get_base_args()
        args["risk_score"] = 70.0
        decision, reasons = evaluate_policy(**args)
        self.assertEqual(decision, "REVIEW")

    def test_score_71_reject(self):
        args = self.get_base_args()
        args["risk_score"] = 71.0
        decision, reasons = evaluate_policy(**args)
        self.assertEqual(decision, "REJECT")

    def test_name_below_floor_reject(self):
        args = self.get_base_args()
        args["risk_signals"]["name_similarity_score"] = 0.4 # below 0.5
        decision, reasons = evaluate_policy(**args)
        self.assertEqual(decision, "REJECT")
        self.assertIn("NAME_MISMATCH_BELOW_FLOOR", reasons)

    def test_redirect_over_threshold_reject(self):
        args = self.get_base_args()
        args["risk_signals"]["redirect_count_30d"] = 2
        decision, reasons = evaluate_policy(**args)
        self.assertEqual(decision, "REJECT")
        self.assertIn("REDIRECT_VELOCITY_HIGH", reasons)

    def test_amount_above_10000_review(self):
        args = self.get_base_args()
        args["amount_paise"] = 1000001
        decision, reasons = evaluate_policy(**args)
        self.assertEqual(decision, "REVIEW")
        self.assertIn("OVER_AUTO_APPROVAL_LIMIT", reasons)

    def test_insufficient_evidence_review(self):
        args = self.get_base_args()
        args["evidence_coverage"] = 25.0
        decision, reasons = evaluate_policy(**args)
        self.assertEqual(decision, "REVIEW")
        self.assertIn("INSUFFICIENT_EVIDENCE", reasons)

    def test_any_llm_flag_review(self):
        args = self.get_base_args()
        args["message_risk_flags"] = {"urgency_language": True}
        decision, reasons = evaluate_policy(**args)
        self.assertEqual(decision, "REVIEW")
        self.assertIn("LLM_MESSAGE_RISK", reasons)

    def test_avoid_verified_channel_review_0_points(self):
        # 0 points
        score = compute_risk_score({"message_risk_flags": {"avoid_verified_channel": True}}, [])
        self.assertEqual(score, 0.0)
        # Causes REVIEW
        args = self.get_base_args()
        args["message_risk_flags"] = {"avoid_verified_channel": True}
        decision, reasons = evaluate_policy(**args)
        self.assertEqual(decision, "REVIEW")
        self.assertIn("LLM_MESSAGE_RISK", reasons)

    def test_instruction_manipulation_review_0_points(self):
        # 0 points
        score = compute_risk_score({"message_risk_flags": {"instruction_manipulation": True}}, [])
        self.assertEqual(score, 0.0)
        # Causes REVIEW
        args = self.get_base_args()
        args["message_risk_flags"] = {"instruction_manipulation": True}
        decision, reasons = evaluate_policy(**args)
        self.assertEqual(decision, "REVIEW")
        self.assertIn("LLM_MESSAGE_RISK", reasons)

    def test_novel_destination_review(self):
        args = self.get_base_args()
        args["risk_signals"]["destination_age_days"] = 2
        decision, reasons = evaluate_policy(**args)
        self.assertEqual(decision, "REVIEW")
        self.assertIn("NEW_DESTINATION", reasons)

    def test_amount_mismatch_review(self):
        args = self.get_base_args()
        args["amount_matches_original"] = False
        decision, reasons = evaluate_policy(**args)
        self.assertEqual(decision, "REVIEW")
        self.assertIn("AMOUNT_MISMATCH", reasons)

    def test_unknown_optional_evidence_fails_safely(self):
        args = self.get_base_args()
        args["risk_signals"] = {}
        decision, reasons = evaluate_policy(**args)
        # known_destination is True, everything else is fine -> APPROVE
        self.assertEqual(decision, "APPROVE")

    def test_no_reason_code_claims_unavailable_evidence(self):
        args = self.get_base_args()
        args["risk_score"] = 100.0 # Force reject
        decision, reasons = evaluate_policy(**args)
        
        invalid_reasons = ["ACCOUNT_CLOSED_VERIFIED", "ACCOUNT_STATUS_ACTIVE", "BANK_ACCOUNT_VERIFIED", "DUPLICATE_RISK_UNRESOLVED"]
        for r in invalid_reasons:
            self.assertNotIn(r, reasons)

    def test_policy_is_pure_deterministic(self):
        args = self.get_base_args()
        d1, r1 = evaluate_policy(**args)
        d2, r2 = evaluate_policy(**args)
        self.assertEqual(d1, d2)
        self.assertEqual(sorted(r1), sorted(r2))

