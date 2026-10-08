-- ============================================================================
-- MediConnect — PostgreSQL Central Database Target Schema
-- Target Multi-User Deployment Schema for Production Migration
-- ============================================================================

-- Enable pgcrypto extension if needed for server-side UUIDs or cryptographic functions
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ----------------------------------------------------------------------------
-- 1. USERS TABLE (ASHA Workers, ANM Supervisors, Block Medical Officers)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(100) UNIQUE NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    role VARCHAR(50) NOT NULL DEFAULT 'asha_worker', -- 'asha_worker', 'supervisor', 'admin'
    village VARCHAR(100) NOT NULL,
    sub_center VARCHAR(150) DEFAULT '',
    phone VARCHAR(20) DEFAULT '',
    password_hash VARCHAR(255) NOT NULL,
    salt VARCHAR(64) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_users_username ON users(username);
CREATE INDEX IF NOT EXISTS idx_users_village ON users(village);

-- ----------------------------------------------------------------------------
-- 2. PATIENTS TABLE (Mothers / Pregnant Women - D1 Patient Store)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS patients (
    id SERIAL PRIMARY KEY,
    client_uid VARCHAR(120) UNIQUE,
    full_name VARCHAR(255) NOT NULL,
    age INTEGER NOT NULL CHECK (age >= 10 AND age <= 70),
    husband_name VARCHAR(255) DEFAULT '',
    village VARCHAR(100) NOT NULL,
    phone VARCHAR(20) DEFAULT '',
    rch_id VARCHAR(100) DEFAULT '',
    lmp_date DATE,
    edd_date DATE,
    gravida INTEGER DEFAULT 1,
    high_risk_flag INTEGER DEFAULT 0,
    notes TEXT DEFAULT '',
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    sync_status VARCHAR(20) DEFAULT 'SYNCED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_patients_client_uid ON patients(client_uid);
CREATE INDEX IF NOT EXISTS idx_patients_village ON patients(village);
CREATE INDEX IF NOT EXISTS idx_patients_high_risk ON patients(high_risk_flag);

-- ----------------------------------------------------------------------------
-- 3. MATERNAL RECORDS TABLE (ANC Clinical Visits & ML Predictions - D2 Store)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS maternal_records (
    id SERIAL PRIMARY KEY,
    client_uid VARCHAR(120) UNIQUE,
    patient_id INTEGER NOT NULL REFERENCES patients(id) ON DELETE CASCADE,
    visit_number INTEGER DEFAULT 1,
    age INTEGER NOT NULL,
    systolic_bp INTEGER NOT NULL,
    diastolic_bp INTEGER NOT NULL,
    blood_sugar REAL NOT NULL,
    body_temp REAL NOT NULL,
    heart_rate INTEGER NOT NULL,
    risk_level VARCHAR(50) NOT NULL, -- 'Low Risk', 'Medium Risk', 'High Risk'
    confidence REAL,                 -- Predicted class probability
    model_version VARCHAR(50) NOT NULL DEFAULT 'v1.0.0',
    action_notes TEXT DEFAULT '',
    recorded_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    sync_status VARCHAR(20) DEFAULT 'SYNCED',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_maternal_client_uid ON maternal_records(client_uid);
CREATE INDEX IF NOT EXISTS idx_maternal_patient_id ON maternal_records(patient_id);
CREATE INDEX IF NOT EXISTS idx_maternal_risk_level ON maternal_records(risk_level);

-- ----------------------------------------------------------------------------
-- 4. CHILDREN TABLE (D3 Child Store)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS children (
    id SERIAL PRIMARY KEY,
    client_uid VARCHAR(120) UNIQUE,
    mother_id INTEGER REFERENCES patients(id) ON DELETE SET NULL,
    name VARCHAR(255) NOT NULL,
    gender VARCHAR(20) NOT NULL,
    dob DATE NOT NULL,
    birth_weight REAL,
    guardian_name VARCHAR(255) DEFAULT '',
    village VARCHAR(100) NOT NULL,
    phone VARCHAR(20) DEFAULT '',
    rch_child_id VARCHAR(100) DEFAULT '',
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    sync_status VARCHAR(20) DEFAULT 'SYNCED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_children_client_uid ON children(client_uid);
CREATE INDEX IF NOT EXISTS idx_children_mother_id ON children(mother_id);
CREATE INDEX IF NOT EXISTS idx_children_village ON children(village);

-- ----------------------------------------------------------------------------
-- 5. IMMUNIZATIONS TABLE (UIP Vaccination Tracking - D3 Store)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS immunizations (
    id SERIAL PRIMARY KEY,
    client_uid VARCHAR(120) UNIQUE,
    child_id INTEGER NOT NULL REFERENCES children(id) ON DELETE CASCADE,
    vaccine_name VARCHAR(100) NOT NULL,
    dose_number INTEGER NOT NULL DEFAULT 1,
    due_date DATE NOT NULL,
    given_date DATE,
    status VARCHAR(50) NOT NULL, -- 'COMPLETED', 'DUE', 'OVERDUE', 'FOLLOW_UP_REQUIRED'
    batch_no VARCHAR(100) DEFAULT '',
    notes TEXT DEFAULT '',
    administered_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    sync_status VARCHAR(20) DEFAULT 'SYNCED',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_immunizations_client_uid ON immunizations(client_uid);
CREATE INDEX IF NOT EXISTS idx_immunizations_child_id ON immunizations(child_id);
CREATE INDEX IF NOT EXISTS idx_immunizations_status ON immunizations(status);
CREATE INDEX IF NOT EXISTS idx_immunizations_due_date ON immunizations(due_date);

-- ----------------------------------------------------------------------------
-- 6. SYMPTOM LOGS TABLE (Syndromic Surveillance for Outbreak Early Warning - D4 Store)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS symptom_logs (
    id SERIAL PRIMARY KEY,
    client_uid VARCHAR(120) UNIQUE,
    village VARCHAR(100) NOT NULL,
    person_name VARCHAR(255) NOT NULL,
    age INTEGER,
    gender VARCHAR(20),
    symptom_type VARCHAR(100) NOT NULL, -- 'Fever', 'Diarrhea/Vomiting', 'Acute Respiratory/Cough', 'Skin Rash/Measles', 'Jaundice', 'Other'
    severity VARCHAR(50) NOT NULL DEFAULT 'Moderate', -- 'Mild', 'Moderate', 'Severe'
    onset_date DATE NOT NULL,
    asha_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    notes TEXT DEFAULT '',
    sync_status VARCHAR(20) DEFAULT 'SYNCED',
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_symptoms_client_uid ON symptom_logs(client_uid);
CREATE INDEX IF NOT EXISTS idx_symptoms_village ON symptom_logs(village);
CREATE INDEX IF NOT EXISTS idx_symptoms_onset_date ON symptom_logs(onset_date);
CREATE INDEX IF NOT EXISTS idx_symptoms_type ON symptom_logs(symptom_type);

-- ----------------------------------------------------------------------------
-- 7. SYNC AUDIT TABLE (Offline Synchronization Ledger - D6 Store)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS sync_audit (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    client_device_id VARCHAR(100) DEFAULT '',
    records_pushed INTEGER DEFAULT 0,
    sync_type VARCHAR(50) DEFAULT 'PUSH',
    status VARCHAR(50) NOT NULL, -- 'SUCCESS', 'FAILED'
    synced_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_sync_audit_user_id ON sync_audit(user_id);
CREATE INDEX IF NOT EXISTS idx_sync_audit_synced_at ON sync_audit(synced_at);
