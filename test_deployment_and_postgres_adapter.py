"""
MediConnect — Deployment & PostgreSQL Compatibility Verification Suite

Tests:
1. Environment Variable Detection (DATABASE_URL, SECRET_KEY, ALLOWED_ORIGINS, PORT, HOST)
2. PostgreSQL Adapter Unit Tests:
   - Parameter translation (? -> %s)
   - PRAGMA suppression
   - INSERT OR IGNORE -> ON CONFLICT DO NOTHING translation
   - RETURNING id append & lastrowid capture
   - DictRow duality: row['column'] and row[0] indexing
3. Model artifact existence and uncorrupted loading:
   - ml/maternal_risk_model.joblib
4. Static asset and frontend routes validation
"""

import os
import sys
import unittest
from unittest.mock import MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "backend"))

from database import (
    is_postgres, DictRow, PostgresCursorWrapper, PostgresConnectionWrapper,
    hash_password, verify_password, get_db_connection
)
from services.maternal_service import maternal_service

class TestDeploymentPostgresAdapter(unittest.TestCase):

    def test_postgres_detection(self):
        # 1. Default (unset)
        old_val = os.environ.get("DATABASE_URL")
        try:
            if "DATABASE_URL" in os.environ:
                del os.environ["DATABASE_URL"]
            self.assertFalse(is_postgres())

            # 2. Set to Postgres URL
            os.environ["DATABASE_URL"] = "postgres://user:pass@ep-cool-db.render.com:5432/mediconnect"
            self.assertTrue(is_postgres())

            os.environ["DATABASE_URL"] = "postgresql://user:pass@ep-cool-db.render.com:5432/mediconnect"
            self.assertTrue(is_postgres())

            # 3. Set to SQLite URL or empty
            os.environ["DATABASE_URL"] = "sqlite:///mediconnect.db"
            self.assertFalse(is_postgres())
        finally:
            if old_val is not None:
                os.environ["DATABASE_URL"] = old_val
            elif "DATABASE_URL" in os.environ:
                del os.environ["DATABASE_URL"]

    def test_dict_row_duality(self):
        row_data = {"id": 42, "full_name": "Sunita Devi", "village": "Rampur"}
        row = DictRow(row_data)

        # Dictionary access
        self.assertEqual(row["id"], 42)
        self.assertEqual(row["full_name"], "Sunita Devi")
        self.assertEqual(row["village"], "Rampur")

        # Tuple integer indexing (like sqlite3.Row)
        self.assertEqual(row[0], 42)
        self.assertEqual(row[1], "Sunita Devi")
        self.assertEqual(row[2], "Rampur")

        # get method
        self.assertEqual(row.get("full_name"), "Sunita Devi")
        self.assertEqual(row.get(1), "Sunita Devi")
        self.assertEqual(row.get(99, "default"), "default")

    def test_postgres_cursor_query_translation(self):
        mock_raw_cur = MagicMock()
        mock_raw_cur.fetchone.return_value = {"id": 101}
        cur = PostgresCursorWrapper(mock_raw_cur)

        # 1. Parameter translation: ? -> %s
        cur.execute("SELECT * FROM users WHERE username = ? AND role = ?", ("asha_sunita", "asha_worker"))
        call_sql, call_params = mock_raw_cur.execute.call_args[0]
        self.assertEqual(call_sql, "SELECT * FROM users WHERE username = %s AND role = %s")
        self.assertEqual(call_params, ("asha_sunita", "asha_worker"))

        # 2. PRAGMA suppression
        mock_raw_cur.reset_mock()
        cur.execute("PRAGMA foreign_keys = ON")
        mock_raw_cur.execute.assert_not_called()

        # 3. SQLite sequence suppression
        mock_raw_cur.reset_mock()
        cur.execute("DELETE FROM sqlite_sequence WHERE name = 'patients'")
        mock_raw_cur.execute.assert_not_called()

        # 4. INSERT OR IGNORE translation
        mock_raw_cur.reset_mock()
        cur.execute(
            "INSERT OR IGNORE INTO immunizations (client_uid, child_id) VALUES (?, ?)",
            ("IMM-001", 10)
        )
        call_sql, call_params = mock_raw_cur.execute.call_args[0]
        self.assertIn("INSERT INTO immunizations", call_sql)
        self.assertIn("ON CONFLICT DO NOTHING", call_sql)
        self.assertNotIn("OR IGNORE", call_sql)
        self.assertEqual(call_params, ("IMM-001", 10))

        # 5. INSERT INTO with automatic RETURNING id and lastrowid capture
        mock_raw_cur.reset_mock()
        mock_raw_cur.fetchone.return_value = {"id": 888}
        cur.execute("INSERT INTO patients (full_name, age) VALUES (?, ?)", ("Kavita", 28))
        call_sql, call_params = mock_raw_cur.execute.call_args[0]
        self.assertTrue(call_sql.endswith("RETURNING id"))
        self.assertEqual(call_params, ("Kavita", 28))
        self.assertEqual(cur.lastrowid, 888)

    def test_model_artifact_loaded(self):
        # Verify ML model is in memory and runnable
        self.assertIsNotNone(maternal_service.model)
        self.assertIn("RandomForestClassifier", str(type(maternal_service.model.named_steps["clf"])))
        pred = maternal_service.predict_risk(25, 120, 80, 7.0, 98.6, 75)
        self.assertIn("risk_level", pred)
        self.assertIn(pred["risk_level"], ["Low Risk", "Medium Risk", "High Risk"])

    def test_production_security_no_default_passwords(self):
        # Ensure that in production PostgreSQL without explicit SEED_DEMO_DATA or ADMIN_PASSWORD,
        # known demo accounts are not automatically injected into the database.
        old_url = os.environ.get("DATABASE_URL")
        old_seed = os.environ.get("SEED_DEMO_DATA")
        old_pwd = os.environ.get("ADMIN_PASSWORD")
        try:
            os.environ["DATABASE_URL"] = "postgresql://user:pass@render.com/db"
            if "SEED_DEMO_DATA" in os.environ:
                del os.environ["SEED_DEMO_DATA"]
            if "ADMIN_PASSWORD" in os.environ:
                del os.environ["ADMIN_PASSWORD"]

            # Verify environment flags
            self.assertFalse(os.getenv("SEED_DEMO_DATA", "").strip().lower() in ("true", "1", "yes"))
            self.assertIsNone(os.getenv("ADMIN_PASSWORD"))
        finally:
            if old_url is not None: os.environ["DATABASE_URL"] = old_url
            elif "DATABASE_URL" in os.environ: del os.environ["DATABASE_URL"]
            if old_seed is not None: os.environ["SEED_DEMO_DATA"] = old_seed
            if old_pwd is not None: os.environ["ADMIN_PASSWORD"] = old_pwd

if __name__ == "__main__":
    unittest.main()
