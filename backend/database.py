import sqlite3
import os
import re
import hashlib
import secrets
from datetime import datetime

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_PATH = os.path.join(BASE_DIR, "mediconnect.db")

def is_postgres() -> bool:
    """
    Checks if a PostgreSQL database URL is configured via DATABASE_URL.
    """
    db_url = os.getenv("DATABASE_URL", "").strip()
    return db_url.startswith("postgres://") or db_url.startswith("postgresql://")

class DictRow(dict):
    """
    Dictionary-like row adapter that supports both column-name access (row['full_name'])
    and zero-based integer index access (row[0]), perfectly mirroring sqlite3.Row across engines.
    """
    def __init__(self, data, tuple_data=None):
        super().__init__(data)
        self._tuple = tuple_data if tuple_data is not None else tuple(data.values())

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._tuple[key]
        return super().__getitem__(key)

    def get(self, key, default=None):
        if isinstance(key, int):
            try:
                return self._tuple[key]
            except IndexError:
                return default
        return super().get(key, default)

class PostgresCursorWrapper:
    """
    Wraps a psycopg2 cursor to provide transparent cross-compatibility
    with SQLite idioms used in the MediConnect backend.
    """
    def __init__(self, raw_cursor):
        self._cur = raw_cursor
        self.lastrowid = None

    def execute(self, query, params=None):
        sql = query.strip()

        # 1. No-op SQLite PRAGMA calls
        if sql.upper().startswith("PRAGMA"):
            return self

        # 2. No-op SQLite sequence table cleanup
        if "SQLITE_SEQUENCE" in sql.upper():
            return self

        # 3. Translate SQLite 'INSERT OR IGNORE INTO' to PostgreSQL 'ON CONFLICT DO NOTHING'
        if "INSERT OR IGNORE INTO" in sql.upper():
            sql = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", sql, flags=re.IGNORECASE)
            if "ON CONFLICT" not in sql.upper():
                sql = sql.rstrip("; ") + " ON CONFLICT DO NOTHING"

        # 4. Handle lastrowid via RETURNING id for INSERT queries if not already present
        is_insert = sql.upper().startswith("INSERT INTO")
        has_returning = "RETURNING" in sql.upper()
        if is_insert and not has_returning and "ON CONFLICT" not in sql.upper():
            sql = sql.rstrip("; ") + " RETURNING id"

        # 5. Translate '?' placeholders to '%s' for psycopg2
        if "?" in sql:
            sql = sql.replace("?", "%s")

        # 6. Execute query
        if params is not None:
            if isinstance(params, (list, tuple)):
                self._cur.execute(sql, tuple(params))
            else:
                self._cur.execute(sql, params)
        else:
            self._cur.execute(sql)

        # 7. Capture lastrowid if RETURNING id was appended
        if is_insert and not has_returning and "RETURNING id" in sql:
            try:
                row = self._cur.fetchone()
                if row:
                    self.lastrowid = row.get("id") if hasattr(row, "get") else (row[0] if isinstance(row, tuple) else None)
            except Exception:
                self.lastrowid = None

        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        if isinstance(row, dict):
            return DictRow(row)
        return row

    def fetchall(self):
        rows = self._cur.fetchall()
        if not rows:
            return []
        return [DictRow(r) if isinstance(r, dict) else r for r in rows]

    def close(self):
        self._cur.close()

    def __iter__(self):
        rows = self.fetchall()
        return iter(rows)

class PostgresConnectionWrapper:
    """
    Wraps a psycopg2 connection to provide the same interface as sqlite3.Connection.
    """
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self):
        from psycopg2.extras import RealDictCursor
        return PostgresCursorWrapper(self._conn.cursor(cursor_factory=RealDictCursor))

    def execute(self, query, params=None):
        cur = self.cursor()
        cur.execute(query, params)
        return cur

    def commit(self):
        self._conn.commit()

    def rollback(self):
        self._conn.rollback()

    def close(self):
        self._conn.close()

def get_db_connection():
    """
    Returns an active database connection.
    - If DATABASE_URL is set (PostgreSQL on Render/Cloud), returns PostgresConnectionWrapper.
    - Otherwise, defaults to local SQLite connection (mediconnect.db) for local prototype dev/testing.
    """
    if is_postgres():
        db_url = os.getenv("DATABASE_URL", "").strip()
        # Render sometimes provides postgres:// which psycopg2 prefers as postgresql://
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        import psycopg2
        raw_conn = psycopg2.connect(dsn=db_url)
        return PostgresConnectionWrapper(raw_conn)
    else:
        conn = sqlite3.connect(DB_PATH, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

def hash_password(password: str, salt: str = None) -> tuple[str, str]:
    if salt is None:
        salt = secrets.token_hex(16)
    key = hashlib.pbkdf2_hmac(
        'sha256',
        password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return key.hex(), salt

def verify_password(stored_hash: str, salt: str, provided_password: str) -> bool:
    key = hashlib.pbkdf2_hmac(
        'sha256',
        provided_password.encode('utf-8'),
        salt.encode('utf-8'),
        100000
    )
    return key.hex() == stored_hash

def init_db():
    """
    Initializes database schema and ensures default baseline staff accounts exist.
    Supports both PostgreSQL (via docs/postgres_schema.sql) and SQLite.
    """
    if is_postgres():
        conn = get_db_connection()
        schema_path = os.path.join(BASE_DIR, "docs", "postgres_schema.sql")
        if os.path.exists(schema_path):
            with open(schema_path, "r", encoding="utf-8") as f:
                ddl_sql = f.read()
            raw_cur = conn._conn.cursor()
            raw_cur.execute(ddl_sql)
            conn.commit()
            raw_cur.close()

        # Check and handle initial accounts in PostgreSQL
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM users")
        row = cursor.fetchone()
        count = row[0] if row else 0
        if count == 0:
            admin_user = os.getenv("ADMIN_USERNAME") or os.getenv("INITIAL_ADMIN_USERNAME") or "admin"
            admin_pwd = os.getenv("ADMIN_PASSWORD") or os.getenv("INITIAL_ADMIN_PASSWORD")
            seed_demo = os.getenv("SEED_DEMO_DATA", "").strip().lower() in ("true", "1", "yes")

            now_str = datetime.now().isoformat()
            if admin_pwd:
                phash, salt = hash_password(admin_pwd)
                cursor.execute("""
                    INSERT INTO users (username, full_name, role, village, sub_center, phone, password_hash, salt, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    admin_user,
                    os.getenv("ADMIN_FULL_NAME", "Block Health Supervisor"),
                    "supervisor",
                    os.getenv("ADMIN_VILLAGE", "Block Center"),
                    os.getenv("ADMIN_SUB_CENTER", "Primary Health Center (PHC)"),
                    os.getenv("ADMIN_PHONE", ""),
                    phash,
                    salt,
                    now_str
                ))
                conn.commit()
                print(f"[SECURITY] Bootstrapped production administrator account '{admin_user}' from environment credentials.")
            elif seed_demo:
                demo_users = [
                    ("asha_sunita", "Sunita Devi", "asha_worker", "Rampur", "Rampur Sub-Center", "9876543210", "asha123"),
                    ("asha_anita", "Anita Sharma", "asha_worker", "Bhimpur", "Bhimpur Sub-Center", "9876543211", "asha123"),
                    ("admin_meena", "Meena Kumari (ANM Supervisor)", "supervisor", "Block Center", "Primary Health Center (PHC)", "9876543212", "admin123")
                ]
                for uname, fname, role, village, sc, phone, pwd in demo_users:
                    phash, salt = hash_password(pwd)
                    cursor.execute("""
                        INSERT INTO users (username, full_name, role, village, sub_center, phone, password_hash, salt, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (uname, fname, role, village, sc, phone, phash, salt, now_str))
                conn.commit()
                print("[DB] Explicit SEED_DEMO_DATA flag enabled: seeded demo accounts for evaluation/staging.")
            else:
                print("[SECURITY] PostgreSQL initialized with 0 users. Default demo passwords suppressed for security.")
                print("           To bootstrap admin account: set ADMIN_PASSWORD in environment variables or set SEED_DEMO_DATA=true.")
        conn.close()
        print("[DB] PostgreSQL database initialized and verified successfully.")
        return

    # Default SQLite Initialization
    conn = get_db_connection()
    cursor = conn.cursor()

    # 1. Users Table (ASHA Worker / Supervisors)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        full_name TEXT NOT NULL,
        role TEXT NOT NULL DEFAULT 'asha_worker',
        village TEXT NOT NULL,
        sub_center TEXT DEFAULT '',
        phone TEXT DEFAULT '',
        password_hash TEXT NOT NULL,
        salt TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """)

    # 2. Patients Table (Mothers / Women - D1 Patient Data)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS patients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_uid TEXT UNIQUE,
        full_name TEXT NOT NULL,
        age INTEGER NOT NULL,
        husband_name TEXT DEFAULT '',
        village TEXT NOT NULL,
        phone TEXT DEFAULT '',
        rch_id TEXT DEFAULT '',
        lmp_date TEXT,
        edd_date TEXT,
        gravida INTEGER DEFAULT 1,
        high_risk_flag INTEGER DEFAULT 0,
        notes TEXT DEFAULT '',
        created_by INTEGER,
        sync_status TEXT DEFAULT 'SYNCED',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (created_by) REFERENCES users (id)
    );
    """)

    # 3. Maternal Health Records (Visits & Clinical Measurements - D2 Maternal Health Data)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS maternal_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_uid TEXT UNIQUE,
        patient_id INTEGER NOT NULL,
        visit_number INTEGER DEFAULT 1,
        age INTEGER NOT NULL,
        systolic_bp INTEGER NOT NULL,
        diastolic_bp INTEGER NOT NULL,
        blood_sugar REAL NOT NULL,
        body_temp REAL NOT NULL,
        heart_rate INTEGER NOT NULL,
        risk_level TEXT NOT NULL,
        confidence REAL,
        model_version TEXT NOT NULL,
        action_notes TEXT DEFAULT '',
        recorded_by INTEGER,
        sync_status TEXT DEFAULT 'SYNCED',
        recorded_at TEXT NOT NULL,
        FOREIGN KEY (patient_id) REFERENCES patients (id) ON DELETE CASCADE,
        FOREIGN KEY (recorded_by) REFERENCES users (id)
    );
    """)

    # 4. Children Table (D3 Immunization / Child Data)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS children (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_uid TEXT UNIQUE,
        mother_id INTEGER,
        name TEXT NOT NULL,
        gender TEXT NOT NULL,
        dob TEXT NOT NULL,
        birth_weight REAL,
        guardian_name TEXT DEFAULT '',
        village TEXT NOT NULL,
        phone TEXT DEFAULT '',
        rch_child_id TEXT DEFAULT '',
        created_by INTEGER,
        sync_status TEXT DEFAULT 'SYNCED',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        FOREIGN KEY (mother_id) REFERENCES patients (id) ON DELETE SET NULL,
        FOREIGN KEY (created_by) REFERENCES users (id)
    );
    """)

    # 5. Immunization Records Table (D3 Immunization Tracking)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS immunizations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_uid TEXT UNIQUE,
        child_id INTEGER NOT NULL,
        vaccine_name TEXT NOT NULL,
        dose_number INTEGER NOT NULL DEFAULT 1,
        due_date TEXT NOT NULL,
        given_date TEXT,
        status TEXT NOT NULL,
        batch_no TEXT DEFAULT '',
        notes TEXT DEFAULT '',
        administered_by INTEGER,
        sync_status TEXT DEFAULT 'SYNCED',
        recorded_at TEXT NOT NULL,
        FOREIGN KEY (child_id) REFERENCES children (id) ON DELETE CASCADE,
        FOREIGN KEY (administered_by) REFERENCES users (id)
    );
    """)

    # 6. Symptom Logs Table (D4 Symptom Data - for Outbreak Early Warning)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS symptom_logs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_uid TEXT UNIQUE,
        village TEXT NOT NULL,
        person_name TEXT NOT NULL,
        age INTEGER,
        gender TEXT,
        symptom_type TEXT NOT NULL,
        severity TEXT NOT NULL DEFAULT 'Moderate',
        onset_date TEXT NOT NULL,
        asha_id INTEGER,
        notes TEXT DEFAULT '',
        sync_status TEXT DEFAULT 'SYNCED',
        recorded_at TEXT NOT NULL,
        FOREIGN KEY (asha_id) REFERENCES users (id)
    );
    """)

    # 7. Sync Audit Table (Offline-First Sync Ledger)
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS sync_audit (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        client_device_id TEXT DEFAULT '',
        records_pushed INTEGER DEFAULT 0,
        sync_type TEXT DEFAULT 'PUSH',
        status TEXT NOT NULL,
        synced_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users (id)
    );
    """)

    # Ensure baseline login accounts exist
    cursor.execute("SELECT COUNT(*) FROM users")
    if cursor.fetchone()[0] == 0:
        demo_users = [
            ("asha_sunita", "Sunita Devi", "asha_worker", "Rampur", "Rampur Sub-Center", "9876543210", "asha123"),
            ("asha_anita", "Anita Sharma", "asha_worker", "Bhimpur", "Bhimpur Sub-Center", "9876543211", "asha123"),
            ("admin_meena", "Meena Kumari (ANM Supervisor)", "supervisor", "Block Center", "Primary Health Center (PHC)", "9876543212", "admin123")
        ]
        now_str = datetime.now().isoformat()
        for uname, fname, role, village, sc, phone, pwd in demo_users:
            phash, salt = hash_password(pwd)
            cursor.execute("""
                INSERT INTO users (username, full_name, role, village, sub_center, phone, password_hash, salt, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (uname, fname, role, village, sc, phone, phash, salt, now_str))

    conn.commit()
    conn.close()
    print("[DB] SQLite database initialized successfully.")

if __name__ == "__main__":
    init_db()
