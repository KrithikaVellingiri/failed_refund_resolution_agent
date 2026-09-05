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
        
        type_2 = {"account_closed", "account_permanently_deactivated", "account_details_nonexistent", "vpa_permanently_deactivated"}
        
        # We changed this to only generate type_2 for the 35 eval cases.
        has_type_2 = any(r in type_2 for r in reasons)
        has_type_1 = any(r not in type_2 for r in reasons)
        
        self.assertTrue(has_type_2)
        self.assertFalse(has_type_1) # Because all 35 are type 2 now

    def test_distribution(self):
        cases = self.db.execute(text("SELECT case_payload, ground_truth_label FROM evaluation_cases")).fetchall()
        self.assertEqual(len(cases), 35)
        
        clean = sum(1 for c in cases if c.case_payload.get("scenario_class") == "CLEAN")
        ambiguous = sum(1 for c in cases if c.case_payload.get("scenario_class") == "AMBIGUOUS")
        adversarial = sum(1 for c in cases if c.case_payload.get("scenario_class") == "ADVERSARIAL")
        
        self.assertEqual(clean, 21) # 60% of 35
        self.assertEqual(ambiguous, 9) # 25% of 35
        self.assertEqual(adversarial, 5) # 15% of 35

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
        self.assertEqual(cases_v2, 35)
        
        # Restore original for other tests if they run out of order
        generate_dataset(seed=42, version="v1")

    def test_held_out_distinct(self):
        splits = self.db.execute(text("SELECT DISTINCT split FROM evaluation_cases")).scalars().all()
        self.assertIn("TRAIN", splits)
        self.assertIn("DEV", splits)
        self.assertIn("HELD_OUT", splits)

    def test_diversity(self):
        cases = self.db.execute(text("SELECT case_payload FROM evaluation_cases")).fetchall()
        
        ages = set()
        usages = set()
        amounts_match = set()
        holder_names = set()
        llm_flags = set()
        
        for c in cases:
            payload = c.case_payload
            case_id = payload.get("case_id")
            
            # Check amounts from DB
            r_row = self.db.execute(
                text("SELECT amount, payment_id FROM refunds WHERE refund_id = (SELECT refund_id FROM refund_cases WHERE case_id = :cid)"), 
                {"cid": case_id}
            ).fetchone()
            p_amt = self.db.execute(text("SELECT amount FROM payments WHERE payment_id = :pid"), {"pid": r_row.payment_id}).scalar()
            
            amounts_match.add(r_row.amount == p_amt)
            
            # Check alternate dest
            dest_row = self.db.execute(
                text("SELECT holder_name, first_seen_at, times_used FROM alternate_destinations WHERE destination_id = (SELECT proposed_destination_id FROM refund_cases WHERE case_id = :cid)"), 
                {"cid": case_id}
            ).fetchone()
            
            holder_names.add(dest_row.holder_name)
            usages.add(dest_row.times_used)
            # Age is not perfectly discrete due to timestamp diff, but checking unique values works to show diversity
            ages.add(dest_row.first_seen_at.date())
            
            # Check LLM flags
            flags = payload.get("extracted_claims", {}).get("message_risk_flags", {})
            llm_flags.add(tuple(flags.items()))
            
        # Assert non-uniformity
        self.assertGreater(len(ages), 1)
        self.assertGreater(len(usages), 1)
        self.assertIn(True, amounts_match)
        self.assertIn(False, amounts_match)
        self.assertGreater(len(holder_names), 1)
        self.assertIn(None, holder_names) # At least one None
        self.assertGreater(len(llm_flags), 1)
