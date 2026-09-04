import unittest
from unittest.mock import patch, MagicMock
from app.services.duplicate_guard import execute_with_duplicate_guard, DuplicateGuardBlocked
from app.services.razorpay_client import RazorpayError
from app.schemas.state import CaseState

class TestDuplicateGuard(unittest.TestCase):

    def setUp(self):
        self.payout_mock = MagicMock(return_value="payout_success")
        self.transition_mock = MagicMock()

    @patch('app.services.duplicate_guard.get_refund')
    def test_original_refund_processed_blocks_payout(self, mock_get_refund):
        # A. Original refund status = `processed`
        mock_get_refund.return_value = {"status": "processed"}

        result = execute_with_duplicate_guard(
            refund_id="rfnd_123",
            current_state=CaseState.APPROVED,
            payout_callable=self.payout_mock,
            transition_callback=self.transition_mock
        )

        # → payout continuation is NOT called.
        self.payout_mock.assert_not_called()
        self.assertIsNone(result)

        # → case transitions to `DUPLICATE_GUARD_TRIGGERED` then `RESOLVED`
        self.assertEqual(self.transition_mock.call_count, 2)
        self.assertEqual(self.transition_mock.call_args_list[0][0][0], CaseState.DUPLICATE_GUARD_TRIGGERED)
        self.assertEqual(self.transition_mock.call_args_list[1][0][0], CaseState.RESOLVED)

    @patch('app.services.duplicate_guard.get_refund')
    def test_original_refund_non_processed_allows_payout(self, mock_get_refund):
        # B. Original refund status = non-processed (e.g. failed)
        mock_get_refund.return_value = {"status": "failed"}

        result = execute_with_duplicate_guard(
            refund_id="rfnd_123",
            current_state=CaseState.APPROVED,
            payout_callable=self.payout_mock,
            transition_callback=self.transition_mock
        )

        # → guard permits continuation.
        self.payout_mock.assert_called_once()
        self.assertEqual(result, "payout_success")
        self.transition_mock.assert_not_called()

    @patch('app.services.duplicate_guard.get_refund')
    def test_razorpay_get_request_fails_blocks(self, mock_get_refund):
        # C. Razorpay GET request fails
        mock_get_refund.side_effect = RazorpayError("API Error")

        with self.assertRaises(DuplicateGuardBlocked):
            execute_with_duplicate_guard(
                refund_id="rfnd_123",
                current_state=CaseState.APPROVED,
                payout_callable=self.payout_mock,
                transition_callback=self.transition_mock
            )

        self.payout_mock.assert_not_called()
        self.transition_mock.assert_not_called()

    @patch('app.services.duplicate_guard.get_refund')
    def test_razorpay_get_request_times_out_blocks(self, mock_get_refund):
        # D. Razorpay GET request times out
        mock_get_refund.side_effect = Exception("Timeout")

        with self.assertRaises(DuplicateGuardBlocked):
            execute_with_duplicate_guard(
                refund_id="rfnd_123",
                current_state=CaseState.APPROVED,
                payout_callable=self.payout_mock,
                transition_callback=self.transition_mock
            )

        self.payout_mock.assert_not_called()
        self.transition_mock.assert_not_called()

    @patch('app.services.duplicate_guard.get_refund')
    def test_razorpay_response_malformed_blocks(self, mock_get_refund):
        # E. Razorpay response is malformed
        
        # Test 1: Not a dict
        mock_get_refund.return_value = ["not", "a", "dict"]
        with self.assertRaises(DuplicateGuardBlocked):
            execute_with_duplicate_guard(
                refund_id="rfnd_123",
                current_state=CaseState.APPROVED,
                payout_callable=self.payout_mock,
                transition_callback=self.transition_mock
            )
            
        # Test 2: Missing status
        mock_get_refund.return_value = {"id": "rfnd_123"}
        with self.assertRaises(DuplicateGuardBlocked):
            execute_with_duplicate_guard(
                refund_id="rfnd_123",
                current_state=CaseState.APPROVED,
                payout_callable=self.payout_mock,
                transition_callback=self.transition_mock
            )

        self.payout_mock.assert_not_called()
        self.transition_mock.assert_not_called()

    @patch('app.services.duplicate_guard.get_refund')
    def test_razorpay_unknown_status_blocks(self, mock_get_refund):
        # F. Razorpay returns an unknown/unexpected refund status
        mock_get_refund.return_value = {"status": "partially_refunded"} # Unknown status

        with self.assertRaises(DuplicateGuardBlocked):
            execute_with_duplicate_guard(
                refund_id="rfnd_123",
                current_state=CaseState.APPROVED,
                payout_callable=self.payout_mock,
                transition_callback=self.transition_mock
            )

        self.payout_mock.assert_not_called()
        self.transition_mock.assert_not_called()

    @patch('app.services.duplicate_guard.get_refund')
    def test_live_fetch_occurs_immediately_before(self, mock_get_refund):
        # G. Verify that the LIVE refund-status GET occurs immediately before the protected payout continuation.
        call_order = []
        
        def mock_get_refund_ordered(*args, **kwargs):
            call_order.append("get_refund")
            return {"status": "pending"}
            
        def mock_payout():
            call_order.append("payout")
            return "success"
            
        mock_get_refund.side_effect = mock_get_refund_ordered
        
        execute_with_duplicate_guard(
            refund_id="rfnd_123",
            current_state=CaseState.APPROVED,
            payout_callable=mock_payout,
            transition_callback=self.transition_mock
        )
        
        self.assertEqual(call_order, ["get_refund", "payout"])

    @patch('app.services.duplicate_guard.get_refund')
    def test_late_processed_blocks_payout(self, mock_get_refund):
        # H. Verify that when the original refund becomes `processed` between the earlier case state and this final guard check, the guard still blocks the payout.
        
        # Simulating that previously we thought it was 'failed' (since current_state is APPROVED), 
        # but now the live fetch says 'processed'
        mock_get_refund.return_value = {"status": "processed"}

        execute_with_duplicate_guard(
            refund_id="rfnd_123",
            current_state=CaseState.APPROVED,
            payout_callable=self.payout_mock,
            transition_callback=self.transition_mock
        )

        self.payout_mock.assert_not_called()
        self.assertEqual(self.transition_mock.call_count, 2)
