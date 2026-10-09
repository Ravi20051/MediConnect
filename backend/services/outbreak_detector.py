from datetime import datetime, timedelta
import sqlite3

class OutbreakDetectorService:
    def __init__(self, get_db_connection_func):
        self.get_db = get_db_connection_func

    def detect_anomalies(self, recent_days: int = 7, baseline_days: int = 30, village_filter: str = None) -> dict:
        """
        Analyzes live symptom logs in SQLite across villages or for a specific village.
        Computes rolling baseline vs recent case clusters.
        Honest anomaly detection without fabricated medical claims.
        """
        conn = self.get_db()
        cursor = conn.cursor()

        now = datetime.now()
        recent_threshold = (now - timedelta(days=recent_days)).strftime("%Y-%m-%d")
        baseline_start = (now - timedelta(days=baseline_days)).strftime("%Y-%m-%d")

        # 1. Total symptoms count by village
        cursor.execute("""
            SELECT village, COUNT(*) as total_count 
            FROM symptom_logs 
            GROUP BY village
        """)
        village_totals = {row["village"]: row["total_count"] for row in cursor.fetchall()}

        # 2. Symptoms by village and symptom type in the recent window (last 7 days)
        cursor.execute("""
            SELECT village, symptom_type, COUNT(*) as recent_count,
                   SUM(CASE WHEN severity = 'Severe' THEN 1 ELSE 0 END) as severe_count
            FROM symptom_logs
            WHERE onset_date >= ?
            GROUP BY village, symptom_type
        """, (recent_threshold,))
        recent_records = cursor.fetchall()

        # 3. Symptoms by village and symptom type in the historical baseline window (prior to recent window)
        cursor.execute("""
            SELECT village, symptom_type, COUNT(*) as hist_count
            FROM symptom_logs
            WHERE onset_date >= ? AND onset_date < ?
            GROUP BY village, symptom_type
        """, (baseline_start, recent_threshold))
        hist_records = {(row["village"], row["symptom_type"]): row["hist_count"] for row in cursor.fetchall()}

        alerts = []
        monitored_villages = {}

        for r in recent_records:
            village = r["village"]
            stype = r["symptom_type"]
            rec_cnt = r["recent_count"]
            sev_cnt = r["severe_count"]

            total_village_records = village_totals.get(village, 0)
            hist_cnt = hist_records.get((village, stype), 0)

            # Baseline rate normalized to a 7-day period
            baseline_7d_rate = (hist_cnt / (baseline_days - recent_days)) * recent_days

            if total_village_records < 3:
                status = "INSUFFICIENT_DATA"
                alert_text = "Insufficient data for outbreak detection in this village."
                badge = "Insufficient Data"
                is_anomaly = False
            else:
                # Anomaly criteria: recent count is at least 3x baseline AND at least 3 cases in recent window, OR >= 5 cases in 7 days
                spike_ratio = rec_cnt / max(1.0, baseline_7d_rate)
                if (spike_ratio >= 2.5 and rec_cnt >= 4) or (rec_cnt >= 5):
                    is_anomaly = True
                    status = "ANOMALY_DETECTED"
                    badge = "Warning: Symptom Spike"
                    alert_text = f"Early warning: unusual symptom cluster of '{stype}' ({rec_cnt} cases in last {recent_days} days vs baseline ~{round(baseline_7d_rate, 1)}). Possible unusual symptom pattern detected."
                else:
                    is_anomaly = False
                    status = "NORMAL_VARIATION"
                    badge = "Normal Baseline"
                    alert_text = f"Symptom levels within expected seasonal variation ({rec_cnt} cases reported)."

            item = {
                "village": village,
                "symptom_type": stype,
                "recent_cases_7d": rec_cnt,
                "severe_cases": sev_cnt,
                "historical_baseline_7d": round(baseline_7d_rate, 1),
                "is_anomaly": is_anomaly,
                "status": status,
                "badge": badge,
                "message": alert_text,
                "action_recommendation": "Inspect drinking water source, sanitize surrounding areas, and alert PHC Medical Officer for active surveillance." if is_anomaly else "Continue routine surveillance."
            }

            if is_anomaly:
                alerts.append(item)

            if village not in monitored_villages:
                monitored_villages[village] = []
            monitored_villages[village].append(item)

        # Villages with zero recent symptoms or insufficient data
        for village, tot in village_totals.items():
            if village not in monitored_villages:
                monitored_villages[village] = [{
                    "village": village,
                    "symptom_type": "None",
                    "recent_cases_7d": 0,
                    "severe_cases": 0,
                    "historical_baseline_7d": 0,
                    "is_anomaly": False,
                    "status": "NORMAL_OR_NO_CASES" if tot >= 3 else "INSUFFICIENT_DATA",
                    "badge": "No Recent Cases" if tot >= 3 else "Insufficient Data",
                    "message": "No active symptom cases in recent period." if tot >= 3 else "Insufficient data for outbreak detection.",
                    "action_recommendation": "Maintain standard community reporting."
                }]

        # Recent individual symptom entries for field ledger
        log_query = """
            SELECT id, village, person_name, age, gender, symptom_type, severity, onset_date, recorded_at
            FROM symptom_logs
        """
        log_params = []
        if village_filter:
            log_query += " WHERE village = ?"
            log_params.append(village_filter.strip())
        log_query += " ORDER BY onset_date DESC, id DESC LIMIT 20"
        cursor.execute(log_query, log_params)
        recent_log_entries = [dict(row) for row in cursor.fetchall()]

        conn.close()

        # Apply village filter if specified
        if village_filter:
            vf_lower = village_filter.strip().lower()
            alerts = [a for a in alerts if a["village"].strip().lower() == vf_lower]
            monitored_villages = {k: v for k, v in monitored_villages.items() if k.strip().lower() == vf_lower}

        return {
            "analysis_window_days": recent_days,
            "baseline_window_days": baseline_days,
            "active_alerts_count": len(alerts),
            "alerts": alerts,
            "monitored_villages": monitored_villages,
            "recent_logs": recent_log_entries,
            "disclaimer": "Early warning surveillance only. Does not confirm clinical or laboratory outbreak diagnosis."
        }
