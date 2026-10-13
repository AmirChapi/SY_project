# -*- coding: utf-8 -*-
"""שאילתות ניתוח על היסטוריית השיחות - לזיהוי דפוסים שעשויים להעיד על ניסיון תקיפה."""

# סדר קבוע להצגת רמות הסיכון בגרפים
RISK_LEVELS = ["נמוך", "בינוני", "גבוה"]


def get_summary(conn) -> dict:
    total_calls = conn.execute("SELECT COUNT(*) AS c FROM calls").fetchone()["c"]
    high_count = conn.execute(
        "SELECT COUNT(*) AS c FROM risk_assessments WHERE risk_level = 'גבוה'"
    ).fetchone()["c"]
    otp_count = conn.execute(
        "SELECT COUNT(*) AS c FROM risk_assessments WHERE otp_required = 1"
    ).fetchone()["c"]
    high_pct = round((high_count / total_calls) * 100) if total_calls else 0
    return {
        "total_calls": total_calls,
        "high_count": high_count,
        "high_pct": high_pct,
        "otp_count": otp_count,
    }


def get_risk_distribution(conn) -> list:
    rows = conn.execute(
        "SELECT risk_level, COUNT(*) AS c FROM risk_assessments GROUP BY risk_level"
    ).fetchall()
    counts = {row["risk_level"]: row["c"] for row in rows}
    return [{"level": level, "count": counts.get(level, 0)} for level in RISK_LEVELS]


def get_kpis(conn) -> dict:
    """מדדי הצלחה מהספרות: False-Positive, זמן טיפול לפי רמה, שיעור השלמת Step-Up (Gunson; Wiefling 2021)."""
    step = conn.execute(
        """SELECT
             COUNT(*) AS total,
             SUM(CASE WHEN result = 'approved' THEN 1 ELSE 0 END) AS approved,
             SUM(CASE WHEN result = 'failed' THEN 1 ELSE 0 END) AS failed
           FROM step_up_challenges"""
    ).fetchone()
    total = step["total"] or 0
    approved = step["approved"] or 0
    failed = step["failed"] or 0

    # False-Positive מוגדר: שיחות שהגיעו ל-Step-Up ובהן הלקוח האמיתי אישר → היו לגיטימיות
    fp_rate = round((approved / total) * 100) if total else 0
    pass_rate = round((approved / (approved + failed)) * 100) if (approved + failed) else 0

    handle = conn.execute(
        """SELECT risk_assessments.risk_level, AVG(calls.handle_seconds) AS avg_sec
           FROM calls JOIN risk_assessments ON calls.call_id = risk_assessments.call_id
           WHERE calls.handle_seconds IS NOT NULL
           GROUP BY risk_assessments.risk_level"""
    ).fetchall()
    handle_by_level = {r["risk_level"]: round(r["avg_sec"]) for r in handle}

    return {
        "step_up_total": total,
        "step_up_approved": approved,
        "step_up_failed": failed,
        "false_positive_rate": fp_rate,
        "step_up_pass_rate": pass_rate,
        "handle_by_level": [{"level": lv, "avg_sec": handle_by_level.get(lv)} for lv in RISK_LEVELS],
    }


def get_top_indicators(conn, limit: int = 8) -> list:
    rows = conn.execute(
        """SELECT indicator_label, COUNT(*) AS c
           FROM risk_indicators
           WHERE is_present = 1
           GROUP BY indicator_label
           ORDER BY c DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [{"label": row["indicator_label"], "count": row["c"]} for row in rows]


def get_repeat_targets(conn, min_calls: int = 2, limit: int = 10) -> list:
    """לקוחות/חשבונות שקיבלו מספר פניות - יכול להעיד על ניסיונות תקיפה חוזרים על אותו יעד."""
    rows = conn.execute(
        """SELECT customers.full_name, customers.account_number, customers.phone,
                  COUNT(*) AS call_count,
                  SUM(CASE WHEN risk_assessments.risk_level = 'גבוה' THEN 1 ELSE 0 END) AS high_count
           FROM calls
           JOIN customers ON calls.customer_id = customers.customer_id
           LEFT JOIN risk_assessments ON calls.call_id = risk_assessments.call_id
           GROUP BY calls.customer_id
           HAVING call_count >= ?
           ORDER BY call_count DESC
           LIMIT ?""",
        (min_calls, limit),
    ).fetchall()
    return [dict(row) for row in rows]


def get_recent_high_risk(conn, limit: int = 10) -> list:
    rows = conn.execute(
        """SELECT calls.call_id, calls.call_time, calls.agent_name, calls.call_type,
                  customers.full_name, risk_assessments.total_score
           FROM calls
           JOIN customers ON calls.customer_id = customers.customer_id
           JOIN risk_assessments ON calls.call_id = risk_assessments.call_id
           WHERE risk_assessments.risk_level = 'גבוה'
           ORDER BY calls.call_id DESC
           LIMIT ?""",
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]
