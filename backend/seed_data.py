import os
import json
import joblib
import pandas as pd
from datetime import datetime, timedelta
from database import get_db_connection, hash_password, init_db

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(BASE_DIR, "ml", "maternal_risk_model.joblib")

def seed():
    init_db()
    conn = get_db_connection()
    cursor = conn.cursor()

    # Check if already seeded
    cursor.execute("SELECT COUNT(*) FROM patients")
    if cursor.fetchone()[0] > 0:
        print("Database already contains patient data. Skipping seeding.")
        conn.close()
        return

    print("Seeding initial authentic field data...")

    # 1. Create Users
    users = [
        ("asha_sunita", "Sunita Devi", "asha_worker", "Rampur", "Rampur Sub-Center", "9876543210", "asha123"),
        ("asha_anita", "Anita Sharma", "asha_worker", "Bhimpur", "Bhimpur Sub-Center", "9876543211", "asha123"),
        ("admin_meena", "Meena Kumari (ANM Supervisor)", "supervisor", "Block Center", "Primary Health Center (PHC)", "9876543212", "admin123")
    ]
    
    user_ids = {}
    for uname, fname, role, village, sc, phone, pwd in users:
        cursor.execute("SELECT id FROM users WHERE username = ?", (uname,))
        row = cursor.fetchone()
        if row:
            user_ids[uname] = row[0]
        else:
            phash, salt = hash_password(pwd)
            cursor.execute("""
                INSERT INTO users (username, full_name, role, village, sub_center, phone, password_hash, salt, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (uname, fname, role, village, sc, phone, phash, salt, datetime.now().isoformat()))
            user_ids[uname] = cursor.lastrowid
    
    sunita_id = user_ids["asha_sunita"]
    anita_id = user_ids["asha_anita"]

    # Load ML model to compute real predictions for seeded maternal visits
    model = joblib.load(MODEL_PATH)

    # 2. Seed Mothers / Patients
    now = datetime.now()
    mothers_data = [
        # (name, age, husband, village, phone, rch_id, lmp_offset_days, edd_offset_days, gravida, notes, user_id)
        ("Pooja Devi", 25, "Rajesh Kumar", "Rampur", "9871112233", "RCH-UP-2026-001", -120, 160, 2, "2nd pregnancy, past normal delivery", sunita_id),
        ("Kavita Yadav", 35, "Suresh Yadav", "Rampur", "9871112234", "RCH-UP-2026-002", -180, 100, 3, "High blood pressure observed during last visit", sunita_id),
        ("Aarti Singh", 21, "Manoj Singh", "Rampur", "9871112235", "RCH-UP-2026-003", -60, 220, 1, "Primigravida, first ANC completed", sunita_id),
        ("Suman Verma", 29, "Dinesh Verma", "Bhimpur", "9871112236", "RCH-UP-2026-004", -150, 130, 2, "Normal ANC 2 completed", anita_id),
        ("Rekha Bai", 38, "Mahesh Bai", "Bhimpur", "9871112237", "RCH-UP-2026-005", -210, 70, 4, "High blood sugar reported", anita_id),
        ("Anjali Sharma", 23, "Vikram Sharma", "Rampur", "9871112238", "RCH-UP-2026-006", -90, 190, 1, "All tests normal", sunita_id),
    ]

    mother_ids = []
    for m in mothers_data:
        lmp = (now + timedelta(days=m[6])).strftime("%Y-%m-%d")
        edd = (now + timedelta(days=m[7])).strftime("%Y-%m-%d")
        created_at = (now + timedelta(days=m[6] + 15)).isoformat()
        cursor.execute("""
            INSERT INTO patients (client_uid, full_name, age, husband_name, village, phone, rch_id, lmp_date, edd_date, gravida, high_risk_flag, notes, created_by, sync_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SYNCED', ?, ?)
        """, (f"PAT-{m[5]}", m[0], m[1], m[2], m[3], m[4], m[5], lmp, edd, m[8], 0, m[9], m[10], created_at, created_at))
        mother_ids.append(cursor.lastrowid)

    # 3. Seed Maternal Health Records with Real ML Predictions
    # Inputs: [Age, SystolicBP, DiastolicBP, BS, BodyTemp, HeartRate]
    maternal_visits = [
        # Pooja Devi (Normal)
        (mother_ids[0], 1, 25, 110, 75, 7.2, 98.4, 72, "ANC 1 routine checkup", sunita_id, -90),
        (mother_ids[0], 2, 25, 115, 78, 7.4, 98.2, 74, "ANC 2 regular checkup", sunita_id, -30),
        # Kavita Yadav (High Risk: Age 35, BP 145/95, BS 13.5)
        (mother_ids[1], 1, 35, 145, 95, 13.5, 98.6, 86, "Severe headache and elevated BP observed", sunita_id, -20),
        # Aarti Singh (Low Risk: Age 21, BP 110, Diastolic 70, BS 7.0)
        (mother_ids[2], 1, 21, 110, 70, 7.0, 98.0, 70, "Initial registration and checkup", sunita_id, -45),
        # Suman Verma (Medium Risk: Age 29, BP 125, Diastolic 85, BS 9.5)
        (mother_ids[3], 1, 29, 125, 85, 9.5, 98.6, 76, "ANC 2 visit", anita_id, -40),
        # Rekha Bai (High Risk: Age 38, BP 140, Diastolic 90, BS 15.0, HeartRate 88)
        (mother_ids[4], 1, 38, 140, 90, 15.0, 98.4, 88, "Gestational diabetes indicators and elevated BP", anita_id, -15),
    ]

    for pid, vnum, age, sbp, dbp, bs, bt, hr, notes, uid, off_days in maternal_visits:
        features_df = pd.DataFrame([{
            "Age": age, "SystolicBP": sbp, "DiastolicBP": dbp, "BS": bs, "BodyTemp": bt, "HeartRate": hr
        }])
        pred_label = model.predict(features_df)[0]
        proba = float(max(model.predict_proba(features_df)[0]))
        rec_time = (now + timedelta(days=off_days)).isoformat()
        
        cursor.execute("""
            INSERT INTO maternal_records (client_uid, patient_id, visit_number, age, systolic_bp, diastolic_bp, blood_sugar, body_temp, heart_rate, risk_level, confidence, model_version, action_notes, recorded_by, sync_status, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'v1.0.0', ?, ?, 'SYNCED', ?)
        """, (f"MR-{pid}-{vnum}", pid, vnum, age, sbp, dbp, bs, bt, hr, pred_label, round(proba, 4), notes, uid, rec_time))
        
        # If High Risk, flag patient table
        if pred_label == "High Risk":
            cursor.execute("UPDATE patients SET high_risk_flag = 1 WHERE id = ?", (pid,))

    # 4. Seed Children Records (Linked to Mothers & Universal Immunization Schedule)
    children_data = [
        # (mother_id, name, gender, age_in_months, weight, village, phone, uid)
        (mother_ids[0], "Aarav Kumar", "Male", 3.5, 5.8, "Rampur", "9871112233", sunita_id),
        (mother_ids[1], "Priya Yadav", "Female", 10.0, 8.2, "Rampur", "9871112234", sunita_id),
        (mother_ids[3], "Rohan Verma", "Male", 1.5, 4.2, "Bhimpur", "9871112236", anita_id),
        (None, "Vikas Gond", "Male", 16.0, 9.5, "Rampur", "9871119999", sunita_id), # Guardian child
        (None, "Khushi Kumari", "Female", 2.0, 4.6, "Rampur", "9871118888", sunita_id)
    ]

    child_ids = []
    for mid, cname, gender, age_m, bweight, village, phone, uid in children_data:
        dob = (now - timedelta(days=int(age_m * 30.4))).strftime("%Y-%m-%d")
        created_at = (now - timedelta(days=int(age_m * 30.4) - 2)).isoformat()
        cursor.execute("""
            INSERT INTO children (client_uid, mother_id, name, gender, dob, birth_weight, guardian_name, village, phone, rch_child_id, created_by, sync_status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SYNCED', ?, ?)
        """, (f"CH-{cname.replace(' ', '')}", mid, cname, gender, dob, bweight, "Mother/Father", village, phone, f"RCH-CH-{cname[:3]}", uid, created_at, created_at))
        child_ids.append((cursor.lastrowid, dob, age_m))

    # 5. Seed Immunization Schedule & Status for Children based on UIP rules:
    # Birth: BCG, OPV 0, Hep B 0
    # 6 Weeks (~1.5m): Pentavalent 1, OPV 1, Rotavirus 1
    # 10 Weeks (~2.5m): Pentavalent 2, OPV 2, Rotavirus 2
    # 14 Weeks (~3.5m): Pentavalent 3, OPV 3, fIPV 1
    # 9-12 Months: MR 1, Vit A 1, PCV Booster
    # 16-24 Months: DPT Booster 1, MR 2, OPV Booster
    for cid, dob_str, age_m in child_ids:
        dob = datetime.strptime(dob_str, "%Y-%m-%d")
        
        # Schedule items: (vaccine_name, dose, due_days_after_birth)
        uip_schedule = [
            ("BCG", 1, 0),
            ("Hep B (Birth)", 1, 0),
            ("OPV (Birth)", 0, 0),
            ("Pentavalent", 1, 42), # 6 weeks
            ("OPV", 1, 42),
            ("Pentavalent", 2, 70), # 10 weeks
            ("OPV", 2, 70),
            ("Pentavalent", 3, 98), # 14 weeks
            ("OPV", 3, 98),
            ("Measles-Rubella (MR)", 1, 274), # 9 months
            ("Vitamin A", 1, 274),
            ("DPT Booster", 1, 485) # 16 months
        ]

        for vname, dose, due_days in uip_schedule:
            due_date = dob + timedelta(days=due_days)
            due_str = due_date.strftime("%Y-%m-%d")
            
            # Status determination based on child age vs due date:
            if now > due_date + timedelta(days=28): # overdue if > 4 weeks past due date and not given
                if due_days < int(age_m * 30.4) - 40:
                    # administered in past
                    status = "COMPLETED"
                    given_date = (due_date + timedelta(days=5)).strftime("%Y-%m-%d")
                else:
                    # missed vaccination -> OVERDUE
                    status = "OVERDUE"
                    given_date = None
            elif now >= due_date:
                # Due now / this month
                status = "DUE"
                given_date = None
            else:
                # Scheduled in future
                status = "SCHEDULED"
                given_date = None

            if status in ["COMPLETED", "DUE", "OVERDUE"]:
                # If overdue and older than 1 month, mark as FOLLOW_UP_REQUIRED
                if status == "OVERDUE":
                    status = "FOLLOW_UP_REQUIRED"

                cursor.execute("""
                    INSERT INTO immunizations (client_uid, child_id, vaccine_name, dose_number, due_date, given_date, status, batch_no, notes, administered_by, sync_status, recorded_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, 'B-2026', '', ?, 'SYNCED', ?)
                """, (f"IMM-{cid}-{vname}-{dose}", cid, vname, dose, due_str, given_date, status, sunita_id, now.isoformat()))

    # 6. Seed Symptom Logs across villages for Outbreak Early Warning
    # Scenario:
    # In 'Rampur': Historical baseline is 1-2 cases of diarrhea per week.
    # In the last 4 days, there are 8 cases of Diarrhea/Vomiting reported by ASHA Sunita! -> Anomaly / Cluster Detected.
    # In 'Bhimpur': Normal baseline (1 mild fever, 1 respiratory cough over 10 days) -> Normal, no cluster.
    symptom_entries = [
        # Historical baseline in Rampur (15-30 days ago)
        ("Rampur", "Mohan Lal", 45, "Male", "Diarrhea/Vomiting", "Mild", -28, sunita_id),
        ("Rampur", "Geeta", 8, "Female", "Fever", "Moderate", -22, sunita_id),
        ("Rampur", "Santosh", 60, "Male", "Acute Respiratory/Cough", "Mild", -18, sunita_id),
        ("Rampur", "Baby of Aarti", 1, "Male", "Diarrhea/Vomiting", "Mild", -14, sunita_id),
        
        # Recent Cluster in Rampur (Last 4 days: 6 acute Diarrhea/Vomiting cases!)
        ("Rampur", "Kamlesh Kumar", 12, "Male", "Diarrhea/Vomiting", "Moderate", -3, sunita_id),
        ("Rampur", "Suraj", 7, "Male", "Diarrhea/Vomiting", "Severe", -3, sunita_id),
        ("Rampur", "Mamta", 30, "Female", "Diarrhea/Vomiting", "Severe", -2, sunita_id),
        ("Rampur", "Chotu", 5, "Male", "Diarrhea/Vomiting", "Moderate", -2, sunita_id),
        ("Rampur", "Lata Devi", 52, "Female", "Diarrhea/Vomiting", "Severe", -1, sunita_id),
        ("Rampur", "Pappu", 9, "Male", "Diarrhea/Vomiting", "Moderate", 0, sunita_id),

        # Normal baseline in Bhimpur (sporadic, no cluster)
        ("Bhimpur", "Ravi Prasad", 35, "Male", "Fever", "Mild", -10, anita_id),
        ("Bhimpur", "Shanti", 50, "Female", "Acute Respiratory/Cough", "Mild", -4, anita_id),
        ("Bhimpur", "Tara", 4, "Female", "Skin Rash/Measles", "Mild", -1, anita_id),
    ]

    for village, pname, age, gender, stype, sev, off_days, asha_uid in symptom_entries:
        onset = (now + timedelta(days=off_days)).strftime("%Y-%m-%d")
        rec_time = (now + timedelta(days=off_days)).isoformat()
        cursor.execute("""
            INSERT INTO symptom_logs (client_uid, village, person_name, age, gender, symptom_type, severity, onset_date, asha_id, notes, sync_status, recorded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'Field survey report', 'SYNCED', ?)
        """, (f"SYM-{village[:3]}-{pname.replace(' ', '')}-{off_days}", village, pname, age, gender, stype, sev, onset, asha_uid, rec_time))

    # 7. Record an initial sync audit
    cursor.execute("""
        INSERT INTO sync_audit (user_id, client_device_id, records_pushed, sync_type, status, synced_at)
        VALUES (?, 'ASHA-DEVICE-01', 18, 'INITIAL_SEED', 'SUCCESS', ?)
    """, (sunita_id, now.isoformat()))

    conn.commit()
    conn.close()
    print("Authentic field seed data successfully populated.")

if __name__ == "__main__":
    seed()
