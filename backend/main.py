import os
import sys
import json
import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any

# Ensure backend directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, HTTPException, Depends, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from database import get_db_connection, verify_password, hash_password, init_db, is_postgres
from services.maternal_service import maternal_service
from services.child_followup import ChildFollowupService
from services.child_analytics import child_analytics_service
from services.outbreak_detector import OutbreakDetectorService

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
ML_DIR = os.path.join(BASE_DIR, "ml")
METADATA_PATH = os.path.join(ML_DIR, "model_metadata.json")

# Environment / Security
SECRET_KEY = os.getenv("SECRET_KEY", "mediconnect-insecure-dev-secret-key-change-in-production")
ALLOWED_ORIGINS_ENV = os.getenv("ALLOWED_ORIGINS") or os.getenv("CORS_ALLOWED_ORIGINS")
if ALLOWED_ORIGINS_ENV:
    ALLOWED_ORIGINS = [o.strip() for o in ALLOWED_ORIGINS_ENV.split(",") if o.strip()]
else:
    ALLOWED_ORIGINS = ["*"]

# Ensure DB is initialized
init_db()

child_followup_service = ChildFollowupService(get_db_connection)
outbreak_service = OutbreakDetectorService(get_db_connection)

app = FastAPI(
    title="MediConnect API",
    description="A Predictive EHR Companion for ASHA Workers in Low-Internet Rural Areas",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_no_cache_header(request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/static") or request.url.path == "/" or request.url.path.endswith(".html") or request.url.path.endswith(".js"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response

# -------------------------------------------------------------
# Pydantic Request Models
# -------------------------------------------------------------
class LoginRequest(BaseModel):
    username: str
    password: str

class MaternalPredictRequest(BaseModel):
    Age: float = Field(..., ge=10, le=100, description="Age in years")
    SystolicBP: float = Field(..., ge=60, le=240, description="Systolic Blood Pressure (mmHg)")
    DiastolicBP: float = Field(..., ge=40, le=160, description="Diastolic Blood Pressure (mmHg)")
    BS: float = Field(..., ge=3.0, le=35.0, description="Blood Glucose / Sugar (mmol/L)")
    BodyTemp: float = Field(..., ge=95.0, le=110.0, description="Body Temperature (Fahrenheit)")
    HeartRate: float = Field(..., ge=40, le=200, description="Heart Rate (BPM)")

class MaternalRecordCreate(BaseModel):
    client_uid: Optional[str] = None
    patient_id: int
    visit_number: int = 1
    Age: float
    SystolicBP: float
    DiastolicBP: float
    BS: float
    BodyTemp: float
    HeartRate: float
    notes: Optional[str] = ""
    recorded_by: Optional[int] = 1

class PatientCreate(BaseModel):
    client_uid: Optional[str] = None
    full_name: str
    age: int
    husband_name: Optional[str] = ""
    village: str
    phone: Optional[str] = ""
    rch_id: Optional[str] = ""
    lmp_date: Optional[str] = None
    edd_date: Optional[str] = None
    gravida: Optional[int] = 1
    notes: Optional[str] = ""
    created_by: Optional[int] = 1

class ChildCreate(BaseModel):
    client_uid: Optional[str] = None
    mother_id: Optional[int] = None
    name: str
    gender: str
    dob: str
    birth_weight: Optional[float] = None
    guardian_name: Optional[str] = ""
    village: str
    phone: Optional[str] = ""
    rch_child_id: Optional[str] = ""
    created_by: Optional[int] = 1

class ImmunizationUpdate(BaseModel):
    given_date: str
    batch_no: Optional[str] = ""
    notes: Optional[str] = ""
    status: str = "COMPLETED"
    administered_by: Optional[int] = 1

class SymptomCreate(BaseModel):
    client_uid: Optional[str] = None
    village: str
    person_name: str
    age: Optional[int] = None
    gender: Optional[str] = "Female"
    symptom_type: str
    severity: str = "Moderate"
    onset_date: str
    notes: Optional[str] = ""
    asha_id: Optional[int] = 1

class SyncPushRequest(BaseModel):
    client_device_id: Optional[str] = "WEB_CLIENT"
    user_id: Optional[int] = 1
    patients: List[Dict[str, Any]] = []
    maternal_records: List[Dict[str, Any]] = []
    children: List[Dict[str, Any]] = []
    immunizations: List[Dict[str, Any]] = []
    symptoms: List[Dict[str, Any]] = []

# -------------------------------------------------------------
# System & Auth Endpoints
# -------------------------------------------------------------
@app.get("/api/health")
def health_check():
    db_status = "connected"
    try:
        conn = get_db_connection()
        conn.execute("SELECT 1").fetchone()
        conn.close()
    except Exception as e:
        db_status = f"error: {str(e)}"

    model_status = "loaded" if maternal_service.model is not None else "not_loaded"
    db_engine = "PostgreSQL" if is_postgres() else "SQLite"

    return {
        "status": "healthy",
        "app_name": "MediConnect",
        "database": db_status,
        "database_type": db_engine,
        "maternal_model": model_status,
        "server_time": datetime.now().isoformat()
    }

@app.post("/api/auth/login")
def login(req: LoginRequest):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE username = ?", (req.username.strip(),))
    user = cursor.fetchone()
    conn.close()

    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    if not verify_password(user["password_hash"], user["salt"], req.password):
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    return {
        "success": True,
        "token": f"mc_token_{user['id']}_{int(datetime.now().timestamp())}",
        "user": {
            "id": user["id"],
            "username": user["username"],
            "full_name": user["full_name"],
            "role": user["role"],
            "village": user["village"],
            "sub_center": user["sub_center"],
            "phone": user["phone"]
        }
    }

@app.get("/api/dashboard/stats")
def get_dashboard_stats(village: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor()

    village_filter = "WHERE village = ?" if village else ""
    v_params = [village] if village else []

    cursor.execute(f"SELECT COUNT(*) FROM patients {village_filter}", v_params)
    total_mothers = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM patients WHERE high_risk_flag = 1 {'AND village = ?' if village else ''}", v_params)
    high_risk_mothers = cursor.fetchone()[0]

    cursor.execute(f"SELECT COUNT(*) FROM children {village_filter}", v_params)
    total_children = cursor.fetchone()[0]

    # Immunization stats
    imm_query = """
        SELECT 
            SUM(CASE WHEN i.status = 'COMPLETED' THEN 1 ELSE 0 END) as completed_count,
            SUM(CASE WHEN i.status = 'DUE' THEN 1 ELSE 0 END) as due_count,
            SUM(CASE WHEN i.status IN ('OVERDUE', 'FOLLOW_UP_REQUIRED') THEN 1 ELSE 0 END) as overdue_count
        FROM immunizations i
        JOIN children c ON i.child_id = c.id
    """
    if village:
        imm_query += " WHERE c.village = ?"
        cursor.execute(imm_query, (village,))
    else:
        cursor.execute(imm_query)
    imm_row = cursor.fetchone()

    # Outbreak alerts count
    outbreak_summary = outbreak_service.detect_anomalies(recent_days=7)
    active_alerts = outbreak_summary["active_alerts_count"]

    # Last sync audit
    cursor.execute("SELECT synced_at, status FROM sync_audit ORDER BY id DESC LIMIT 1")
    last_sync = cursor.fetchone()
    last_sync_str = last_sync["synced_at"] if last_sync else None

    conn.close()

    return {
        "total_mothers": total_mothers,
        "high_risk_mothers": high_risk_mothers,
        "total_children": total_children,
        "immunizations": {
            "completed": imm_row["completed_count"] or 0,
            "due": imm_row["due_count"] or 0,
            "overdue": imm_row["overdue_count"] or 0
        },
        "active_outbreak_alerts": active_alerts,
        "last_synced_at": last_sync_str,
        "data_source": "Actual SQLite Database (mediconnect.db)"
    }

# -------------------------------------------------------------
# Patients / Mothers (D1 & D2)
# -------------------------------------------------------------
@app.get("/api/patients")
def list_patients(village: Optional[str] = None, high_risk_only: bool = False, search: Optional[str] = None):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT p.*, 
               (SELECT risk_level FROM maternal_records WHERE patient_id = p.id ORDER BY id DESC LIMIT 1) as latest_risk_level,
               (SELECT recorded_at FROM maternal_records WHERE patient_id = p.id ORDER BY id DESC LIMIT 1) as latest_visit_date,
               (SELECT COUNT(*) FROM children WHERE mother_id = p.id) as children_count
        FROM patients p
        WHERE 1=1
    """
    params = []

    if village:
        query += " AND p.village = ?"
        params.append(village)

    if high_risk_only:
        query += " AND p.high_risk_flag = 1"

    if search:
        query += " AND (p.full_name LIKE ? OR p.rch_id LIKE ? OR p.phone LIKE ?)"
        term = f"%{search.strip()}%"
        params.extend([term, term, term])

    query += " ORDER BY p.high_risk_flag DESC, p.updated_at DESC"

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"patients": rows, "count": len(rows)}

@app.post("/api/patients")
def create_patient(data: PatientCreate):
    conn = get_db_connection()
    cursor = conn.cursor()

    now_iso = datetime.now().isoformat()
    client_uid = data.client_uid or f"PAT-{int(datetime.now().timestamp() * 1000)}"

    try:
        cursor.execute("""
            INSERT INTO patients (
                client_uid, full_name, age, husband_name, village, phone,
                rch_id, lmp_date, edd_date, gravida, high_risk_flag, notes,
                created_by, sync_status, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, 'SYNCED', ?, ?)
        """, (
            client_uid, data.full_name.strip(), data.age, data.husband_name,
            data.village.strip(), data.phone, data.rch_id, data.lmp_date,
            data.edd_date, data.gravida, data.notes, data.created_by, now_iso, now_iso
        ))
        patient_id = cursor.lastrowid
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.close()
        raise HTTPException(status_code=400, detail=f"Patient could not be saved: {str(e)}")

    conn.close()
    return {"success": True, "id": patient_id, "client_uid": client_uid, "message": "Mother record created successfully."}

@app.get("/api/patients/{patient_id}")
def get_patient(patient_id: int):
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM patients WHERE id = ?", (patient_id,))
    patient = cursor.fetchone()
    if not patient:
        conn.close()
        raise HTTPException(status_code=404, detail="Patient not found.")

    # Fetch maternal health history (D2)
    cursor.execute("""
        SELECT * FROM maternal_records 
        WHERE patient_id = ? 
        ORDER BY visit_number ASC, id ASC
    """, (patient_id,))
    visits = [dict(r) for r in cursor.fetchall()]

    # Fetch children (D3)
    cursor.execute("""
        SELECT * FROM children 
        WHERE mother_id = ? 
        ORDER BY dob DESC
    """, (patient_id,))
    children = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return {
        "patient": dict(patient),
        "visits": visits,
        "children": children
    }

# -------------------------------------------------------------
# Maternal Health Risk Prediction & Records (ML Module)
# -------------------------------------------------------------
@app.post("/api/maternal/predict")
def predict_maternal_risk(req: MaternalPredictRequest):
    """
    Inference endpoint: uses the genuine trained model artifact on exact 6 features.
    """
    try:
        result = maternal_service.predict_risk(
            age=req.Age,
            systolic_bp=req.SystolicBP,
            diastolic_bp=req.DiastolicBP,
            bs=req.BS,
            body_temp=req.BodyTemp,
            heart_rate=req.HeartRate
        )
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Prediction error: {str(e)}")

@app.post("/api/maternal/records")
def record_maternal_visit(data: MaternalRecordCreate):
    """
    Records an authentic clinical ANC visit for a mother.
    Runs the genuine model to predict risk and saves the result to D2 Maternal Health Data.
    """
    prediction = maternal_service.predict_risk(
        age=data.Age,
        systolic_bp=data.SystolicBP,
        diastolic_bp=data.DiastolicBP,
        bs=data.BS,
        body_temp=data.BodyTemp,
        heart_rate=data.HeartRate
    )

    risk_level = prediction["risk_level"]
    confidence = prediction["confidence"]
    model_version = prediction["model_version"]

    conn = get_db_connection()
    cursor = conn.cursor()

    now_iso = datetime.now().isoformat()
    client_uid = data.client_uid or f"MR-{data.patient_id}-{int(datetime.now().timestamp() * 1000)}"

    cursor.execute("""
        INSERT INTO maternal_records (
            client_uid, patient_id, visit_number, age, systolic_bp, diastolic_bp,
            blood_sugar, body_temp, heart_rate, risk_level, confidence,
            model_version, action_notes, recorded_by, sync_status, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SYNCED', ?)
    """, (
        client_uid, data.patient_id, data.visit_number, data.Age, data.SystolicBP,
        data.DiastolicBP, data.BS, data.BodyTemp, data.HeartRate, risk_level,
        confidence, model_version, data.notes, data.recorded_by, now_iso
    ))
    record_id = cursor.lastrowid

    # If High Risk, flag patient
    if risk_level == "High Risk":
        cursor.execute("UPDATE patients SET high_risk_flag = 1, updated_at = ? WHERE id = ?", (now_iso, data.patient_id))
    else:
        cursor.execute("UPDATE patients SET updated_at = ? WHERE id = ?", (now_iso, data.patient_id))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "record_id": record_id,
        "client_uid": client_uid,
        "prediction": prediction
    }

# -------------------------------------------------------------
# Children & Immunization (D3)
# -------------------------------------------------------------
@app.get("/api/children")
def list_children(village: Optional[str] = None, mother_id: Optional[int] = None):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
        SELECT c.*, p.full_name as mother_name,
               (SELECT COUNT(*) FROM immunizations WHERE child_id = c.id AND status = 'COMPLETED') as completed_vaccines,
               (SELECT COUNT(*) FROM immunizations WHERE child_id = c.id AND status IN ('OVERDUE', 'FOLLOW_UP_REQUIRED')) as overdue_vaccines
        FROM children c
        LEFT JOIN patients p ON c.mother_id = p.id
        WHERE 1=1
    """
    params = []
    if village:
        query += " AND c.village = ?"
        params.append(village)
    if mother_id:
        query += " AND c.mother_id = ?"
        params.append(mother_id)

    query += " ORDER BY c.created_at DESC"
    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"children": rows, "count": len(rows)}

@app.post("/api/children")
def create_child(data: ChildCreate):
    conn = get_db_connection()
    cursor = conn.cursor()

    now_iso = datetime.now().isoformat()
    client_uid = data.client_uid or f"CH-{int(datetime.now().timestamp() * 1000)}"

    cursor.execute("""
        INSERT INTO children (
            client_uid, mother_id, name, gender, dob, birth_weight,
            guardian_name, village, phone, rch_child_id, created_by,
            sync_status, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SYNCED', ?, ?)
    """, (
        client_uid, data.mother_id, data.name.strip(), data.gender, data.dob,
        data.birth_weight, data.guardian_name, data.village.strip(), data.phone,
        data.rch_child_id, data.created_by, now_iso, now_iso
    ))
    child_id = cursor.lastrowid

    # Automatically generate standard UIP vaccination schedule for this child
    dob = datetime.strptime(data.dob, "%Y-%m-%d")
    now = datetime.now()

    uip_schedule = [
        ("BCG", 1, 0),
        ("Hep B (Birth)", 1, 0),
        ("OPV (Birth)", 0, 0),
        ("Pentavalent", 1, 42),
        ("OPV", 1, 42),
        ("Pentavalent", 2, 70),
        ("OPV", 2, 70),
        ("Pentavalent", 3, 98),
        ("OPV", 3, 98),
        ("Measles-Rubella (MR)", 1, 274),
        ("Vitamin A", 1, 274),
        ("DPT Booster", 1, 485)
    ]

    for vname, dose, days in uip_schedule:
        due_date = dob + timedelta(days=days)
        due_str = due_date.strftime("%Y-%m-%d")
        
        if now > due_date + timedelta(days=28):
            status_val = "FOLLOW_UP_REQUIRED"
        elif now >= due_date:
            status_val = "DUE"
        else:
            status_val = "SCHEDULED"

        cursor.execute("""
            INSERT INTO immunizations (
                client_uid, child_id, vaccine_name, dose_number, due_date,
                status, administered_by, sync_status, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'SYNCED', ?)
        """, (f"IMM-{child_id}-{vname[:3]}-{dose}", child_id, vname, dose, due_str, status_val, data.created_by, now_iso))

    conn.commit()
    conn.close()

    return {"success": True, "id": child_id, "client_uid": client_uid, "message": "Child registered and UIP schedule initialized."}

@app.get("/api/children/{child_id_or_uid}")
def get_child_details(child_id_or_uid: str):
    conn = get_db_connection()
    cursor = conn.cursor()

    if child_id_or_uid.isdigit():
        cursor.execute("""
            SELECT c.*, p.full_name as mother_name, p.village as mother_village
            FROM children c
            LEFT JOIN patients p ON c.mother_id = p.id
            WHERE c.id = ? OR c.client_uid = ?
        """, (int(child_id_or_uid), child_id_or_uid))
    else:
        cursor.execute("""
            SELECT c.*, p.full_name as mother_name, p.village as mother_village
            FROM children c
            LEFT JOIN patients p ON c.mother_id = p.id
            WHERE c.client_uid = ?
        """, (child_id_or_uid,))
    
    child = cursor.fetchone()
    if not child:
        conn.close()
        raise HTTPException(status_code=404, detail="Child record not found.")

    ch_id = child["id"]
    cursor.execute("""
        SELECT * FROM immunizations 
        WHERE child_id = ? 
        ORDER BY due_date ASC
    """, (ch_id,))
    immunizations = [dict(r) for r in cursor.fetchall()]

    conn.close()
    return {"child": dict(child), "immunizations": immunizations}

@app.put("/api/immunizations/{imm_id}")
def update_immunization(imm_id: int, data: ImmunizationUpdate):
    conn = get_db_connection()
    cursor = conn.cursor()

    now_iso = datetime.now().isoformat()
    cursor.execute("""
        UPDATE immunizations
        SET given_date = ?, batch_no = ?, notes = ?, status = ?,
            administered_by = ?, recorded_at = ?, sync_status = 'SYNCED'
        WHERE id = ?
    """, (data.given_date, data.batch_no, data.notes, data.status, data.administered_by, now_iso, imm_id))

    conn.commit()
    conn.close()
    return {"success": True, "message": "Immunization record updated."}

@app.get("/api/immunizations/follow-up")
def get_immunization_followup(village: Optional[str] = None):
    """
    Returns weekly actionable follow-up list for ASHA workers.
    Rule-based tracking from SQL child records without fake ML claims.
    """
    return child_followup_service.get_actionable_followup_list(village_filter=village)

# -------------------------------------------------------------
# Symptom Logging & Outbreak Early Warning (D4)
# -------------------------------------------------------------
@app.get("/api/symptoms")
def list_symptoms(village: Optional[str] = None, limit: int = 50):
    conn = get_db_connection()
    cursor = conn.cursor()

    query = "SELECT * FROM symptom_logs WHERE 1=1"
    params = []
    if village:
        query += " AND village = ?"
        params.append(village)
    query += " ORDER BY onset_date DESC, id DESC LIMIT ?"
    params.append(limit)

    cursor.execute(query, params)
    rows = [dict(r) for r in cursor.fetchall()]
    conn.close()
    return {"symptoms": rows, "count": len(rows)}

@app.post("/api/symptoms")
def create_symptom(data: SymptomCreate):
    conn = get_db_connection()
    cursor = conn.cursor()

    now_iso = datetime.now().isoformat()
    client_uid = data.client_uid or f"SYM-{int(datetime.now().timestamp() * 1000)}"

    cursor.execute("""
        INSERT INTO symptom_logs (
            client_uid, village, person_name, age, gender, symptom_type,
            severity, onset_date, asha_id, notes, sync_status, recorded_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SYNCED', ?)
    """, (
        client_uid, data.village.strip(), data.person_name.strip(), data.age,
        data.gender, data.symptom_type, data.severity, data.onset_date,
        data.asha_id, data.notes, now_iso
    ))
    sym_id = cursor.lastrowid
    conn.commit()
    conn.close()

    # Re-evaluate outbreak alert status
    alerts_data = outbreak_service.detect_anomalies(recent_days=7)

    return {
        "success": True,
        "id": sym_id,
        "client_uid": client_uid,
        "outbreak_alert_status": alerts_data["active_alerts_count"] > 0,
        "message": "Symptom case logged successfully."
    }

@app.get("/api/outbreak/alerts")
def get_outbreak_alerts():
    """
    Returns village-level symptom monitoring, anomaly detection,
    and early warning notifications.
    """
    return outbreak_service.detect_anomalies(recent_days=7, baseline_days=30)

# -------------------------------------------------------------
# Aggregate Child Coverage Analytics (From XLS Dataset)
# -------------------------------------------------------------
@app.get("/api/analytics/coverage")
def get_coverage_analytics():
    """
    Returns aggregate district and state coverage statistics, dropout rate metrics,
    and variable dictionary from the verified XLS dataset files.
    """
    return child_analytics_service.get_coverage_summary()

# -------------------------------------------------------------
# Model Status & Retraining (Development / Admin)
# -------------------------------------------------------------
@app.get("/api/model/status")
def get_model_status():
    if not os.path.exists(METADATA_PATH):
        raise HTTPException(status_code=404, detail="Model metadata not found. Please train model.")
    with open(METADATA_PATH, "r") as f:
        meta = json.load(f)
    return meta

@app.post("/api/model/retrain")
def retrain_model():
    from ml.train_maternal_model import train_and_evaluate
    try:
        updated_meta = train_and_evaluate()
        maternal_service.load_model()
        return {
            "success": True,
            "message": "Model retrained and reloaded successfully.",
            "metrics": updated_meta["evaluation_metrics"],
            "model_version": updated_meta["model_version"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Retraining failed: {str(e)}")

# -------------------------------------------------------------
# Offline Synchronization Center
# -------------------------------------------------------------
@app.post("/api/sync/push")
def sync_push(batch: SyncPushRequest):
    """
    Idempotent synchronization gateway for offline ASHA field clients.
    Accepts client-side cached records and merges them cleanly without duplication.
    """
    conn = get_db_connection()
    cursor = conn.cursor()

    now_iso = datetime.now().isoformat()
    processed_counts = {
        "patients": 0,
        "maternal_records": 0,
        "children": 0,
        "immunizations": 0,
        "symptoms": 0
    }

    # 1. Sync Patients
    for p in batch.patients:
        c_uid = p.get("client_uid")
        if not c_uid:
            continue
        cursor.execute("SELECT id FROM patients WHERE client_uid = ?", (c_uid,))
        existing = cursor.fetchone()
        if not existing:
            cursor.execute("""
                INSERT INTO patients (
                    client_uid, full_name, age, husband_name, village, phone,
                    rch_id, lmp_date, edd_date, gravida, high_risk_flag, notes,
                    created_by, sync_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SYNCED', ?, ?)
            """, (
                c_uid, p["full_name"], p.get("age", 25), p.get("husband_name", ""),
                p["village"], p.get("phone", ""), p.get("rch_id", ""), p.get("lmp_date"),
                p.get("edd_date"), p.get("gravida", 1), p.get("high_risk_flag", 0),
                p.get("notes", ""), batch.user_id, p.get("created_at", now_iso), now_iso
            ))
            processed_counts["patients"] += 1

    # 2. Sync Maternal Records
    for mr in batch.maternal_records:
        c_uid = mr.get("client_uid")
        if not c_uid:
            continue
        cursor.execute("SELECT id FROM maternal_records WHERE client_uid = ?", (c_uid,))
        if not cursor.fetchone():
            # If patient_client_uid is provided, resolve real id
            p_id = mr.get("patient_id")
            if mr.get("patient_client_uid"):
                cursor.execute("SELECT id FROM patients WHERE client_uid = ?", (mr["patient_client_uid"],))
                p_row = cursor.fetchone()
                if p_row:
                    p_id = p_row["id"]

            if p_id:
                # Run real prediction if missing
                risk_lvl = mr.get("risk_level")
                conf = mr.get("confidence", 0.8)
                if not risk_lvl:
                    pred = maternal_service.predict_risk(
                        age=mr["Age"], systolic_bp=mr["SystolicBP"],
                        diastolic_bp=mr["DiastolicBP"], bs=mr["BS"],
                        body_temp=mr["BodyTemp"], heart_rate=mr["HeartRate"]
                    )
                    risk_lvl = pred["risk_level"]
                    conf = pred["confidence"]

                cursor.execute("""
                    INSERT INTO maternal_records (
                        client_uid, patient_id, visit_number, age, systolic_bp,
                        diastolic_bp, blood_sugar, body_temp, heart_rate, risk_level,
                        confidence, model_version, action_notes, recorded_by,
                        sync_status, recorded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'v1.0.0', ?, ?, 'SYNCED', ?)
                """, (
                    c_uid, p_id, mr.get("visit_number", 1), mr["Age"], mr["SystolicBP"],
                    mr["DiastolicBP"], mr["BS"], mr["BodyTemp"], mr["HeartRate"],
                    risk_lvl, conf, mr.get("notes", ""), batch.user_id, mr.get("recorded_at", now_iso)
                ))
                processed_counts["maternal_records"] += 1
                if risk_lvl == "High Risk":
                    cursor.execute("UPDATE patients SET high_risk_flag = 1 WHERE id = ?", (p_id,))

    # 3. Sync Children
    for ch in batch.children:
        c_uid = ch.get("client_uid")
        if not c_uid:
            continue
        cursor.execute("SELECT id FROM children WHERE client_uid = ?", (c_uid,))
        if not cursor.fetchone():
            m_id = ch.get("mother_id")
            if ch.get("mother_client_uid"):
                cursor.execute("SELECT id FROM patients WHERE client_uid = ?", (ch["mother_client_uid"],))
                mrow = cursor.fetchone()
                if mrow:
                    m_id = mrow["id"]

            cursor.execute("""
                INSERT INTO children (
                    client_uid, mother_id, name, gender, dob, birth_weight,
                    guardian_name, village, phone, rch_child_id, created_by,
                    sync_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SYNCED', ?, ?)
            """, (
                c_uid, m_id, ch["name"], ch["gender"], ch["dob"],
                ch.get("birth_weight"), ch.get("guardian_name", ""),
                ch["village"], ch.get("phone", ""), ch.get("rch_child_id", ""),
                batch.user_id, ch.get("created_at", now_iso), now_iso
            ))
            ch_new_id = cursor.lastrowid
            processed_counts["children"] += 1

            # Auto-generate UIP schedule for synced child if not sent separately
            dob_val = ch.get("dob")
            if dob_val:
                try:
                    c_dob = datetime.strptime(dob_val, "%Y-%m-%d")
                    now_dt = datetime.now()
                    uip_sched = [
                        ("BCG", 1, 0), ("Hep B (Birth)", 1, 0), ("OPV (Birth)", 0, 0),
                        ("Pentavalent", 1, 42), ("OPV", 1, 42), ("Pentavalent", 2, 70),
                        ("OPV", 2, 70), ("Pentavalent", 3, 98), ("OPV", 3, 98),
                        ("Measles-Rubella (MR)", 1, 274), ("Vitamin A", 1, 274),
                        ("DPT Booster", 1, 485)
                    ]
                    for vname, dose, days in uip_sched:
                        due_dt = c_dob + timedelta(days=days)
                        due_str = due_dt.strftime("%Y-%m-%d")
                        st = "FOLLOW_UP_REQUIRED" if now_dt > due_dt + timedelta(days=28) else ("DUE" if now_dt >= due_dt else "SCHEDULED")
                        cursor.execute("""
                            INSERT OR IGNORE INTO immunizations (
                                client_uid, child_id, vaccine_name, dose_number, due_date,
                                status, administered_by, sync_status, recorded_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, 'SYNCED', ?)
                        """, (f"IMM-{ch_new_id}-{vname[:3]}-{dose}", ch_new_id, vname, dose, due_str, st, batch.user_id, now_iso))
                except Exception:
                    pass

    # 4. Sync Immunizations
    for im in batch.immunizations:
        c_uid = im.get("client_uid")
        if not c_uid:
            continue
        cursor.execute("SELECT id, status, given_date FROM immunizations WHERE client_uid = ?", (c_uid,))
        existing = cursor.fetchone()
        if existing:
            # Update status if completed offline and not already recorded as completed
            if im.get("status") == "COMPLETED" and im.get("given_date"):
                if existing["status"] != "COMPLETED" or existing["given_date"] != im.get("given_date"):
                    cursor.execute("""
                        UPDATE immunizations 
                        SET status = 'COMPLETED', given_date = ?, batch_no = ?, sync_status = 'SYNCED'
                        WHERE id = ?
                    """, (im["given_date"], im.get("batch_no", ""), existing["id"]))
                    processed_counts["immunizations"] += 1
        else:
            ch_id = im.get("child_id")
            if im.get("child_client_uid"):
                cursor.execute("SELECT id FROM children WHERE client_uid = ?", (im["child_client_uid"],))
                crow = cursor.fetchone()
                if crow:
                    ch_id = crow["id"]
            if ch_id:
                cursor.execute("""
                    INSERT INTO immunizations (
                        client_uid, child_id, vaccine_name, dose_number, due_date,
                        given_date, status, batch_no, notes, administered_by,
                        sync_status, recorded_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SYNCED', ?)
                """, (
                    c_uid, ch_id, im["vaccine_name"], im.get("dose_number", 1),
                    im["due_date"], im.get("given_date"), im["status"],
                    im.get("batch_no", ""), im.get("notes", ""), batch.user_id,
                    im.get("recorded_at", now_iso)
                ))
                processed_counts["immunizations"] += 1

    # 5. Sync Symptoms
    for sym in batch.symptoms:
        c_uid = sym.get("client_uid")
        if not c_uid:
            continue
        cursor.execute("SELECT id FROM symptom_logs WHERE client_uid = ?", (c_uid,))
        if not cursor.fetchone():
            cursor.execute("""
                INSERT INTO symptom_logs (
                    client_uid, village, person_name, age, gender, symptom_type,
                    severity, onset_date, asha_id, notes, sync_status, recorded_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'SYNCED', ?)
            """, (
                c_uid, sym["village"], sym["person_name"], sym.get("age"),
                sym.get("gender", "Female"), sym["symptom_type"],
                sym.get("severity", "Moderate"), sym["onset_date"],
                batch.user_id, sym.get("notes", ""), sym.get("recorded_at", now_iso)
            ))
            processed_counts["symptoms"] += 1

    total_records = sum(processed_counts.values())

    # Log to sync audit
    cursor.execute("""
        INSERT INTO sync_audit (user_id, client_device_id, records_pushed, sync_type, status, synced_at)
        VALUES (?, ?, ?, 'PUSH', 'SUCCESS', ?)
    """, (batch.user_id, batch.client_device_id, total_records, now_iso))

    conn.commit()
    conn.close()

    return {
        "success": True,
        "total_records_synced": total_records,
        "details": processed_counts,
        "synced_at": now_iso,
        "status": "SYNCED"
    }

@app.post("/api/admin/clean-records")
def clean_records():
    """
    Cleans all patient, maternal, child, immunization, and symptom records for a fresh start,
    while keeping authorized user accounts intact.
    Supports both PostgreSQL and SQLite.
    """
    conn = get_db_connection()
    cursor = conn.cursor()
    if is_postgres():
        cursor.execute("TRUNCATE TABLE immunizations, children, maternal_records, patients, symptom_logs, sync_audit RESTART IDENTITY CASCADE;")
    else:
        cursor.execute("PRAGMA foreign_keys = OFF")
        tables = ["immunizations", "children", "maternal_records", "patients", "symptom_logs", "sync_audit"]
        for table in tables:
            cursor.execute(f"DELETE FROM {table}")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('immunizations', 'children', 'maternal_records', 'patients', 'symptom_logs', 'sync_audit')")
        cursor.execute("PRAGMA foreign_keys = ON")
    conn.commit()
    conn.close()
    return {"success": True, "message": "All clinical, child, maternal, and surveillance records cleared successfully."}

# -------------------------------------------------------------
# Static Frontend Serving
# -------------------------------------------------------------
NO_CACHE_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0"
}

if os.path.exists(FRONTEND_DIR):
    app.mount("/static", StaticFiles(directory=FRONTEND_DIR), name="static")

    @app.get("/")
    def serve_index():
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"), headers=NO_CACHE_HEADERS)

    @app.get("/sw.js")
    def serve_sw():
        sw_file = os.path.join(FRONTEND_DIR, "sw.js")
        if os.path.exists(sw_file):
            return FileResponse(
                sw_file,
                media_type="application/javascript",
                headers={**NO_CACHE_HEADERS, "Service-Worker-Allowed": "/"}
            )
        raise HTTPException(status_code=404, detail="Service worker not found")

    @app.get("/manifest.json")
    def serve_manifest():
        manifest_file = os.path.join(FRONTEND_DIR, "manifest.json")
        if os.path.exists(manifest_file):
            return FileResponse(
                manifest_file,
                media_type="application/manifest+json",
                headers=NO_CACHE_HEADERS
            )
        raise HTTPException(status_code=404, detail="Manifest not found")

    @app.get("/{full_path:path}")
    def serve_spa(full_path: str):
        file_path = os.path.join(FRONTEND_DIR, full_path)
        if os.path.exists(file_path) and os.path.isfile(file_path):
            return FileResponse(file_path, headers=NO_CACHE_HEADERS)
        return FileResponse(os.path.join(FRONTEND_DIR, "index.html"), headers=NO_CACHE_HEADERS)

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=False)
