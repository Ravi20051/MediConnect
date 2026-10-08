"""
MediConnect — Local Production-Like Simulation & Deployment Verification

Simulates a production environment with:
- PORT=10000
- HOST=0.0.0.0
- SECRET_KEY=production-test-key-32-chars-long-abc
- ALLOWED_ORIGINS=https://mediconnect.onrender.com,http://localhost:10000
- Runs all core API endpoints, frontend serving, service worker, and model inference
"""

import os
import sys

# Set production simulation environment variables before imports
os.environ["HOST"] = "0.0.0.0"
os.environ["PORT"] = "10000"
os.environ["SECRET_KEY"] = "production-test-key-32-chars-long-abc"
os.environ["ALLOWED_ORIGINS"] = "https://mediconnect.onrender.com,http://localhost:10000"

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from fastapi.testclient import TestClient
from main import app
from services.maternal_service import maternal_service

client = TestClient(app)

def run_production_simulation():
    print("=" * 70)
    print("    MEDICONNECT — PRODUCTION SIMULATION & CONFIGURATION TEST")
    print("=" * 70)

    # 1. Health check with DB and Model
    res = client.get("/api/health")
    assert res.status_code == 200, f"Health check failed: {res.text}"
    data = res.json()
    assert data["status"] == "healthy"
    assert data["database"] == "connected"
    assert data["maternal_model"] == "loaded"
    print(" [PASS] 1. /api/health: healthy, DB connected, model loaded (DB engine: %s)" % data["database_type"])

    # 2. Production Authentication
    res = client.post("/api/auth/login", json={"username": "asha_sunita", "password": "asha123"})
    assert res.status_code == 200
    login_data = res.json()
    assert "token" in login_data
    assert login_data["user"]["username"] == "asha_sunita"
    print(" [PASS] 2. /api/auth/login: authenticated user '%s' (%s)" % (login_data["user"]["full_name"], login_data["user"]["role"]))

    # 3. Model Inference (Single Genuine Model)
    pred_payload = {
        "Age": 32.0,
        "SystolicBP": 140.0,
        "DiastolicBP": 90.0,
        "BS": 12.0,
        "BodyTemp": 98.6,
        "HeartRate": 85.0
    }
    res = client.post("/api/maternal/predict", json=pred_payload)
    assert res.status_code == 200
    pred_res = res.json()
    assert pred_res["risk_level"] in ["Low Risk", "Medium Risk", "High Risk"]
    assert pred_res["algorithm"] == "RandomForestClassifier"
    print(" [PASS] 3. /api/maternal/predict: genuine ML inference executed (Risk: %s, Prob: %.2f)" % (
        pred_res["risk_level"], pred_res["predicted_class_probability"]
    ))

    # 4. Outbreak Cluster Detection
    res = client.get("/api/outbreak/alerts")
    assert res.status_code == 200
    outbreak_res = res.json()
    assert "alerts" in outbreak_res
    print(" [PASS] 4. /api/outbreak/alerts: active alerts = %d" % outbreak_res["active_alerts_count"])

    # 5. UIP Follow-Up Service
    res = client.get("/api/immunizations/follow-up")
    assert res.status_code == 200
    imm_res = res.json()
    assert "follow_up_list" in imm_res
    print(" [PASS] 5. /api/immunizations/follow-up: follow-up tracking operational (total pending: %d)" % imm_res["summary"]["total_pending"])

    # 6. Child Macro Analytics (Coverage)
    res = client.get("/api/analytics/coverage")
    assert res.status_code == 200
    cov_res = res.json()
    assert cov_res["aggregate_metrics"]["penta_dropout_rate_pct"] is not None
    print(" [PASS] 6. /api/analytics/coverage: macro analytics loaded (%d districts reporting)" % cov_res["dataset_info"]["total_districts"])

    # 7. Static Application Shell & PWA Endpoints
    res = client.get("/")
    assert res.status_code == 200
    assert "MediConnect" in res.text
    print(" [PASS] 7. GET /: application HTML shell served")

    res = client.get("/sw.js")
    assert res.status_code == 200
    assert res.headers.get("service-worker-allowed") == "/"
    print(" [PASS] 8. GET /sw.js: Service Worker served with 'Service-Worker-Allowed: /'")

    res = client.get("/manifest.json")
    assert res.status_code == 200
    print(" [PASS] 9. GET /manifest.json: PWA manifest served")

    print("\n" + "=" * 70)
    print("    ALL PRODUCTION SIMULATION CHECKS PASSED SUCCESSFULLY! (100%)")
    print("=" * 70)

if __name__ == "__main__":
    run_production_simulation()
