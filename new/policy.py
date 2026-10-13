# -*- coding: utf-8 -*-
"""מטריצת מדיניות - אילו פעולות מותרות לנציג בכל רמת סיכון.

הרעיון (Arias-Cabarcos 2019, הסקירה): ממשק הנציג מציג "הפעולה המותרת הבאה" ולא רק מספר.
"""
from typing import Dict, List, Optional

import db

_POLICY_CACHE: Optional[Dict[str, List[dict]]] = None


def _fallback() -> Dict[str, List[dict]]:
    result: Dict[str, List[dict]] = {}
    for (level_key, action_key, label, allowed) in db.SEED_POLICY:
        result.setdefault(level_key, []).append(
            {"action_key": action_key, "label": label, "allowed": bool(allowed)}
        )
    return result


def load_policy(conn=None) -> Dict[str, List[dict]]:
    global _POLICY_CACHE
    if conn is None:
        return _POLICY_CACHE or _fallback()
    rows = conn.execute(
        "SELECT level_key, action_key, action_label, allowed FROM policy_rules ORDER BY rule_id"
    ).fetchall()
    result: Dict[str, List[dict]] = {}
    for r in rows:
        result.setdefault(r["level_key"], []).append(
            {"action_key": r["action_key"], "label": r["action_label"], "allowed": bool(r["allowed"])}
        )
    _POLICY_CACHE = result or _fallback()
    return _POLICY_CACHE


def actions_for_level(level_key: str, conn=None) -> List[dict]:
    return load_policy(conn).get(level_key, [])
