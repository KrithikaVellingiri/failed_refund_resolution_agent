import unittest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
import json
import hmac
import hashlib
import time

from app.main import app
from app.config import settings
from app.db.database import get_db

class TestRazorpay(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        settings.RAZORPAY_WEBHOOK_SECRET = "test_secret"
        
        self.mock_db = MagicMock()
        
        # Override the dependency
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

    def test_webhook_missing_signature(self):
        payload = {"event": "refund.created"}
        response = self.client.post("/webhooks/razorpay", json=payload)
        self.assertEqual(response.status_code, 400)
        self.assertIn("Invalid webhook signature", response.json()["detail"])

    def test_webhook_invalid_signature(self):
        payload = {"event": "refund.created"}
        headers = {"x-razorpay-signature": "invalid_sig"}
        response = self.client.post("/webhooks/razorpay", json=payload, headers=headers)
        self.assertEqual(response.status_code, 400)

    def test_webhook_valid_signature_payment_not_found(self):
        payload = {
            "event": "refund.created",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_123",
                        "payment_id": "pay_123",
                        "amount": 1000,
                        "status": "pending"
                    }
                }
            }
        }
        sig = self._generate_signature(payload)
        
        # Mock payment not found
        mock_result = MagicMock()
        mock_result.scalar.return_value = None
        self.mock_db.execute.return_value = mock_result
        
        response = self.client.post(
            "/webhooks/razorpay", 
            content=json.dumps(payload, separators=(',', ':')).encode('utf-8'), 
            headers={"x-razorpay-signature": sig}
        )
        self.assertEqual(response.status_code, 404)

    def test_webhook_refund_created(self):
        payload = {
            "event": "refund.created",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_123",
                        "payment_id": "pay_123",
                        "amount": 1000,
                        "status": "pending"
                    }
                }
            }
        }
        sig = self._generate_signature(payload)
        
        # Mock payment found
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        self.mock_db.execute.return_value = mock_result
        
        response = self.client.post(
            "/webhooks/razorpay", 
            content=json.dumps(payload, separators=(',', ':')).encode('utf-8'), 
            headers={"x-razorpay-signature": sig}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"status": "success"})

    def test_webhook_refund_processed(self):
        payload = {
            "event": "refund.processed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_123",
                        "payment_id": "pay_123",
                        "amount": 1000,
                        "status": "processed"
                    }
                }
            }
        }
        sig = self._generate_signature(payload)
        
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        self.mock_db.execute.return_value = mock_result
        
        response = self.client.post(
            "/webhooks/razorpay", 
            content=json.dumps(payload, separators=(',', ':')).encode('utf-8'), 
            headers={"x-razorpay-signature": sig}
        )
        self.assertEqual(response.status_code, 200)

    def test_webhook_refund_failed_type_2_transition(self):
        payload = {
            "event": "refund.failed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_123",
                        "payment_id": "pay_123",
                        "amount": 1000,
                        "status": "failed",
                        "error_reason": "account_closed"
                    }
                }
            }
        }
        sig = self._generate_signature(payload)
        
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        self.mock_db.execute.return_value = mock_result
        
        response = self.client.post(
            "/webhooks/razorpay", 
            content=json.dumps(payload, separators=(',', ':')).encode('utf-8'), 
            headers={"x-razorpay-signature": sig}
        )
        self.assertEqual(response.status_code, 200)
        
        # Verify that it DID insert refund_cases and progressed to AWAITING_ALTERNATE
        execute_calls = self.mock_db.execute.call_args_list
        found_case_insert = any(
            len(call.args) > 0 and hasattr(call.args[0], 'text') and "INSERT INTO refund_cases" in call.args[0].text 
            for call in execute_calls
        )
        self.assertTrue(found_case_insert)
        
        found_awaiting_alt = any(
            len(call.args) > 0 and hasattr(call.args[0], 'text') and "SET state = 'AWAITING_ALTERNATE'" in call.args[0].text 
            for call in execute_calls
        )
        self.assertTrue(found_awaiting_alt)

    def test_webhook_refund_failed_type_1_matched_no_transition(self):
        payload = {
            "event": "refund.failed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_123",
                        "payment_id": "pay_123",
                        "amount": 1000,
                        "status": "failed",
                        "error_reason": "bank_processing_error"
                    }
                }
            }
        }
        sig = self._generate_signature(payload)
        
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        self.mock_db.execute.return_value = mock_result
        
        response = self.client.post(
            "/webhooks/razorpay", 
            content=json.dumps(payload, separators=(',', ':')).encode('utf-8'), 
            headers={"x-razorpay-signature": sig}
        )
        self.assertEqual(response.status_code, 200)
        
        execute_calls = self.mock_db.execute.call_args_list
        found_awaiting_alt = any(
            len(call.args) > 0 and hasattr(call.args[0], 'text') and "SET state = 'AWAITING_ALTERNATE'" in call.args[0].text 
            for call in execute_calls
        )
        self.assertFalse(found_awaiting_alt)

    def test_webhook_refund_failed_type_1_unrecognized_no_transition(self):
        payload = {
            "event": "refund.failed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_123",
                        "payment_id": "pay_123",
                        "amount": 1000,
                        "status": "failed",
                        "error_reason": "weird_error_123"
                    }
                }
            }
        }
        sig = self._generate_signature(payload)
        
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        self.mock_db.execute.return_value = mock_result
        
        response = self.client.post(
            "/webhooks/razorpay", 
            content=json.dumps(payload, separators=(',', ':')).encode('utf-8'), 
            headers={"x-razorpay-signature": sig}
        )
        self.assertEqual(response.status_code, 200)
        
        execute_calls = self.mock_db.execute.call_args_list
        found_awaiting_alt = any(
            len(call.args) > 0 and hasattr(call.args[0], 'text') and "SET state = 'AWAITING_ALTERNATE'" in call.args[0].text 
            for call in execute_calls
        )
        self.assertFalse(found_awaiting_alt)

    def test_webhook_refund_speed_changed(self):
        payload = {
            "event": "refund.speed_changed",
            "payload": {
                "refund": {
                    "entity": {
                        "id": "rfnd_123",
                        "payment_id": "pay_123",
                        "amount": 1000,
                        "status": "processed",
                        "speed_requested": "normal",
                        "speed_processed": "instant"
                    }
                }
            }
        }
        sig = self._generate_signature(payload)
        
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        self.mock_db.execute.return_value = mock_result
        
        response = self.client.post(
            "/webhooks/razorpay", 
            content=json.dumps(payload, separators=(',', ':')).encode('utf-8'), 
            headers={"x-razorpay-signature": sig}
        )
        self.assertEqual(response.status_code, 200)

    @patch('httpx.AsyncClient.post')
    def test_force_failure_harness(self, mock_post):
        req = {
            "payment_id": "pay_test",
            "refund_id": "rfnd_test",
            "amount": 5000
        }
        response = self.client.post("/harness/force_refund_failure", json=req)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["payment_id"], "pay_test")
        self.assertEqual(data["refund_id"], "rfnd_test")
        self.assertIn("signature", data)
        
        # Ensure that it explicitly creates the payment record first
        execute_calls = self.mock_db.execute.call_args_list
        found_payment_insert = any(
            len(call.args) > 0 and hasattr(call.args[0], 'text') and "INSERT INTO payments" in call.args[0].text 
            for call in execute_calls
        )
        self.assertTrue(found_payment_insert)

        # Verify background task fired an HTTP request
        self.assertTrue(mock_post.called)
        
        # Manually pass the captured payload to the webhook handler using TestClient
        # This properly tests the harness-to-webhook integration without needing a live server
        call_kwargs = mock_post.call_args.kwargs
        content = call_kwargs['content']
        headers = call_kwargs['headers']
        
        # Before calling webhook, mock that the payment exists
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        self.mock_db.execute.return_value = mock_result
        
        webhook_resp = self.client.post("/webhooks/razorpay", content=content, headers=headers)
        self.assertEqual(webhook_resp.status_code, 200)

    def test_get_refund(self):
        mock_result = MagicMock()
        mock_result.mappings().first.return_value = {
            "refund_id": "rfnd_123",
            "payment_id": "pay_123",
            "amount": 1000,
            "status": "failed",
            "failure_reason": "destination_unavailable"
        }
        self.mock_db.execute.return_value = mock_result
        
        response = self.client.get("/v1/refunds/rfnd_123")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "failed")

    def test_get_refund_not_found(self):
        mock_result = MagicMock()
        mock_result.mappings().first.return_value = None
        self.mock_db.execute.return_value = mock_result
        
        response = self.client.get("/v1/refunds/rfnd_999")
        self.assertEqual(response.status_code, 404)

    @patch('app.services.razorpay_client.requests.post')
    def test_refund_payment_success(self, mock_post):
        from app.services.razorpay_client import refund_payment
        settings.RAZORPAY_KEY_ID = "test_key"
        settings.RAZORPAY_KEY_SECRET = "test_secret"
        
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "rfnd_123", "status": "processed"}
        mock_post.return_value = mock_response
        
        result = refund_payment("pay_123", 5000)
        
        self.assertEqual(result, {"id": "rfnd_123", "status": "processed"})
        
        # Verify endpoint and method
        url = mock_post.call_args.args[0]
        self.assertEqual(url, "https://api.razorpay.com/v1/payments/pay_123/refund")
        
        # Verify payload and auth
        kwargs = mock_post.call_args.kwargs
        self.assertEqual(kwargs["json"], {"amount": 5000})
        self.assertEqual(kwargs["auth"].username, "test_key")
        self.assertEqual(kwargs["auth"].password, "test_secret")

    @patch('app.services.razorpay_client.requests.post')
    def test_refund_payment_error(self, mock_post):
        from app.services.razorpay_client import refund_payment, RazorpayError
        import requests
        
        settings.RAZORPAY_KEY_ID = "test_key"
        settings.RAZORPAY_KEY_SECRET = "test_secret"
        
        mock_err_response = MagicMock()
        mock_err_response.text = "Razorpay error details"
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.exceptions.HTTPError(response=mock_err_response)
        mock_post.return_value = mock_response
        
        with self.assertRaises(RazorpayError):
            refund_payment("pay_123", 5000)

if __name__ == '__main__':
    unittest.main()
