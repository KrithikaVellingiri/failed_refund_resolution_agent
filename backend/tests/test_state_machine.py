import unittest
from app.schemas.state import CaseState
from app.services.state_machine import validate_transition, InvalidTransitionError

class TestStateMachine(unittest.TestCase):
    
    def test_valid_transitions(self):
        valid_transitions = [
            (CaseState.REFUND_FAILED, CaseState.CLASSIFIED),
            (CaseState.CLASSIFIED, CaseState.AWAITING_ALTERNATE),
            (CaseState.AWAITING_ALTERNATE, CaseState.ALTERNATE_SUBMITTED),
            (CaseState.ALTERNATE_SUBMITTED, CaseState.INVESTIGATING),
            (CaseState.INVESTIGATING, CaseState.RISK_SCORED),
            (CaseState.RISK_SCORED, CaseState.APPROVED),
            (CaseState.RISK_SCORED, CaseState.REVIEW),
            (CaseState.RISK_SCORED, CaseState.REJECTED),
            (CaseState.REVIEW, CaseState.APPROVED),
            (CaseState.REVIEW, CaseState.REJECTED),
            (CaseState.REVIEW, CaseState.NEEDS_INFORMATION),
            (CaseState.NEEDS_INFORMATION, CaseState.AWAITING_ALTERNATE),
            (CaseState.APPROVED, CaseState.DUPLICATE_GUARD_TRIGGERED),
            (CaseState.APPROVED, CaseState.PAYOUT_PENDING),
            (CaseState.DUPLICATE_GUARD_TRIGGERED, CaseState.RESOLVED),
            (CaseState.PAYOUT_PENDING, CaseState.PAYOUT_SUCCESS),
            (CaseState.PAYOUT_PENDING, CaseState.PAYOUT_FAILED),
            (CaseState.PAYOUT_SUCCESS, CaseState.RESOLVED),
            (CaseState.PAYOUT_FAILED, CaseState.RISK_SCORED),
            (CaseState.PAYOUT_FAILED, CaseState.RESOLVED)
        ]
        
        for curr, next_st in valid_transitions:
            self.assertTrue(validate_transition(curr, next_st))

    def test_case_expired_transitions(self):
        # Test pre-payout states can transition to CASE_EXPIRED
        pre_payout_states = [
            CaseState.REFUND_FAILED,
            CaseState.CLASSIFIED,
            CaseState.AWAITING_ALTERNATE,
            CaseState.ALTERNATE_SUBMITTED,
            CaseState.INVESTIGATING,
            CaseState.RISK_SCORED,
            CaseState.APPROVED,
            CaseState.REVIEW,
            CaseState.NEEDS_INFORMATION,
            CaseState.DUPLICATE_GUARD_TRIGGERED
        ]
        for state in pre_payout_states:
            self.assertTrue(validate_transition(state, CaseState.CASE_EXPIRED))

    def test_invalid_transitions(self):
        invalid_transitions = [
            (CaseState.REFUND_FAILED, CaseState.APPROVED),
            (CaseState.REFUND_FAILED, CaseState.PAYOUT_PENDING),
            (CaseState.CLASSIFIED, CaseState.APPROVED),
            (CaseState.AWAITING_ALTERNATE, CaseState.APPROVED),
            (CaseState.INVESTIGATING, CaseState.PAYOUT_SUCCESS),
            (CaseState.RISK_SCORED, CaseState.PAYOUT_SUCCESS),
            (CaseState.RESOLVED, CaseState.APPROVED),
            (CaseState.RESOLVED, CaseState.REFUND_FAILED),
            (CaseState.CASE_EXPIRED, CaseState.INVESTIGATING),
            (CaseState.PAYOUT_SUCCESS, CaseState.PAYOUT_PENDING)
        ]
        
        for curr, next_st in invalid_transitions:
            with self.assertRaises(InvalidTransitionError):
                validate_transition(curr, next_st)

if __name__ == '__main__':
    unittest.main()
