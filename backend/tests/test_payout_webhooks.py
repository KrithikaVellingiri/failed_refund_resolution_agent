import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import json
import hmac
import hashlib

from app.main import app
from app.config import settings
from app.db.database import get_db

class TestPayoutWebhooks(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        settings.RAZORPAY_WEBHOOK_SECRET = "test_secret"
        
        self.mock_db = MagicMock()
        app.dependency_overrides[get_db] = lambda: self.mock_db

    def tearDown(self):
        app.dependency_overrides.clear()

    def _generate_signature(self, payload: dict) -> str:
        raw_body = json.dumps(payload, separators=(',', ':')).encode('utf-8')
        return hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode('utf-8'),
            raw_body,
            hashlib.sha256
        ).hexdigest()

    def _create_payload(self, event: str, status: str, payout_id: str = "pout_123"):
        return {
            "event": event,
            "payload": {
                "payout": {
                    "entity": {
                        "id": payout_id,
                        "status": status
                    }
                }
            }
        }

    def _setup_mock_db_row(self, case_state="PAYOUT_PENDING", payout_status="processing"):
        mock_result = MagicMock()
        mock_result.mappings().first.return_value = {
            "case_id": "case_123",
            "current_case_state": case_state,
            "current_payout_status": payout_status
        }
        self.mock_db.execute.return_value = mock_result

    def test_payout_processed(self):
        self._setup_mock_db_row()
        payload = self._create_payload("pout_123", "processed")
        payload["event"] = "payout.processed"
        
        sig = self._generate_signature(payload)
        headers = {"x-razorpay-signature": sig}
        
        response = self.client.post("/webhooks/razorpay", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        
        # Verify db calls
        # 1. SELECT FOR UPDATE
        # 2. UPDATE payouts
        # 3. UPDATE refund_cases -> RESOLVED
        # 4. INSERT audit_events
        # 5. COMMIT
        self.assertTrue(self.mock_db.commit.called)
        
        updates = [call.args[0].text for call in self.mock_db.execute.call_args_list]
        self.assertTrue(any("UPDATE payouts SET status = :status" in q for q in updates))
        self.assertTrue(any("UPDATE refund_cases SET state = 'RESOLVED'" in q for q in updates))
        self.assertTrue(any("INSERT INTO audit_events" in q for q in updates))

    def test_payout_failed(self):
        self._setup_mock_db_row()
        payload = self._create_payload("payout.failed", "failed")
        
        sig = self._generate_signature(payload)
        headers = {"x-razorpay-signature": sig}
        
        response = self.client.post("/webhooks/razorpay", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        
        updates = [call.args[0].text for call in self.mock_db.execute.call_args_list]
        self.assertTrue(any("UPDATE payouts SET status = :status" in q for q in updates))
        self.assertTrue(any("UPDATE refund_cases SET state = 'PAYOUT_FAILED'" in q for q in updates))

    def test_payout_reversed(self):
        self._setup_mock_db_row()
        payload = self._create_payload("payout.reversed", "reversed")
        
        sig = self._generate_signature(payload)
        headers = {"x-razorpay-signature": sig}
        
        response = self.client.post("/webhooks/razorpay", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        
        updates = [call.args[0].text for call in self.mock_db.execute.call_args_list]
        self.assertTrue(any("UPDATE payouts SET status = :status" in q for q in updates))
        self.assertTrue(any("UPDATE refund_cases SET state = 'PAYOUT_FAILED'" in q for q in updates))

    def test_payout_idempotency(self):
        # Setup mock to return that the payout is already processed
        self._setup_mock_db_row(case_state="RESOLVED", payout_status="processed")
        payload = self._create_payload("payout.processed", "processed")
        
        sig = self._generate_signature(payload)
        headers = {"x-razorpay-signature": sig}
        
        response = self.client.post("/webhooks/razorpay", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "success")
        self.assertEqual(response.json()["note"], "idempotent")
        
        # Ensure no updates were run
        updates = [call.args[0].text for call in self.mock_db.execute.call_args_list]
        self.assertFalse(any("UPDATE payouts SET status" in q for q in updates))
        self.assertTrue(self.mock_db.commit.called)

    def test_payout_unknown_id(self):
        # Setup mock to return None (unknown payout)
        mock_result = MagicMock()
        mock_result.mappings().first.return_value = None
        self.mock_db.execute.return_value = mock_result
        
        payload = self._create_payload("payout.processed", "processed")
        sig = self._generate_signature(payload)
        headers = {"x-razorpay-signature": sig}
        
        response = self.client.post("/webhooks/razorpay", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ignored")
        self.assertEqual(response.json()["reason"], "unknown payout_id")
        
        # Ensure no DB commit or updates
        self.assertFalse(self.mock_db.commit.called)

    def test_payout_invalid_state(self):
        # Setup mock where case is in an invalid state (e.g. APPROVED instead of PAYOUT_PENDING)
        self._setup_mock_db_row(case_state="APPROVED", payout_status="processing")
        payload = self._create_payload("payout.processed", "processed")
        
        sig = self._generate_signature(payload)
        headers = {"x-razorpay-signature": sig}
        
        response = self.client.post("/webhooks/razorpay", json=payload, headers=headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ignored")
        self.assertEqual(response.json()["reason"], "case state is APPROVED")
        
        # Ensure commit was called to release lock, but no updates
        self.assertTrue(self.mock_db.commit.called)
        updates = [call.args[0].text for call in self.mock_db.execute.call_args_list]
        self.assertFalse(any("UPDATE payouts SET status" in q for q in updates))

if __name__ == '__main__':
    unittest.main()
