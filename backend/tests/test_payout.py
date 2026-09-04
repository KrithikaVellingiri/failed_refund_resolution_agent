import unittest
import string
from unittest.mock import patch, MagicMock
from app.services.razorpay_client import (
    create_payout, 
    _generate_idempotency_key, 
    PayoutCapExceededError, 
    InvalidInputError, 
    RazorpayError
)

class TestPayout(unittest.TestCase):
    
    # --- Setup ---
    def setUp(self):
        from app.config import settings
        self.original_key = settings.RAZORPAY_KEY_ID
        self.original_secret = settings.RAZORPAY_KEY_SECRET
        self.original_account = settings.RAZORPAYX_ACCOUNT_NUMBER
        settings.RAZORPAY_KEY_ID = "mock_key"
        settings.RAZORPAY_KEY_SECRET = "mock_secret"
        settings.RAZORPAYX_ACCOUNT_NUMBER = "mock_account_number"
        
    def tearDown(self):
        from app.config import settings
        settings.RAZORPAY_KEY_ID = self.original_key
        settings.RAZORPAY_KEY_SECRET = self.original_secret
        settings.RAZORPAYX_ACCOUNT_NUMBER = self.original_account

    # --- A. Valid payout ---
    @patch('app.services.razorpay_client.requests.post')
    def test_valid_payout(self, mock_post):
        mock_response = MagicMock()
        mock_response.json.return_value = {"id": "pout_123"}
        mock_post.return_value = mock_response

        result = create_payout(
            case_id="case-456", 
            amount=500000, 
            fund_account_id="fa_123", 
            mode="UPI"
        )
        
        self.assertEqual(result, {"id": "pout_123"})
        mock_post.assert_called_once()
        
        # F. Verify payload and headers exactly
        args, kwargs = mock_post.call_args
        self.assertEqual(args[0], "https://api.razorpay.com/v1/payouts")
        self.assertIn("json", kwargs)
        self.assertEqual(kwargs["json"]["purpose"], "refund")
        self.assertEqual(kwargs["json"]["amount"], 500000)
        self.assertEqual(kwargs["json"]["fund_account_id"], "fa_123")
        self.assertEqual(kwargs["json"]["mode"], "UPI")
        self.assertEqual(kwargs["json"]["account_number"], "mock_account_number")
        self.assertIn("headers", kwargs)
        self.assertIn("X-Payout-Idempotency", kwargs["headers"])

    # --- B. Idempotency & G. Repeated attempts ---
    def test_idempotency_key_generation(self):
        key1 = _generate_idempotency_key("case-456")
        key2 = _generate_idempotency_key("case-456")
        key3 = _generate_idempotency_key("case-457")
        
        # Same case_id -> same key
        self.assertEqual(key1, key2)
        
        # Two different case_ids -> different keys
        self.assertNotEqual(key1, key3)
        
        # Generated key is 4-36 characters
        self.assertTrue(4 <= len(key1) <= 36)
        self.assertEqual(len(key1), 35) # "po-" + 32 chars
        
        # Generated key contains only permitted characters
        permitted = set(string.ascii_letters + string.digits + "-_ ")
        for char in key1:
            self.assertIn(char, permitted)

    def test_idempotency_key_long_case_ids(self):
        # Long case IDs do not cause truncation-based collisions
        long_id_a = "A" * 50 + "1"
        long_id_b = "A" * 50 + "2"
        
        key_a = _generate_idempotency_key(long_id_a)
        key_b = _generate_idempotency_key(long_id_b)
        
        self.assertNotEqual(key_a, key_b)
        self.assertEqual(len(key_a), 35)

    # --- C. Monetary cap ---
    @patch('app.services.razorpay_client.requests.post')
    def test_amount_exactly_10000_allowed(self, mock_post):
        mock_post.return_value.json.return_value = {"id": "pout_123"}
        # 1000000 paise = 10000 INR
        create_payout("case-123", 1000000, "fa_123", "UPI")
        mock_post.assert_called_once()
        
    @patch('app.services.razorpay_client.requests.post')
    def test_amount_above_10000_blocked(self, mock_post):
        with self.assertRaises(PayoutCapExceededError):
            create_payout("case-123", 1000001, "fa_123", "UPI")
        mock_post.assert_not_called()
        
    @patch('app.services.razorpay_client.requests.post')
    def test_amount_below_10000_allowed(self, mock_post):
        mock_post.return_value.json.return_value = {"id": "pout_123"}
        create_payout("case-123", 999999, "fa_123", "UPI")
        mock_post.assert_called_once()

    # --- D. Invalid input & Config ---
    @patch('app.services.razorpay_client.requests.post')
    def test_invalid_negative_amount_blocked(self, mock_post):
        with self.assertRaises(InvalidInputError):
            create_payout("case-123", -500, "fa_123", "UPI")
        mock_post.assert_not_called()

    @patch('app.services.razorpay_client.requests.post')
    def test_invalid_zero_amount_blocked(self, mock_post):
        with self.assertRaises(InvalidInputError):
            create_payout("case-123", 0, "fa_123", "UPI")
        mock_post.assert_not_called()

    @patch('app.services.razorpay_client.requests.post')
    def test_invalid_empty_case_id_blocked(self, mock_post):
        with self.assertRaises(InvalidInputError):
            create_payout("", 500, "fa_123", "UPI")
        mock_post.assert_not_called()

    @patch('app.services.razorpay_client.requests.post')
    def test_missing_account_number_blocked(self, mock_post):
        from app.config import settings
        settings.RAZORPAYX_ACCOUNT_NUMBER = None
        
        with self.assertRaises(ValueError) as context:
            create_payout("case-123", 500, "fa_123", "UPI")
            
        self.assertIn("account number is not configured", str(context.exception))
        mock_post.assert_not_called()

    # --- E. Razorpay failure ---
    @patch('app.services.razorpay_client.requests.post')
    def test_razorpay_api_failure_surfaced(self, mock_post):
        from requests.exceptions import HTTPError
        # Make the mock raise an HTTPError
        mock_response = MagicMock()
        mock_response.text = "Bad Request"
        mock_post.side_effect = HTTPError(response=mock_response)
        
        with self.assertRaises(RazorpayError):
            create_payout("case-123", 50000, "fa_123", "UPI")
            
    @patch('app.services.razorpay_client.requests.post')
    def test_razorpay_network_failure_surfaced(self, mock_post):
        from requests.exceptions import ConnectionError
        mock_post.side_effect = ConnectionError("Network down")
        
        with self.assertRaises(RazorpayError):
            create_payout("case-123", 50000, "fa_123", "UPI")
