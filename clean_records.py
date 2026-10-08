import sqlite3
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "mediconnect.db")

def clean_database():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("PRAGMA foreign_keys = OFF")

    tables = ["immunizations", "children", "maternal_records", "patients", "symptom_logs", "sync_audit"]
    
    print("Clearing tables...")
    for table in tables:
        cursor.execute(f"DELETE FROM {table}")
        print(f" - Cleaned table: {table}")

    # Reset auto-increment sequence counters so new records start from ID 1
    cursor.execute("DELETE FROM sqlite_sequence WHERE name IN ('immunizations', 'children', 'maternal_records', 'patients', 'symptom_logs', 'sync_audit')")
    
    cursor.execute("PRAGMA foreign_keys = ON")
    conn.commit()

    print("\nVerification of table row counts:")
    for table in tables + ["users"]:
        cursor.execute(f"SELECT COUNT(*) FROM {table}")
        count = cursor.fetchone()[0]
        print(f" - {table}: {count} records")

    conn.close()
    print("\nDatabase records cleaned successfully. Users preserved for login.")

if __name__ == "__main__":
    clean_database()
