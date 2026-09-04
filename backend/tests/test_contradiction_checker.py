import unittest
from app.services.contradiction_checker import check_claims
from app.services.llm_client import ExtractedClaims, Claim, MessageRiskFlags

class TestContradictionChecker(unittest.TestCase):
    def setUp(self):
        self.flags = MessageRiskFlags(
            urgency_language=False,
            third_party_destination=False,
            avoid_verified_channel=False,
            instruction_manipulation=False
        )

    def test_account_closed_unverifiable(self):
        """
        The canonical "closed-account claim vs ACTIVE status" test.
        Since authoritative 'account_status' is NOT actually available 
        in the current evidence bundle (Task 6) or schema, we cannot deterministically
        contradict this claim without inventing evidence.
        Therefore, it correctly falls back to UNVERIFIABLE.
        """
        extracted = ExtractedClaims(
            claims=[Claim(claim_text="my old account was closed", claim_type="account_closed", confidence=0.9)],
            message_risk_flags=self.flags
        )
        bundle = {} # missing account_status natively
        
        checks = check_claims(extracted, bundle)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["status"], "UNVERIFIABLE")
        self.assertIn("missing", checks[0]["evidence"])

    def test_prior_usage_consistent(self):
        extracted = ExtractedClaims(
            claims=[Claim(claim_text="I used this before", claim_type="prior_usage", confidence=0.9)],
            message_risk_flags=self.flags
        )
        bundle = {"destination_prior_uses": 3}
        
        checks = check_claims(extracted, bundle)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["status"], "CONSISTENT")
        self.assertEqual(checks[0]["evidence"], "destination usage count = 3")

    def test_prior_usage_contradicted(self):
        extracted = ExtractedClaims(
            claims=[Claim(claim_text="I used this before", claim_type="prior_usage", confidence=0.9)],
            message_risk_flags=self.flags
        )
        bundle = {"destination_prior_uses": 0}
        
        checks = check_claims(extracted, bundle)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["status"], "CONTRADICTED")
        self.assertEqual(checks[0]["evidence"], "destination usage count = 0")

    def test_prior_usage_missing_evidence(self):
        extracted = ExtractedClaims(
            claims=[Claim(claim_text="I used this before", claim_type="prior_usage", confidence=0.9)],
            message_risk_flags=self.flags
        )
        bundle = {"destination_prior_uses": None}
        
        checks = check_claims(extracted, bundle)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["status"], "UNVERIFIABLE")

    def test_multiple_claims(self):
        extracted = ExtractedClaims(
            claims=[
                Claim(claim_text="I used this before", claim_type="prior_usage", confidence=0.9),
                Claim(claim_text="my old account was closed", claim_type="account_closed", confidence=0.9)
            ],
            message_risk_flags=self.flags
        )
        bundle = {"destination_prior_uses": 0} # Native bundle without account_status
        
        checks = check_claims(extracted, bundle)
        self.assertEqual(len(checks), 2)
        
        # Checking first claim
        self.assertEqual(checks[0]["claim"], "I used this before")
        self.assertEqual(checks[0]["status"], "CONTRADICTED")
        
        # Checking second claim
        self.assertEqual(checks[1]["claim"], "my old account was closed")
        self.assertEqual(checks[1]["status"], "UNVERIFIABLE")

    def test_unsupported_claim_type(self):
        extracted = ExtractedClaims(
            claims=[Claim(claim_text="I need this now", claim_type="urgency", confidence=0.9)],
            message_risk_flags=self.flags
        )
        bundle = {}
        
        checks = check_claims(extracted, bundle)
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0]["status"], "UNVERIFIABLE")

    def test_identical_input_produces_identical_output(self):
        extracted = ExtractedClaims(
            claims=[Claim(claim_text="my old account was closed", claim_type="account_closed", confidence=0.9)],
            message_risk_flags=self.flags
        )
        bundle = {} # Empty native bundle
        
        checks1 = check_claims(extracted, bundle)
        checks2 = check_claims(extracted, bundle)
        self.assertEqual(checks1, checks2)
