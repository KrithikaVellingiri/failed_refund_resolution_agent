import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from unittest.mock import patch, MagicMock
from app.main import app
from app.schemas.state import CaseState
from app.db.database import get_db, SessionLocal
from app.services.duplicate_guard import DuplicateGuardBlocked

client = TestClient(app)

def setup_case(db, state: CaseState = CaseState.REVIEW, case_id: str = "b68f5c9e-5e37-4d92-95f2-4e9c7a052b61"):
    # Clear existing data safely
    db.execute(text("DELETE FROM audit_events"))
    db.execute(text("DELETE FROM payouts"))
    db.execute(text("DELETE FROM reviewer_outcomes"))
    db.execute(text("DELETE FROM claim_evidence_checks"))
    db.execute(text("DELETE FROM extracted_claims"))
    db.execute(text("DELETE FROM risk_signals"))
    db.execute(text("UPDATE refund_cases SET proposed_destination_id = NULL"))
    db.execute(text("DELETE FROM alternate_destinations"))
    db.execute(text("DELETE FROM refund_cases"))

    # Insert a dummy customer and refund if not exists
    db.execute(text("INSERT INTO customers (customer_id, name) VALUES ('00000000-0000-0000-0000-000000000001', 'Test Customer') ON CONFLICT DO NOTHING"))
    db.execute(text("INSERT INTO payments (payment_id, customer_id, amount, status) VALUES ('pay_test123', '00000000-0000-0000-0000-000000000001', 1000, 'captured') ON CONFLICT DO NOTHING"))
    db.execute(text("INSERT INTO refunds (refund_id, payment_id, amount, status, failure_reason) VALUES ('rfnd_test123', 'pay_test123', 1000, 'failed', 'bank_error') ON CONFLICT DO NOTHING"))
    
    # Need alternate destination to fetch for payout
    db.execute(
        text("INSERT INTO alternate_destinations (destination_id, customer_id, type, identifier) VALUES ('cc2450a5-31fa-4179-88a8-e7d350d23f18', '00000000-0000-0000-0000-000000000001', 'UPI', 'fa_test123') ON CONFLICT DO NOTHING")
    )

    db.execute(
        text("INSERT INTO refund_cases (case_id, refund_id, failure_type, classification_source, state, proposed_destination_id) VALUES (:id, 'rfnd_test123', 'TYPE_1_TECHNICAL', 'MATCHED_RULE', :state, 'cc2450a5-31fa-4179-88a8-e7d350d23f18')"),
        {"id": case_id, "state": state.value}
    )
    db.commit()

@pytest.fixture(autouse=True)
def clean_db():
    db = SessionLocal()
    setup_case(db)
    db.close()
    yield

def test_approve_transitions_and_triggers_payout():
    db = SessionLocal()
    case_id = "b68f5c9e-5e37-4d92-95f2-4e9c7a052b61"
    
    with patch("app.api.cases.execute_with_duplicate_guard") as mock_guard:
        # Mock guard success, returning simulated payout response
        mock_guard.return_value = ({"id": "pout_test123", "status": "processing"}, "cc2450a5-31fa-4179-88a8-e7d350d23f18", "UPI")
        
        # We need to simulate the BackgroundTasks behavior synchronously for the test
        # TestClient automatically runs BackgroundTasks
        response = client.post(
            f"/v1/cases/{case_id}/review",
            json={
                "action": "APPROVE",
                "reason": "Looks good",
                "reviewer_id": "rev_1"
            }
        )
        assert response.status_code == 200
        assert response.json()["new_state"] == "APPROVED"
        
        # Verify guard was called (from background task)
        assert mock_guard.called
        
        # Check DB states
        case = db.execute(text("SELECT state FROM refund_cases WHERE case_id = :id"), {"id": case_id}).mappings().first()
        # Because background task updates to PAYOUT_PENDING immediately if guard succeeds in this test
        assert case["state"] == "PAYOUT_PENDING"
        
        # Check reviewer_outcomes
        outcome = db.execute(text("SELECT * FROM reviewer_outcomes WHERE case_id = :id"), {"id": case_id}).mappings().first()
        assert outcome["action"] == "APPROVE"
        assert outcome["reviewer_id"] == "rev_1"
        assert outcome["reason"] == "Looks good"
        
        # Check audit_events for REVIEWER action
        audit = db.execute(text("SELECT * FROM audit_events WHERE case_id = :id AND actor_type = 'REVIEWER'"), {"id": case_id}).mappings().first()
        assert audit is not None
        
        # Check payouts table
        payout = db.execute(text("SELECT * FROM payouts WHERE case_id = :id"), {"id": case_id}).mappings().first()
        assert payout is not None
        assert payout["status"] == "processing"
        
    db.close()

def test_reject_transitions_state_no_payout():
    db = SessionLocal()
    case_id = "b68f5c9e-5e37-4d92-95f2-4e9c7a052b61"
    
    with patch("app.api.cases.execute_with_duplicate_guard") as mock_guard:
        response = client.post(
            f"/v1/cases/{case_id}/review",
            json={
                "action": "REJECT",
                "reason": "Too risky",
                "reviewer_id": "rev_2"
            }
        )
        assert response.status_code == 200
        assert response.json()["new_state"] == "REJECTED"
        
        # Ensure background task / payout was NOT called
        mock_guard.assert_not_called()
        
        case = db.execute(text("SELECT state FROM refund_cases WHERE case_id = :id"), {"id": case_id}).mappings().first()
        assert case["state"] == "REJECTED"
        
    db.close()

def test_request_more_info_transitions_state_no_payout():
    case_id = "b68f5c9e-5e37-4d92-95f2-4e9c7a052b61"
    with patch("app.api.cases.execute_with_duplicate_guard") as mock_guard:
        response = client.post(
            f"/v1/cases/{case_id}/review",
            json={
                "action": "REQUEST_MORE_INFO",
                "reason": "Need proof",
                "reviewer_id": "rev_3"
            }
        )
        assert response.status_code == 200
        assert response.json()["new_state"] == "NEEDS_INFORMATION"
        mock_guard.assert_not_called()

def test_blank_reason_rejected():
    case_id = "b68f5c9e-5e37-4d92-95f2-4e9c7a052b61"
    response = client.post(
        f"/v1/cases/{case_id}/review",
        json={"action": "APPROVE", "reason": "   ", "reviewer_id": "rev_1"}
    )
    assert response.status_code == 422 # Pydantic validation error

def test_blank_reviewer_id_rejected():
    case_id = "b68f5c9e-5e37-4d92-95f2-4e9c7a052b61"
    response = client.post(
        f"/v1/cases/{case_id}/review",
        json={"action": "APPROVE", "reason": "Good", "reviewer_id": "   "}
    )
    assert response.status_code == 422

def test_non_review_case_rejected():
    db = SessionLocal()
    case_id = "b68f5c9e-5e37-4d92-95f2-4e9c7a052b61"
    setup_case(db, state=CaseState.APPROVED, case_id=case_id)
    
    response = client.post(
        f"/v1/cases/{case_id}/review",
        json={"action": "APPROVE", "reason": "Good", "reviewer_id": "rev_1"}
    )
    assert response.status_code == 400
    assert "not in REVIEW state" in response.text
    db.close()

def test_invalid_action_rejected():
    case_id = "b68f5c9e-5e37-4d92-95f2-4e9c7a052b61"
    response = client.post(
        f"/v1/cases/{case_id}/review",
        json={"action": "MAGIC", "reason": "Good", "reviewer_id": "rev_1"}
    )
    assert response.status_code == 422

def test_payout_submission_failure_leaves_case_approved():
    db = SessionLocal()
    case_id = "b68f5c9e-5e37-4d92-95f2-4e9c7a052b61"
    
    # We patch execute_with_duplicate_guard to raise an exception 
    # to simulate Razorpay API failure inside payout_callable
    with patch("app.api.cases.execute_with_duplicate_guard", side_effect=Exception("Razorpay timeout")):
        response = client.post(
            f"/v1/cases/{case_id}/review",
            json={"action": "APPROVE", "reason": "Good", "reviewer_id": "rev_1"}
        )
        assert response.status_code == 200
        
        # Check DB state - should remain APPROVED, not PAYOUT_PENDING
        case = db.execute(text("SELECT state FROM refund_cases WHERE case_id = :id"), {"id": case_id}).mappings().first()
        assert case["state"] == "APPROVED"
        
        # Ensure no payouts row
        payout = db.execute(text("SELECT * FROM payouts WHERE case_id = :id"), {"id": case_id}).mappings().first()
        assert payout is None
        
    db.close()

def test_duplicate_guard_processed_path_does_not_create_payout():
    db = SessionLocal()
    case_id = "b68f5c9e-5e37-4d92-95f2-4e9c7a052b61"
    
    # We simulate duplicate guard catching a processed refund
    def mock_execute(*args, **kwargs):
        # Trigger transition callback for duplicate
        cb = kwargs.get("transition_callback")
        cb(CaseState.DUPLICATE_GUARD_TRIGGERED)
        cb(CaseState.RESOLVED)
        return None # duplicate blocked returns None
        
    with patch("app.api.cases.execute_with_duplicate_guard", side_effect=mock_execute):
        response = client.post(
            f"/v1/cases/{case_id}/review",
            json={"action": "APPROVE", "reason": "Good", "reviewer_id": "rev_1"}
        )
        assert response.status_code == 200
        
        case = db.execute(text("SELECT state FROM refund_cases WHERE case_id = :id"), {"id": case_id}).mappings().first()
        assert case["state"] == "RESOLVED"
        
        payout = db.execute(text("SELECT * FROM payouts WHERE case_id = :id"), {"id": case_id}).mappings().first()
        assert payout is None
        
    db.close()
