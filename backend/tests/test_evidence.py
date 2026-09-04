import unittest
from sqlalchemy import text
from app.db.database import SessionLocal
from app.services.evidence import aggregate_evidence
import uuid

class TestEvidenceAggregator(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.db = SessionLocal()
        
        # Create a base setup for evidence testing
        cls.customer_id_1 = str(uuid.uuid4())
        cls.db.execute(
            text("INSERT INTO customers (customer_id, name, email) VALUES (:id, 'Test User One', 'test1@synthetic.local')"),
            {"id": cls.customer_id_1}
        )
        
        cls.payment_id_1 = f"pay_evid_1_{cls.customer_id_1[:6]}"
        cls.db.execute(
            text("INSERT INTO payments (payment_id, customer_id, amount, currency, status) VALUES (:id, :cid, 1000, 'INR', 'captured')"),
            {"id": cls.payment_id_1, "cid": cls.customer_id_1}
        )
        
        cls.refund_id_1 = f"rfnd_evid_1_{cls.customer_id_1[:6]}"
        cls.db.execute(
            text("INSERT INTO refunds (refund_id, payment_id, amount, status, failure_reason) VALUES (:id, :pid, 1000, 'failed', 'account_closed')"),
            {"id": cls.refund_id_1, "pid": cls.payment_id_1}
        )
        
        cls.case_id_1 = cls.db.execute(
            text("""
                INSERT INTO refund_cases (refund_id, failure_type, classification_source, state)
                VALUES (:rid, 'TYPE_2_DESTINATION_UNAVAILABLE', 'MATCHED_RULE', 'AWAITING_ALTERNATE')
                RETURNING case_id
            """),
            {"rid": cls.refund_id_1}
        ).scalar()
        
        # Second customer for mismatch
        cls.customer_id_2 = str(uuid.uuid4())
        cls.db.execute(
            text("INSERT INTO customers (customer_id, name, email) VALUES (:id, 'Test User Two', 'test2@synthetic.local')"),
            {"id": cls.customer_id_2}
        )
        cls.payment_id_2 = f"pay_evid_2_{cls.customer_id_2[:6]}"
        cls.db.execute(text("INSERT INTO payments (payment_id, customer_id, amount, currency, status) VALUES (:id, :cid, 2000, 'INR', 'captured')"), {"id": cls.payment_id_2, "cid": cls.customer_id_2})
        cls.refund_id_2 = f"rfnd_evid_2_{cls.customer_id_2[:6]}"
        cls.db.execute(text("INSERT INTO refunds (refund_id, payment_id, amount, status, failure_reason) VALUES (:id, :pid, 2000, 'failed', 'account_closed')"), {"id": cls.refund_id_2, "pid": cls.payment_id_2})
        cls.case_id_2 = cls.db.execute(
            text("INSERT INTO refund_cases (refund_id, failure_type, classification_source, state) VALUES (:rid, 'TYPE_2_DESTINATION_UNAVAILABLE', 'MATCHED_RULE', 'AWAITING_ALTERNATE') RETURNING case_id"),
            {"rid": cls.refund_id_2}
        ).scalar()
        
        cls.db.commit()

    @classmethod
    def tearDownClass(cls):
        cls.db.execute(text(f"UPDATE refund_cases SET proposed_destination_id = NULL WHERE case_id IN ('{cls.case_id_1}', '{cls.case_id_2}')"))
        cls.db.execute(text(f"DELETE FROM alternate_destinations WHERE customer_id IN ('{cls.customer_id_1}', '{cls.customer_id_2}')"))
        cls.db.execute(text(f"DELETE FROM refund_cases WHERE case_id IN ('{cls.case_id_1}', '{cls.case_id_2}')"))
        cls.db.execute(text(f"DELETE FROM refunds WHERE refund_id IN ('{cls.refund_id_1}', '{cls.refund_id_2}')"))
        cls.db.execute(text(f"DELETE FROM payments WHERE payment_id IN ('{cls.payment_id_1}', '{cls.payment_id_2}')"))
        cls.db.execute(text(f"DELETE FROM customers WHERE customer_id IN ('{cls.customer_id_1}', '{cls.customer_id_2}')"))
        cls.db.commit()
        cls.db.close()

    def setUp(self):
        self.db.rollback()
        self.db.execute(text(f"UPDATE refund_cases SET proposed_destination_id = NULL WHERE case_id IN ('{self.case_id_1}', '{self.case_id_2}')"))
        self.db.execute(text(f"DELETE FROM alternate_destinations WHERE customer_id IN ('{self.customer_id_1}', '{self.customer_id_2}')"))
        self.db.commit()

    def test_missing_evidence(self):
        # No proposed destination attached
        bundle = aggregate_evidence(self.case_id_1, self.db)
        
        self.assertEqual(bundle["case_id"], str(self.case_id_1))
        self.assertIsNone(bundle["destination_age_days"])
        self.assertIsNone(bundle["destination_prior_uses"])
        self.assertEqual(bundle["redirect_count_30d"], 0)
        self.assertTrue(bundle["amount_matches_original"])
        self.assertIsNone(bundle["name_similarity_score"])
        self.assertEqual(bundle["ownership_signal"], "UNAVAILABLE")
        self.assertIsNone(bundle["message_risk_flags"])

    def test_complete_evidence_verified_synthetic(self):
        # Complete bundle with exact name match
        dest_id = str(uuid.uuid4())
        self.db.execute(
            text("""
                INSERT INTO alternate_destinations (destination_id, customer_id, type, identifier, holder_name, times_used, first_seen_at) 
                VALUES (:did, :cid, 'UPI', 'test@upi', 'Test User One', 5, NOW() - INTERVAL '10 days')
            """),
            {"did": dest_id, "cid": self.customer_id_1}
        )
        self.db.execute(
            text("UPDATE refund_cases SET proposed_destination_id = :did WHERE case_id = :case_id"),
            {"did": dest_id, "case_id": self.case_id_1}
        )
        self.db.commit()
        
        bundle = aggregate_evidence(self.case_id_1, self.db)
        
        self.assertEqual(bundle["case_id"], str(self.case_id_1))
        self.assertGreaterEqual(bundle["destination_age_days"], 9) # Allows for time delta
        self.assertEqual(bundle["destination_prior_uses"], 5) # Prior destination previously used
        self.assertEqual(bundle["redirect_count_30d"], 1)
        self.assertTrue(bundle["amount_matches_original"])
        self.assertEqual(bundle["name_similarity_score"], 1.0)
        self.assertEqual(bundle["ownership_signal"], "VERIFIED_SYNTHETIC") # Synthetic evidence/verification labeling
        
    def test_prior_destination_never_used(self):
        dest_id = str(uuid.uuid4())
        self.db.execute(
            text("""
                INSERT INTO alternate_destinations (destination_id, customer_id, type, identifier, holder_name, times_used) 
                VALUES (:did, :cid, 'UPI', 'test2@upi', 'Test User One', 0)
            """),
            {"did": dest_id, "cid": self.customer_id_1}
        )
        self.db.execute(text("UPDATE refund_cases SET proposed_destination_id = :did WHERE case_id = :case_id"), {"did": dest_id, "case_id": self.case_id_1})
        self.db.commit()
        
        bundle = aggregate_evidence(self.case_id_1, self.db)
        self.assertEqual(bundle["destination_prior_uses"], 0)
        
    def test_mismatch_synthetic_labeling(self):
        # Complete bundle with name mismatch
        dest_id = str(uuid.uuid4())
        self.db.execute(
            text("""
                INSERT INTO alternate_destinations (destination_id, customer_id, type, identifier, holder_name) 
                VALUES (:did, :cid, 'UPI', 'test@upi', 'Completely Different Name')
            """),
            {"did": dest_id, "cid": self.customer_id_2}
        )
        self.db.execute(text("UPDATE refund_cases SET proposed_destination_id = :did WHERE case_id = :case_id"), {"did": dest_id, "case_id": self.case_id_2})
        self.db.commit()
        
        bundle = aggregate_evidence(self.case_id_2, self.db)
        
        self.assertEqual(bundle["case_id"], str(self.case_id_2))
        self.assertLess(bundle["name_similarity_score"], 0.5)
        self.assertEqual(bundle["ownership_signal"], "MISMATCH_SYNTHETIC")

    def test_deterministic_output(self):
        # Test that running aggregator multiple times gives exact same dict
        dest_id = str(uuid.uuid4())
        self.db.execute(
            text("INSERT INTO alternate_destinations (destination_id, customer_id, type, identifier, holder_name) VALUES (:did, :cid, 'UPI', 'test@upi', 'Test User One')"),
            {"did": dest_id, "cid": self.customer_id_1}
        )
        self.db.execute(text("UPDATE refund_cases SET proposed_destination_id = :did WHERE case_id = :case_id"), {"did": dest_id, "case_id": self.case_id_1})
        self.db.commit()
        
        bundle_1 = aggregate_evidence(self.case_id_1, self.db)
        bundle_2 = aggregate_evidence(self.case_id_1, self.db)
        
        self.assertEqual(bundle_1, bundle_2)
