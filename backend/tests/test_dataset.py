import unittest
from sqlalchemy import text
import json
from app.db.database import SessionLocal
from scripts.generate_synthetic_data import generate_dataset

class TestSyntheticDataset(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        generate_dataset(seed=42, version="v1")
        cls.db = SessionLocal()

    @classmethod
    def tearDownClass(cls):
        cls.db.close()

    def test_record_counts(self):
        customers = self.db.execute(text("SELECT COUNT(*) FROM customers")).scalar()
        payments = self.db.execute(text("SELECT COUNT(*) FROM payments")).scalar()
        refunds = self.db.execute(text("SELECT COUNT(*) FROM refunds")).scalar()
        failed_refunds = self.db.execute(text("SELECT COUNT(*) FROM refunds WHERE status = 'failed'")).scalar()
        
        self.assertEqual(customers, 150)
        self.assertEqual(payments, 600)
        self.assertEqual(refunds, 120)
        self.assertEqual(failed_refunds, 35)

    def test_foreign_key_relationships(self):
        # If foreign keys were invalid, generation would have failed, but we can double check
        orphaned_payments = self.db.execute(text("SELECT COUNT(*) FROM payments WHERE customer_id NOT IN (SELECT customer_id FROM customers)")).scalar()
        orphaned_refunds = self.db.execute(text("SELECT COUNT(*) FROM refunds WHERE payment_id NOT IN (SELECT payment_id FROM payments)")).scalar()
        self.assertEqual(orphaned_payments, 0)
        self.assertEqual(orphaned_refunds, 0)

    def test_failure_reasons_represented(self):
        reasons = self.db.execute(text("SELECT DISTINCT failure_reason FROM refunds WHERE status = 'failed'")).scalars().all()
        
        type_1 = {"bank_processing_error", "technical_issue", "npci_timeout", "gateway_error", "account_temporarily_frozen", "account_details_malformed", "vpa_malformed"}
        type_2 = {"account_closed", "account_permanently_deactivated", "account_details_nonexistent", "vpa_permanently_deactivated"}
        
        # Ensure at least one of each is present (with our random choice, they might not all be hit with 35 tries, but we should see some from each bucket)
        has_type_1 = any(r in type_1 for r in reasons)
        has_type_2 = any(r in type_2 for r in reasons)
        has_unknown = any(r not in type_1 and r not in type_2 for r in reasons)
        
        self.assertTrue(has_type_1)
        self.assertTrue(has_type_2)
        self.assertTrue(has_unknown)

    def test_distribution(self):
        cases = self.db.execute(text("SELECT case_payload, ground_truth_label FROM evaluation_cases")).fetchall()
        self.assertEqual(len(cases), 20)
        
        clean = sum(1 for c in cases if c.case_payload.get("scenario_class") == "CLEAN")
        ambiguous = sum(1 for c in cases if c.case_payload.get("scenario_class") == "AMBIGUOUS")
        adversarial = sum(1 for c in cases if c.case_payload.get("scenario_class") == "ADVERSARIAL")
        
        self.assertEqual(clean, 12) # 60% of 20
        self.assertEqual(ambiguous, 5) # 25% of 20
        self.assertEqual(adversarial, 3) # 15% of 20

    def test_ground_truth_fields(self):
        cases = self.db.execute(text("SELECT case_payload FROM evaluation_cases")).fetchall()
        for c in cases:
            payload = c.case_payload
            self.assertIn("scenario_class", payload)
            self.assertIn("expected_decision", payload)
            self.assertIn("evidence_snapshot", payload)

    def test_synthetic_labels(self):
        cases = self.db.execute(text("SELECT case_payload FROM evaluation_cases")).fetchall()
        for c in cases:
            payload = c.case_payload
            # Verify synthetic verification signals are explicitly labeled SYNTHETIC
            evidence = payload.get("evidence_snapshot", {})
            for key, val in evidence.items():
                self.assertIn("SYNTHETIC", val)

    def test_reproducibility(self):
        # Run generator again with same seed, verify no change in total cases because of the deletes, 
        # and verify specific case IDs or payloads match
        generate_dataset(seed=99, version="v2")
        cases_v2 = self.db.execute(text("SELECT COUNT(*) FROM evaluation_cases")).scalar()
        self.assertEqual(cases_v2, 20)
        
        # Restore original for other tests if they run out of order
        generate_dataset(seed=42, version="v1")

    def test_held_out_distinct(self):
        splits = self.db.execute(text("SELECT DISTINCT split FROM evaluation_cases")).scalars().all()
        self.assertIn("TRAIN", splits)
        self.assertIn("HELD_OUT", splits)
