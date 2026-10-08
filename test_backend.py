import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from fastapi.testclient import TestClient
from main import app

client = TestClient(app)

def run_tests():
    print("=== Testing MediConnect Backend API ===")
    
    # 1. Health Check
    r = client.get("/api/health")
    assert r.status_code == 200, f"Health check failed: {r.text}"
    health = r.json()
    print("1. Health Check:", health)
    assert health["database"] == "connected"
    assert health["maternal_model"] == "loaded"

    # 2. Login
    r = client.post("/api/auth/login", json={"username": "asha_sunita", "password": "asha123"})
    assert r.status_code == 200, f"Login failed: {r.text}"
    login_data = r.json()
    print("2. Login successful for:", login_data["user"]["full_name"], "| Village:", login_data["user"]["village"])

    # 3. Dashboard KPIs
    r = client.get("/api/dashboard/stats")
    assert r.status_code == 200
    stats = r.json()
    print("3. Dashboard Stats:", stats)
    assert stats["total_mothers"] > 0
    assert stats["total_children"] > 0

    # 4. Maternal Risk Prediction - High Risk Case
    high_risk_input = {
        "Age": 36,
        "SystolicBP": 145,
        "DiastolicBP": 95,
        "BS": 14.0,
        "BodyTemp": 98.6,
        "HeartRate": 88
    }
    r = client.post("/api/maternal/predict", json=high_risk_input)
    assert r.status_code == 200
    pred_high = r.json()
    print("4. High Risk Case Prediction:", pred_high["risk_level"], "| Predicted Class Probability:", pred_high["predicted_class_probability"])
    assert pred_high["risk_level"] == "High Risk"
    assert pred_high["requires_referral"] is True
    assert "predicted_class_probability" in pred_high
    assert "Decision-support prediction only" in pred_high["disclaimer"]

    # 5. Maternal Risk Prediction - Low Risk Case (matching dataset row 10)
    low_risk_input = {
        "Age": 23,
        "SystolicBP": 90,
        "DiastolicBP": 60,
        "BS": 7.0,
        "BodyTemp": 98.0,
        "HeartRate": 76
    }
    r = client.post("/api/maternal/predict", json=low_risk_input)
    assert r.status_code == 200
    pred_low = r.json()
    print("5. Low Risk Case Prediction:", pred_low["risk_level"], "| Predicted Class Probability:", pred_low["predicted_class_probability"])
    assert pred_low["risk_level"] in ["Low Risk", "Medium Risk"]
    assert "predicted_class_probability" in pred_low

    # 6. Child Immunization Follow-up List (Rule-based UIP)
    r = client.get("/api/immunizations/follow-up")
    assert r.status_code == 200
    fu = r.json()
    print("6. Immunization Follow-Up:", fu["prototype_note"], "| Total Pending:", fu["summary"]["total_pending"])
    assert len(fu["follow_up_list"]) > 0

    # 7. Outbreak Early Warning Anomaly Detection
    r = client.get("/api/outbreak/alerts")
    assert r.status_code == 200
    outbreak = r.json()
    print("7. Outbreak Early Warning: Active Alerts:", outbreak["active_alerts_count"])
    for alert in outbreak["alerts"]:
        print(f"   Alert: [{alert['village']}] {alert['message']}")

    # 8. Child Immunization Aggregate Dataset Analytics
    r = client.get("/api/analytics/coverage")
    assert r.status_code == 200
    cov = r.json()
    print("8. Aggregate Analytics: Total Districts:", cov["dataset_info"]["total_districts"], "| Penta Dropout %:", cov["aggregate_metrics"]["penta_dropout_rate_pct"])

    # 9. Offline Sync Push
    import time
    ts = int(time.time() * 1000)
    sync_payload = {
        "client_device_id": "ASHA-TAB-99",
        "user_id": 1,
        "patients": [{
            "client_uid": f"OFFLINE-PAT-{ts}",
            "full_name": "Meera Devi (Offline Entry)",
            "age": 24,
            "village": "Rampur",
            "phone": "9870001111",
            "rch_id": f"RCH-OFFLINE-{ts}"
        }],
        "symptoms": [{
            "client_uid": f"OFFLINE-SYM-{ts}",
            "village": "Rampur",
            "person_name": "Golu",
            "age": 6,
            "gender": "Male",
            "symptom_type": "Fever",
            "severity": "Mild",
            "onset_date": "2026-09-23"
        }]
    }
    r = client.post("/api/sync/push", json=sync_payload)
    assert r.status_code == 200
    sync_res = r.json()
    print("9. Offline Sync Push Result:", sync_res)
    assert sync_res["total_records_synced"] == 2

    # 10. Model Status & Actual Evaluation Metrics
    r = client.get("/api/model/status")
    assert r.status_code == 200
    model_st = r.json()
    print("10. Model Metrics: Algorithm:", model_st["algorithm"], "| Accuracy:", model_st["evaluation_metrics"]["accuracy"], "| Recall Macro:", model_st["evaluation_metrics"]["recall_macro"])

    print("\nALL 10 VERIFICATION TESTS PASSED SUCCESSFULLY!")

if __name__ == "__main__":
    run_tests()
