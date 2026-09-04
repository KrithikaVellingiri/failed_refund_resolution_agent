import unittest
from app.services.evidence_coverage import calculate_evidence_coverage

class TestEvidenceCoverage(unittest.TestCase):
    def test_all_signals_available(self):
        bundle = {
            "ownership_signal": "VERIFIED_SYNTHETIC",
            "destination_prior_uses": 3,
            "destination_age_days": 120
        }
        claim_checks = [{"claim": "example", "status": "CONSISTENT"}]
        coverage = calculate_evidence_coverage(bundle, claim_checks)
        self.assertEqual(coverage, 100.0)

    def test_three_signals_available(self):
        bundle = {
            "ownership_signal": "UNAVAILABLE",  # Missing
            "destination_prior_uses": 3,
            "destination_age_days": 120
        }
        claim_checks = [{"claim": "example", "status": "CONSISTENT"}]
        coverage = calculate_evidence_coverage(bundle, claim_checks)
        self.assertEqual(coverage, 75.0)

    def test_two_signals_available(self):
        bundle = {
            "ownership_signal": "UNAVAILABLE",  # Missing
            "destination_prior_uses": None,     # Missing
            "destination_age_days": 120
        }
        claim_checks = [{"claim": "example", "status": "CONSISTENT"}]
        coverage = calculate_evidence_coverage(bundle, claim_checks)
        self.assertEqual(coverage, 50.0)

    def test_one_signal_available(self):
        bundle = {
            "ownership_signal": "UNAVAILABLE",  # Missing
            "destination_prior_uses": None,     # Missing
            "destination_age_days": None        # Missing
        }
        claim_checks = [{"claim": "example", "status": "CONSISTENT"}]
        coverage = calculate_evidence_coverage(bundle, claim_checks)
        self.assertEqual(coverage, 25.0)

    def test_zero_signals_available(self):
        bundle = {
            "ownership_signal": "UNAVAILABLE",  # Missing
            "destination_prior_uses": None,     # Missing
            "destination_age_days": None        # Missing
        }
        claim_checks = []  # Missing
        coverage = calculate_evidence_coverage(bundle, claim_checks)
        self.assertEqual(coverage, 0.0)

    def test_unverifiable_checks_do_not_reduce_coverage(self):
        # A claim check exists, even if the status is UNVERIFIABLE.
        # This means we *have* the claim signal itself, it just didn't verify.
        bundle = {
            "ownership_signal": "MISMATCH_SYNTHETIC",
            "destination_prior_uses": 0,
            "destination_age_days": 10
        }
        claim_checks = [{"claim": "urgency", "status": "UNVERIFIABLE"}]
        coverage = calculate_evidence_coverage(bundle, claim_checks)
        self.assertEqual(coverage, 100.0)

    def test_contradictory_checks_do_not_reduce_coverage(self):
        # A claim check exists, even if the status is CONTRADICTED.
        # The completeness of evidence is still 100%.
        bundle = {
            "ownership_signal": "VERIFIED_SYNTHETIC",
            "destination_prior_uses": 0,
            "destination_age_days": 10
        }
        claim_checks = [{"claim": "prior_usage", "status": "CONTRADICTED"}]
        coverage = calculate_evidence_coverage(bundle, claim_checks)
        self.assertEqual(coverage, 100.0)

    def test_deterministic_repeated_calculation(self):
        bundle = {
            "ownership_signal": "VERIFIED_SYNTHETIC",
            "destination_prior_uses": 0,
            "destination_age_days": 10
        }
        claim_checks = [{"claim": "prior_usage", "status": "CONTRADICTED"}]
        cov1 = calculate_evidence_coverage(bundle, claim_checks)
        cov2 = calculate_evidence_coverage(bundle, claim_checks)
        self.assertEqual(cov1, cov2)
        self.assertEqual(cov1, 100.0)
