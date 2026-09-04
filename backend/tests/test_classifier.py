import unittest
from app.services.classifier import classify_refund_failure, FailureType, ClassificationSource

class TestClassifier(unittest.TestCase):
    def test_type_1_reasons(self):
        """Test that all exact Type 1 reasons map to TYPE_1_TECHNICAL + MATCHED_RULE."""
        type_1_reasons = ["bank_processing_error", "technical_issue", "npci_timeout", "gateway_error", "account_temporarily_frozen", "account_details_malformed", "vpa_malformed"]
        for reason in type_1_reasons:
            with self.subTest(reason=reason):
                self.assertEqual(
                    classify_refund_failure(reason, None),
                    (FailureType.TYPE_1_TECHNICAL, ClassificationSource.MATCHED_RULE)
                )

    def test_type_2_reasons(self):
        """Test that all exact Type 2 reasons map to TYPE_2_DESTINATION_UNAVAILABLE + MATCHED_RULE."""
        type_2_reasons = ["account_closed", "account_permanently_deactivated", "account_details_nonexistent", "vpa_permanently_deactivated"]
        for reason in type_2_reasons:
            with self.subTest(reason=reason):
                self.assertEqual(
                    classify_refund_failure(reason, None),
                    (FailureType.TYPE_2_DESTINATION_UNAVAILABLE, ClassificationSource.MATCHED_RULE)
                )

    def test_description_matching(self):
        """Test that description matching correctly identifies Type 1/Type 2 when reason code is unknown."""
        test_cases = [
            ("unknown", "Customer account closed.", (FailureType.TYPE_2_DESTINATION_UNAVAILABLE, ClassificationSource.MATCHED_RULE)),
            ("unknown", "The account is permanently deactivated.", (FailureType.TYPE_2_DESTINATION_UNAVAILABLE, ClassificationSource.MATCHED_RULE)),
            (None, "account_details_nonexistent", (FailureType.TYPE_2_DESTINATION_UNAVAILABLE, ClassificationSource.MATCHED_RULE)),
            ("unknown", "gateway error occurred", (FailureType.TYPE_1_TECHNICAL, ClassificationSource.MATCHED_RULE)),
            ("unknown", "Just some random description", (FailureType.TYPE_1_TECHNICAL, ClassificationSource.UNRECOGNIZED_DEFAULTED))
        ]
        
        for reason, desc, expected in test_cases:
            with self.subTest(reason=reason, desc=desc):
                self.assertEqual(
                    classify_refund_failure(reason, desc),
                    expected
                )

    def test_unknown_reason_fails_safely_to_type_1_unrecognized(self):
        """Test that unknown/unmapped reasons fail safely to Type 1 + UNRECOGNIZED_DEFAULTED."""
        unknown_reasons = ["alien_abduction", "weird_error_123", "", None]
        for reason in unknown_reasons:
            with self.subTest(reason=reason):
                self.assertEqual(
                    classify_refund_failure(reason, None),
                    (FailureType.TYPE_1_TECHNICAL, ClassificationSource.UNRECOGNIZED_DEFAULTED)
                )
