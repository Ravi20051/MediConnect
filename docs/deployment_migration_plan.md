# MediConnect — Multi-User Deployment & PostgreSQL Migration Plan

This document outlines the technical pathway for transitioning MediConnect from its **standalone SQLite college/field prototype** to a **scalable, multi-tenant central PostgreSQL deployment**.

---

## 1. Architectural Context

### Current Prototype Architecture (College / Local Field Sandbox)
```
ASHA Worker Device (Web Browser)
       │ (HTTP via localhost:8000)
       ▼
Local FastAPI Server (Single Process, Uvicorn)
       ├── Machine Learning: ml/maternal_risk_model.joblib (RandomForestClassifier in-memory)
       └── Database: mediconnect.db (Local SQLite 3 with WAL mode)
```

### Target Multi-User Deployment Architecture
```
ASHA Worker Smartphone / Tablet / Laptop
       │ (Responsive Browser Web Application)
       │ (Intermittent Field Internet: 2G / 3G / 4G / Wi-Fi)
       ▼
Reverse Proxy & TLS Termination (Nginx / Caddy / Cloudflare)
       ▼
Hosted FastAPI Application Servers (Gunicorn / Uvicorn Workers)
       ├── Machine Learning Service: ml/maternal_risk_model.joblib
       └── Central Database Connection Pool (SQLAlchemy / psycopg3 / asyncpg)
                   ▼
       Central PostgreSQL 15+ Cluster (Cloud Hosted: RDS / Supabase / Neon / Self-hosted)
                   ├── 7 Relational Tables with Foreign Keys & Client_UID Uniqueness
                   └── sync_audit Table for Field Auditing
```

---

## 2. Table-by-Table Schema Confirmation (All 7 Tables)

All seven tables currently defined in SQLite are confirmed and mapped to PostgreSQL data types:

| # | Table Name | Prototype (SQLite) | Target (PostgreSQL) | Primary Key / Constraints |
|---|---|---|---|---|
| 1 | **`users`** | `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL PRIMARY KEY` | `username UNIQUE`, hashed credentials |
| 2 | **`patients`** | `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL PRIMARY KEY` | `client_uid UNIQUE`, FK `created_by` |
| 3 | **`maternal_records`**| `INTEGER PRIMARY KEY AUTOINCREMENT`| `SERIAL PRIMARY KEY` | `client_uid UNIQUE`, FK `patient_id` (CASCADE) |
| 4 | **`children`** | `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL PRIMARY KEY` | `client_uid UNIQUE`, FK `mother_id` (SET NULL) |
| 5 | **`immunizations`** | `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL PRIMARY KEY` | `client_uid UNIQUE`, FK `child_id` (CASCADE) |
| 6 | **`symptom_logs`** | `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL PRIMARY KEY` | `client_uid UNIQUE`, FK `asha_id` (SET NULL) |
| 7 | **`sync_audit`** | `INTEGER PRIMARY KEY AUTOINCREMENT` | `SERIAL PRIMARY KEY` | Audit ledger, FK `user_id` |

Full DDL script is available at: [docs/postgres_schema.sql](file:///d:/Mediconnect%20app/docs/postgres_schema.sql).

---

## 3. SQLite-Specific SQL Dependencies & Code Changes

During backend migration, the following SQLite-specific behaviors must be updated:

### 1. Parameter Placeholders
- **SQLite**: Uses `?` (qmark style), e.g., `SELECT * FROM patients WHERE client_uid = ?`.
- **PostgreSQL**: Uses `%s` (pyformat with `psycopg`) or `$1, $2` (with `asyncpg`).
- **Resolution**: Use SQLAlchemy Core or an abstraction adapter that translates parameter styles dynamically based on `DB_TYPE`.

### 2. Auto-Incrementing Primary Keys & Sequence Resets
- **SQLite**: `AUTOINCREMENT` and `DELETE FROM sqlite_sequence WHERE name = '...'`.
- **PostgreSQL**: `SERIAL` or `IDENTITY` columns, and `ALTER SEQUENCE <table_name>_id_seq RESTART WITH 1`.

### 3. Insert Idempotency Syntax
- **SQLite**:
  ```sql
  INSERT OR IGNORE INTO immunizations (client_uid, child_id, ...) VALUES (?, ?, ...);
  ```
- **PostgreSQL**:
  ```sql
  INSERT INTO immunizations (client_uid, child_id, ...) VALUES (%s, %s, ...)
  ON CONFLICT (client_uid) DO NOTHING;
  ```

### 4. Pragmas
- **SQLite**:
  ```python
  conn.execute("PRAGMA foreign_keys = ON")
  conn.execute("PRAGMA journal_mode = WAL")
  ```
- **PostgreSQL**: Foreign keys and Write-Ahead Logging (WAL) are built-in server features; remove PRAGMA calls when running against PostgreSQL.

### 5. Last Insert ID Retrieval
- **SQLite**: `cursor.lastrowid`
- **PostgreSQL**: Add `RETURNING id` to the `INSERT` statement, e.g., `INSERT INTO patients (...) VALUES (...) RETURNING id;` and read `cursor.fetchone()[0]`.

---

## 4. Deployment Environment Variables

Configure the following environment variables on the hosted server (e.g., in `.env` or container settings):

```env
# Application Settings
ENVIRONMENT=production
SECRET_KEY=generate_a_secure_random_64_character_hex_string
ALLOWED_ORIGINS=https://mediconnect.ruralhealth.gov.in

# Database Configuration
DB_TYPE=postgres
DATABASE_URL=postgresql://mediconnect_admin:StrongPassword123@db.internal:5432/mediconnect_prod
DB_POOL_MIN=5
DB_POOL_MAX=20

# Host / Server Settings
HOST=0.0.0.0
PORT=8000
WORKERS=4
```

---

## 5. Multi-User Concurrency & Offline Sync Integrity

1. **Client-Side UID Generation**:
   Every offline record created on an ASHA tablet generates a cryptographically random or timestamped `client_uid` (e.g., `PAT-LOCAL-1727712345678-ABCD`).
2. **Idempotent Batch Processing**:
   When connectivity returns, `POST /api/sync/push` processes records within a single database transaction. Existing `client_uid` records are skipped (`ON CONFLICT DO NOTHING`), preventing duplicate mothers, children, or immunization entries.
3. **Connection Pooling**:
   In PostgreSQL, concurrent ASHA workers are served via a database connection pool (`psycopg_pool` or SQLAlchemy queue pool) ensuring high throughput without exhausting database connections.
4. **Permanent Audit Logging**:
   Every sync operation creates an entry in `sync_audit` recording device ID, user ID, total records pushed, and server timestamp.
5. **ML Model Loading**:
   The trained `ml/maternal_risk_model.joblib` artifact (StandardScaler -> RandomForestClassifier) is loaded once into server memory on application startup (`@app.on_event("startup")` or lifespan context), serving stateless sub-millisecond inference across all concurrent worker requests.
