# -*- coding: utf-8 -*-
"""יומן ביקורת - תיעוד כל החלטת מערכת וכל פעולת נציג (הסקירה: Audit Log לתחקור ובקרה)."""
from datetime import datetime
from typing import List, Optional


def write(conn, call_id: Optional[int], actor: str, action: str, details: str = "") -> None:
    conn.execute(
        "INSERT INTO audit_log (call_id, actor, action, details, logged_at) VALUES (?, ?, ?, ?, ?)",
        (call_id, actor, action, details, datetime.now().isoformat(timespec="seconds")),
    )


def for_call(conn, call_id: int) -> List[dict]:
    return conn.execute(
        "SELECT * FROM audit_log WHERE call_id = ? ORDER BY audit_id", (call_id,)
    ).fetchall()


def recent(conn, limit: int = 100) -> List[dict]:
    return conn.execute(
        """SELECT audit_log.*, customers.full_name
           FROM audit_log
           LEFT JOIN calls ON audit_log.call_id = calls.call_id
           LEFT JOIN customers ON calls.customer_id = customers.customer_id
           ORDER BY audit_id DESC LIMIT ?""",
        (limit,),
    ).fetchall()
