import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from app.main import app
from app.db.database import SessionLocal

client = TestClient(app)

@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()

def test_get_cases_queue(db):
    # Ensure there is at least one case in the DB
    case = db.execute(text("SELECT case_id FROM refund_cases LIMIT 1")).fetchone()
    if not case:
        pytest.skip("No cases found in DB for testing.")
        
    response = client.get("/v1/cases")
    assert response.status_code == 200
    cases = response.json()
    assert isinstance(cases, list)
    
    if len(cases) > 0:
        c = cases[0]
        assert "case_id" in c
        assert "amount" in c
        assert "failure_type" in c
        assert "state" in c

def test_get_cases_filters(db):
    case = db.execute(text("SELECT case_id FROM refund_cases LIMIT 1")).fetchone()
    if not case:
        pytest.skip("No cases found in DB for testing.")
        
    response = client.get("/v1/cases?state=REVIEW")
    assert response.status_code == 200
    cases = response.json()
    for c in cases:
        assert c["state"] == "REVIEW"

def test_get_case_detail(db):
    case = db.execute(text("SELECT case_id FROM refund_cases LIMIT 1")).fetchone()
    if not case:
        pytest.skip("No cases found in DB for testing.")
        
    case_id = str(case.case_id)
    response = client.get(f"/v1/cases/{case_id}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["case_id"] == case_id
    assert "amount" in data
    assert "customer" in data
    assert "refund" in data
    assert "risk_signals" in data
    assert "extracted_claims" in data

def test_get_case_detail_not_found():
    import uuid
    dummy_id = str(uuid.uuid4())
    response = client.get(f"/v1/cases/{dummy_id}")
    assert response.status_code == 404
