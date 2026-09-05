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

def test_get_evaluations_list(db):
    run = db.execute(text("SELECT eval_run_id FROM evaluation_runs LIMIT 1")).fetchone()
    if not run:
        pytest.skip("No evaluation runs found in DB.")
        
    response = client.get("/v1/evaluations")
    assert response.status_code == 200
    runs = response.json()
    assert isinstance(runs, list)
    
    if len(runs) > 0:
        r = runs[0]
        assert "run_id" in r
        assert "timestamp" in r
        assert "dataset_version" in r
        assert "policy_version" in r

def test_get_evaluation_detail(db):
    run = db.execute(text("SELECT eval_run_id FROM evaluation_runs LIMIT 1")).fetchone()
    if not run:
        pytest.skip("No evaluation runs found in DB.")
        
    run_id = str(run.eval_run_id)
    response = client.get(f"/v1/evaluations/{run_id}")
    assert response.status_code == 200
    
    data = response.json()
    assert data["run_id"] == run_id
    assert "dataset_version" in data
    assert "metrics" in data
    
    metrics = data["metrics"]
    assert "confusion_matrix" in metrics
    assert "exception_list" in metrics

def test_get_evaluation_detail_not_found():
    import uuid
    dummy_id = str(uuid.uuid4())
    response = client.get(f"/v1/evaluations/{dummy_id}")
    assert response.status_code == 404
