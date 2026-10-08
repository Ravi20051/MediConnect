from datetime import datetime, timedelta
import sqlite3

class ChildFollowupService:
    def __init__(self, get_db_connection_func):
        self.get_db = get_db_connection_func

    def get_actionable_followup_list(self, village_filter: str = None, asha_id: int = None) -> dict:
        """
        Generates actionable weekly immunization follow-up list for ASHA workers.
        Pure rule-based tracking derived from National Immunization Schedule (UIP) rules
        and real database records.
        """
        conn = self.get_db()
        cursor = conn.cursor()

        query = """
            SELECT 
                i.id AS imm_id,
                i.child_id,
                i.vaccine_name,
                i.dose_number,
                i.due_date,
                i.given_date,
                i.status,
                c.name AS child_name,
                c.dob,
                c.gender,
                c.village,
                c.phone,
                c.guardian_name,
                p.full_name AS mother_name
            FROM immunizations i
            JOIN children c ON i.child_id = c.id
            LEFT JOIN patients p ON c.mother_id = p.id
            WHERE i.status IN ('DUE', 'OVERDUE', 'FOLLOW_UP_REQUIRED')
        """
        params = []
        if village_filter:
            query += " AND c.village = ?"
            params.append(village_filter)
        if asha_id:
            query += " AND (c.created_by = ? OR i.administered_by = ?)"
            params.extend([asha_id, asha_id])

        query += " ORDER BY i.due_date ASC"

        cursor.execute(query, params)
        rows = cursor.fetchall()
        
        now = datetime.now()
        follow_ups = []
        summary = {
            "total_pending": len(rows),
            "overdue_count": 0,
            "due_this_week_count": 0,
            "high_priority_count": 0
        }

        for r in rows:
            due_dt = datetime.strptime(r["due_date"], "%Y-%m-%d")
            dob_dt = datetime.strptime(r["dob"], "%Y-%m-%d")
            age_days = (now - dob_dt).days
            age_months = round(age_days / 30.4, 1)

            days_overdue = (now - due_dt).days

            # Determine follow-up urgency
            if days_overdue > 30:
                urgency = "HIGH"
                urgency_badge = "Immediate Home Visit"
                summary["high_priority_count"] += 1
                summary["overdue_count"] += 1
            elif days_overdue > 0:
                urgency = "MEDIUM"
                urgency_badge = "Overdue (Visit within 3 days)"
                summary["overdue_count"] += 1
            elif days_overdue >= -7:
                urgency = "DUE_SOON"
                urgency_badge = "Due This Week"
                summary["due_this_week_count"] += 1
            else:
                urgency = "SCHEDULED"
                urgency_badge = "Upcoming"

            follow_ups.append({
                "immunization_id": r["imm_id"],
                "child_id": r["child_id"],
                "child_name": r["child_name"],
                "mother_name": r["mother_name"] or r["guardian_name"] or "Guardian",
                "village": r["village"],
                "phone": r["phone"] or "Not recorded",
                "child_dob": r["dob"],
                "child_age_months": age_months,
                "vaccine_name": r["vaccine_name"],
                "dose_number": r["dose_number"],
                "due_date": r["due_date"],
                "days_overdue": max(0, days_overdue),
                "current_status": r["status"],
                "urgency": urgency,
                "urgency_badge": urgency_badge,
                "action_recommended": f"Counsel family on {r['vaccine_name']} (Dose {r['dose_number']}) benefits. Mobilize to next VHSND (Village Health Sanitation and Nutrition Day) session."
            })

        conn.close()

        return {
            "methodology": "Rule-based UIP (Universal Immunization Programme) schedule matching",
            "prototype_note": "Immunization Follow-up / Default Risk — rule-based prototype (No fabricated ML)",
            "summary": summary,
            "follow_up_list": follow_ups
        }
