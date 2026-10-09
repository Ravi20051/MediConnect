"""
test_village_isolation.py
=========================
Comprehensive Village-Wise Data Isolation and Server-Side Access Control Test Suite.

Verifies:
- TEST A: Sunita (Rampur) creates mother, maternal record, child, immunization, symptom -> all appear for Sunita.
- TEST B: Anita (Bhimpur) logs in -> CANNOT see Sunita/Rampur records.
- TEST C: Anita attempts direct GET on Rampur records (e.g. GET /api/patients/{sunita_patient_id}) -> returns HTTP 403 Forbidden.
- TEST D: Anita passes ?village=Rampur query parameter -> backend rejects with HTTP 403 Forbidden.
- TEST E: Anita attempts to pass village="Rampur" in POST /api/patients -> backend server forces village="Bhimpur".
- TEST F: Sunita offline record sync via /api/sync/push -> stored under Rampur.
- TEST G: Anita attempts malicious spoofing in /api/sync/push (claiming village="Rampur" or linking to Rampur mother) -> server enforces Bhimpur or denies cross-village link.
- TEST H: Dashboard stats are strictly village-isolated.
- TEST I: Immunization follow-up list is strictly village-isolated.
- TEST J: Outbreak alerts and anomaly detection are strictly village-isolated.
- TEST K: Supervisor/Admin (admin_meena) retains cross-village visibility.
"""

import requests
import json
import sys

BASE_URL = "http://127.0.0.1:8000"

def run_tests():
    print("=" * 70)
    print("MEDICONNECT VILLAGE ISOLATION & ACCESS CONTROL TEST SUITE")
    print("=" * 70)

    # 0. Clean records to have a predictable test environment
    clean_res = requests.post(f"{BASE_URL}/api/admin/clean-records")
    assert clean_res.status_code == 200, f"Clean records failed: {clean_res.text}"
    print("[INIT] Clinical and surveillance records cleaned.")

    # 1. Authenticate Sunita (Rampur)
    login_sunita = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "asha_sunita",
        "password": "asha123"
    })
    assert login_sunita.status_code == 200, f"Login Sunita failed: {login_sunita.text}"
    sunita_data = login_sunita.json()
    sunita_token = sunita_data["token"]
    sunita_user = sunita_data["user"]
    assert sunita_user["village"] == "Rampur", f"Expected Rampur, got {sunita_user['village']}"
    sunita_headers = {"Authorization": f"Bearer {sunita_token}"}
    print(f"[AUTH] Sunita authenticated. Role: {sunita_user['role']}, Village: {sunita_user['village']}")

    # 2. Authenticate Anita (Bhimpur)
    login_anita = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "asha_anita",
        "password": "asha123"
    })
    assert login_anita.status_code == 200, f"Login Anita failed: {login_anita.text}"
    anita_data = login_anita.json()
    anita_token = anita_data["token"]
    anita_user = anita_data["user"]
    assert anita_user["village"] == "Bhimpur", f"Expected Bhimpur, got {anita_user['village']}"
    anita_headers = {"Authorization": f"Bearer {anita_token}"}
    print(f"[AUTH] Anita authenticated. Role: {anita_user['role']}, Village: {anita_user['village']}")

    # 3. Authenticate Supervisor (Admin Meena)
    login_admin = requests.post(f"{BASE_URL}/api/auth/login", json={
        "username": "admin_meena",
        "password": "admin123"
    })
    assert login_admin.status_code == 200, f"Login Admin failed: {login_admin.text}"
    admin_data = login_admin.json()
    admin_token = admin_data["token"]
    admin_headers = {"Authorization": f"Bearer {admin_token}"}
    print(f"[AUTH] Meena (Supervisor) authenticated. Role: {admin_data['user']['role']}")

    print("\n" + "-" * 70)
    print("TEST A: Sunita (Rampur) Creates Full Clinical Set & Verifies Scope")
    print("-" * 70)
    # A1: Add Mother
    res_m = requests.post(f"{BASE_URL}/api/patients", headers=sunita_headers, json={
        "full_name": "Radha Devi",
        "age": 26,
        "husband_name": "Ramesh",
        "village": "Rampur",
        "phone": "9876543210",
        "rch_id": "RCH-RAMPUR-001",
        "lmp_date": "2026-02-15"
    })
    assert res_m.status_code == 200, f"Add mother failed: {res_m.text}"
    sunita_patient_id = res_m.json()["id"]
    print(f"  [PASS] Created mother ID {sunita_patient_id} in {res_m.json()['village']}")

    # A2: Add Maternal Visit Record
    res_mr = requests.post(f"{BASE_URL}/api/maternal/records", headers=sunita_headers, json={
        "patient_id": sunita_patient_id,
        "Age": 26,
        "SystolicBP": 145,
        "DiastolicBP": 95,
        "BS": 12.0,
        "BodyTemp": 99.0,
        "HeartRate": 88,
        "risk_level": "High Risk",
        "confidence": 0.88,
        "notes": "High BP detected"
    })
    assert res_mr.status_code == 200, f"Add maternal record failed: {res_mr.text}"
    print("  [PASS] Created maternal record with High Risk")

    # A3: Add Child
    res_c = requests.post(f"{BASE_URL}/api/children", headers=sunita_headers, json={
        "mother_id": sunita_patient_id,
        "name": "Aarav",
        "gender": "Male",
        "dob": "2025-08-10",
        "village": "Rampur",
        "phone": "9876543210"
    })
    assert res_c.status_code == 200, f"Add child failed: {res_c.text}"
    sunita_child_id = res_c.json()["id"]
    print(f"  [PASS] Created child ID {sunita_child_id} in {res_c.json()['village']}")

    # A4: Update Immunization
    # Child's auto-generated UIP immunizations
    ch_details = requests.get(f"{BASE_URL}/api/children/{sunita_child_id}", headers=sunita_headers).json()
    sunita_imm_id = ch_details["immunizations"][0]["id"]
    res_imm = requests.put(f"{BASE_URL}/api/immunizations/{sunita_imm_id}", headers=sunita_headers, json={
        "given_date": "2025-08-10",
        "batch_no": "B-RAMPUR-01",
        "status": "COMPLETED"
    })
    assert res_imm.status_code == 200, f"Update immunization failed: {res_imm.text}"
    print(f"  [PASS] Recorded immunization ID {sunita_imm_id}")

    # A5: Log 5 Symptoms to create an outbreak pattern in Rampur (threshold is rec_cnt >= 4 or >= 5)
    for i in range(5):
        res_sym = requests.post(f"{BASE_URL}/api/symptoms", headers=sunita_headers, json={
            "village": "Rampur",
            "person_name": f"Patient R{i+1}",
            "age": 30 + i,
            "gender": "Female",
            "symptom_type": "Acute Diarrheal Disease",
            "severity": "Moderate",
            "onset_date": "2026-10-05"
        })
        assert res_sym.status_code == 200, f"Log symptom failed: {res_sym.text}"
    print("  [PASS] Logged 5 acute diarrheal symptom records in Rampur")

    # Verify all appear in Sunita's list
    p_sunita = requests.get(f"{BASE_URL}/api/patients", headers=sunita_headers).json()
    assert p_sunita["count"] == 1
    assert p_sunita["patients"][0]["full_name"] == "Radha Devi"
    print("  [PASS] Sunita sees her Rampur patient")

    c_sunita = requests.get(f"{BASE_URL}/api/children", headers=sunita_headers).json()
    assert c_sunita["count"] == 1
    assert c_sunita["children"][0]["name"] == "Aarav"
    print("  [PASS] Sunita sees her Rampur child")

    print("\n" + "-" * 70)
    print("TEST B: Anita (Bhimpur) Cannot See Any Sunita/Rampur Records")
    print("-" * 70)
    p_anita = requests.get(f"{BASE_URL}/api/patients", headers=anita_headers).json()
    assert p_anita["count"] == 0, f"Anita saw {p_anita['count']} patients! Isolation broken!"
    print("  [PASS] Anita sees 0 patients (Rampur patients hidden)")

    c_anita = requests.get(f"{BASE_URL}/api/children", headers=anita_headers).json()
    assert c_anita["count"] == 0, f"Anita saw {c_anita['count']} children! Isolation broken!"
    print("  [PASS] Anita sees 0 children (Rampur children hidden)")

    s_anita = requests.get(f"{BASE_URL}/api/symptoms", headers=anita_headers).json()
    assert s_anita["count"] == 0, f"Anita saw {s_anita['count']} symptoms! Isolation broken!"
    print("  [PASS] Anita sees 0 symptoms (Rampur symptoms hidden)")

    print("\n" + "-" * 70)
    print("TEST C: Direct ID-Based Access by Anita to Rampur Records Denied (403 Forbidden)")
    print("-" * 70)
    # Direct GET /api/patients/{sunita_patient_id}
    res_direct_pat = requests.get(f"{BASE_URL}/api/patients/{sunita_patient_id}", headers=anita_headers)
    assert res_direct_pat.status_code == 403, f"Expected 403 Forbidden, got {res_direct_pat.status_code}"
    print(f"  [PASS] GET /api/patients/{sunita_patient_id} returned HTTP 403 Forbidden")

    # Direct GET /api/children/{sunita_child_id}
    res_direct_ch = requests.get(f"{BASE_URL}/api/children/{sunita_child_id}", headers=anita_headers)
    assert res_direct_ch.status_code == 403, f"Expected 403 Forbidden, got {res_direct_ch.status_code}"
    print(f"  [PASS] GET /api/children/{sunita_child_id} returned HTTP 403 Forbidden")

    # Direct PUT /api/immunizations/{sunita_imm_id}
    res_direct_imm = requests.put(f"{BASE_URL}/api/immunizations/{sunita_imm_id}", headers=anita_headers, json={
        "status": "COMPLETED", "given_date": "2026-10-08"
    })
    assert res_direct_imm.status_code == 403, f"Expected 403 Forbidden, got {res_direct_imm.status_code}"
    print(f"  [PASS] PUT /api/immunizations/{sunita_imm_id} returned HTTP 403 Forbidden")

    # Direct POST /api/maternal/records referencing Sunita's Rampur patient
    res_mal_mr = requests.post(f"{BASE_URL}/api/maternal/records", headers=anita_headers, json={
        "patient_id": sunita_patient_id,
        "Age": 26, "SystolicBP": 120, "DiastolicBP": 80, "BS": 6.0, "BodyTemp": 98.6, "HeartRate": 72
    })
    assert res_mal_mr.status_code == 403, f"Expected 403 Forbidden, got {res_mal_mr.status_code}"
    print(f"  [PASS] POST /api/maternal/records for Rampur mother returned HTTP 403 Forbidden")

    print("\n" + "-" * 70)
    print("TEST D: Query Parameter Bypass Attempt (?village=Rampur) Denied")
    print("-" * 70)
    # Anita passes ?village=Rampur to GET /api/patients
    res_tamper_pat = requests.get(f"{BASE_URL}/api/patients?village=Rampur", headers=anita_headers)
    assert res_tamper_pat.status_code == 403, f"Expected 403 Forbidden, got {res_tamper_pat.status_code}"
    print("  [PASS] GET /api/patients?village=Rampur returned HTTP 403 Forbidden")

    # Anita passes ?village=Rampur to GET /api/children
    res_tamper_ch = requests.get(f"{BASE_URL}/api/children?village=Rampur", headers=anita_headers)
    assert res_tamper_ch.status_code == 403, f"Expected 403 Forbidden, got {res_tamper_ch.status_code}"
    print("  [PASS] GET /api/children?village=Rampur returned HTTP 403 Forbidden")

    # Anita passes ?village=Rampur to GET /api/dashboard/stats
    res_tamper_stats = requests.get(f"{BASE_URL}/api/dashboard/stats?village=Rampur", headers=anita_headers)
    assert res_tamper_stats.status_code == 403, f"Expected 403 Forbidden, got {res_tamper_stats.status_code}"
    print("  [PASS] GET /api/dashboard/stats?village=Rampur returned HTTP 403 Forbidden")

    print("\n" + "-" * 70)
    print("TEST E: Payload Tampering in POST Enforces Assigned Village")
    print("-" * 70)
    # Anita tries to create a mother with payload village="Rampur"
    res_create_tamper = requests.post(f"{BASE_URL}/api/patients", headers=anita_headers, json={
        "full_name": "Kavita Devi",
        "age": 24,
        "village": "Rampur" # Malicious spoof
    })
    assert res_create_tamper.status_code == 200
    created_village = res_create_tamper.json()["village"]
    assert created_village == "Bhimpur", f"Server trusted client village! Got: {created_village}"
    anita_patient_id = res_create_tamper.json()["id"]
    print(f"  [PASS] Backend overrode client village 'Rampur' and enforced '{created_village}'")

    print("\n" + "-" * 70)
    print("TEST F & G: Offline Sync Scope Enforcement (/api/sync/push)")
    print("-" * 70)
    # Test F: Sunita pushes offline record
    sync_sunita = requests.post(f"{BASE_URL}/api/sync/push", headers=sunita_headers, json={
        "client_device_id": "TAB-SUNITA",
        "user_id": 999, # Client ID is ignored in favor of authenticated user
        "patients": [{
            "client_uid": "PAT-OFFLINE-SUNITA-001",
            "full_name": "Pooja Devi",
            "age": 22,
            "village": "Rampur"
        }],
        "maternal_records": [],
        "children": [],
        "immunizations": [],
        "symptoms": []
    })
    assert sync_sunita.status_code == 200, f"Sync push failed: {sync_sunita.text}"
    assert sync_sunita.json()["details"]["patients"] == 1
    print("  [PASS] Sunita synced offline patient successfully into Rampur")

    # Test G: Anita maliciously attempts to sync a patient into Rampur and link a child to Sunita's mother
    sync_anita_malicious = requests.post(f"{BASE_URL}/api/sync/push", headers=anita_headers, json={
        "client_device_id": "TAB-ANITA-HACK",
        "user_id": 1, # Spoof user 1
        "patients": [{
            "client_uid": "PAT-OFFLINE-ANITA-SPOOF",
            "full_name": "Malicious Spoof Record",
            "age": 29,
            "village": "Rampur" # Malicious spoof attempt
        }],
        "maternal_records": [{
            "client_uid": "MR-ANITA-SPOOF",
            "patient_id": sunita_patient_id, # Cross-village link attempt
            "Age": 26, "SystolicBP": 120, "DiastolicBP": 80, "BS": 5.5, "BodyTemp": 98.4, "HeartRate": 70
        }],
        "children": [],
        "immunizations": [],
        "symptoms": [{
            "client_uid": "SYM-ANITA-SPOOF",
            "village": "Rampur", # Spoof Rampur outbreak
            "person_name": "Spoofed Person",
            "symptom_type": "Fever",
            "onset_date": "2026-10-06"
        }]
    })
    assert sync_anita_malicious.status_code == 200
    # Patient should have been saved under Bhimpur, maternal record skipped, symptom forced to Bhimpur
    assert sync_anita_malicious.json()["details"]["maternal_records"] == 0, "Cross-village maternal record was NOT rejected!"
    print("  [PASS] Cross-village maternal record rejected during sync")

    # Verify patient was assigned to Bhimpur
    check_spoof_pat = requests.get(f"{BASE_URL}/api/patients", headers=anita_headers).json()["patients"]
    spoofed = [p for p in check_spoof_pat if p["client_uid"] == "PAT-OFFLINE-ANITA-SPOOF"]
    assert len(spoofed) == 1
    assert spoofed[0]["village"] == "Bhimpur", f"Expected Bhimpur, got {spoofed[0]['village']}"
    print("  [PASS] Offline patient spoofing overridden by server to Bhimpur")

    print("\n" + "-" * 70)
    print("TEST H: Dashboard Statistics Are Strictly Village-Isolated")
    print("-" * 70)
    stats_sunita = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=sunita_headers).json()
    stats_anita = requests.get(f"{BASE_URL}/api/dashboard/stats", headers=anita_headers).json()

    print(f"  Sunita (Rampur)  Stats: Mothers={stats_sunita['total_mothers']}, High-Risk={stats_sunita['high_risk_mothers']}, Children={stats_sunita['total_children']}")
    print(f"  Anita  (Bhimpur) Stats: Mothers={stats_anita['total_mothers']}, High-Risk={stats_anita['high_risk_mothers']}, Children={stats_anita['total_children']}")

    assert stats_sunita["total_mothers"] == 2 # Radha Devi + Pooja Devi
    assert stats_sunita["high_risk_mothers"] == 1 # Radha Devi
    assert stats_sunita["total_children"] == 1 # Aarav

    assert stats_anita["total_mothers"] == 2 # Kavita Devi + Spoof Record (both forced to Bhimpur)
    assert stats_anita["high_risk_mothers"] == 0
    assert stats_anita["total_children"] == 0
    print("  [PASS] Dashboard stats strictly reflect only the assigned village")

    print("\n" + "-" * 70)
    print("TEST I: Immunization Follow-Up List Is Village-Isolated")
    print("-" * 70)
    fu_sunita = requests.get(f"{BASE_URL}/api/immunizations/follow-up", headers=sunita_headers).json()
    fu_anita = requests.get(f"{BASE_URL}/api/immunizations/follow-up", headers=anita_headers).json()

    print(f"  Sunita Follow-up count: {len(fu_sunita['follow_up_list'])}")
    print(f"  Anita  Follow-up count: {len(fu_anita['follow_up_list'])}")
    assert len(fu_sunita["follow_up_list"]) > 0
    assert all(item["village"] == "Rampur" for item in fu_sunita["follow_up_list"])
    assert len(fu_anita["follow_up_list"]) == 0
    print("  [PASS] Immunization follow-up only contains children from assigned village")

    print("\n" + "-" * 70)
    print("TEST J: Outbreak Surveillance Alerts Are Village-Isolated")
    print("-" * 70)
    alerts_sunita = requests.get(f"{BASE_URL}/api/outbreak/alerts", headers=sunita_headers).json()
    alerts_anita = requests.get(f"{BASE_URL}/api/outbreak/alerts", headers=anita_headers).json()

    print(f"  Sunita Outbreak Alerts: {alerts_sunita['active_alerts_count']}")
    print(f"  Anita  Outbreak Alerts: {alerts_anita['active_alerts_count']}")

    assert alerts_sunita["active_alerts_count"] >= 1, "Rampur cluster not detected for Sunita!"
    assert alerts_anita["active_alerts_count"] == 0, "Bhimpur erroneously received Rampur alert!"
    assert all(a["village"] == "Rampur" for a in alerts_sunita["alerts"])
    print("  [PASS] Outbreak cluster alert active for Rampur, 0 alerts for Bhimpur")

    print("\n" + "-" * 70)
    print("TEST K: Supervisor (admin_meena) Cross-Village Access")
    print("-" * 70)
    # Supervisor sees all villages
    p_admin_all = requests.get(f"{BASE_URL}/api/patients", headers=admin_headers).json()
    assert p_admin_all["count"] == 4 # 2 in Rampur + 2 in Bhimpur
    print(f"  [PASS] Supervisor sees all {p_admin_all['count']} patients across all villages")

    # Supervisor can specifically filter by ?village=Rampur
    p_admin_rampur = requests.get(f"{BASE_URL}/api/patients?village=Rampur", headers=admin_headers).json()
    assert p_admin_rampur["count"] == 2
    print(f"  [PASS] Supervisor can query ?village=Rampur ({p_admin_rampur['count']} records)")

    # Supervisor can specifically filter by ?village=Bhimpur
    p_admin_bhimpur = requests.get(f"{BASE_URL}/api/patients?village=Bhimpur", headers=admin_headers).json()
    assert p_admin_bhimpur["count"] == 2
    print(f"  [PASS] Supervisor can query ?village=Bhimpur ({p_admin_bhimpur['count']} records)")

    print("\n" + "=" * 70)
    print("ALL VILLAGE ISOLATION TESTS PASSED PERFECTLY!")
    print("=" * 70)

if __name__ == "__main__":
    run_tests()
