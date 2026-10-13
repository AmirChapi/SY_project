# -*- coding: utf-8 -*-
"""לוגיקת חישוב רמת הסיכון של שיחה במוקד השירות.

המשקלים והספים נטענים מבסיס הנתונים (indicator_catalog, risk_levels) כדי לאפשר כיול
ללא שינוי קוד - בהתאם למסקנת Wiefling et al. (2021) שאין תצורת RBA אחת שמתאימה לכל שירות.
כשאין חיבור DB (בדיקות יחידה של המנוע) משתמשים בברירות המחדל שב-db.SEED_*.
"""
from typing import List, Optional

import db

_INDICATOR_CACHE: Optional[List[dict]] = None
_LEVEL_CACHE: Optional[List[dict]] = None

# תיקוני ציון לאחר Step-Up - אישור בערוץ רשום מנטרל חלק גדול מהחשד; כישלון מחזק אותו
STEP_UP_APPROVED_ADJUSTMENT = -35
STEP_UP_FAILED_ADJUSTMENT = 30


def _fallback_indicators() -> List[dict]:
    return [
        {"key": k, "label": lbl, "category": cat, "source": src, "weight": w, "is_auto": bool(auto)}
        for (k, lbl, cat, src, w, auto) in db.SEED_INDICATORS
    ]


def _fallback_levels() -> List[dict]:
    return [
        {"key": k, "label": lbl, "min": mn, "max": mx, "recommendation": rec}
        for (k, lbl, mn, mx, rec, _order) in db.SEED_LEVELS
    ]


def load_indicators(conn=None) -> List[dict]:
    """מחזיר את קטלוג האינדיקציות מה-DB (או מברירת המחדל אם אין חיבור)."""
    global _INDICATOR_CACHE
    if conn is None:
        return _INDICATOR_CACHE or _fallback_indicators()
    rows = conn.execute(
        "SELECT indicator_key, label, category, source, weight, is_auto FROM indicator_catalog ORDER BY rowid"
    ).fetchall()
    _INDICATOR_CACHE = [
        {"key": r["indicator_key"], "label": r["label"], "category": r["category"],
         "source": r["source"], "weight": r["weight"], "is_auto": bool(r["is_auto"])}
        for r in rows
    ] or _fallback_indicators()
    return _INDICATOR_CACHE


def load_levels(conn=None) -> List[dict]:
    global _LEVEL_CACHE
    if conn is None:
        return _LEVEL_CACHE or _fallback_levels()
    rows = conn.execute(
        "SELECT level_key, label, min_score, max_score, recommendation FROM risk_levels ORDER BY sort_order"
    ).fetchall()
    _LEVEL_CACHE = [
        {"key": r["level_key"], "label": r["label"], "min": r["min_score"],
         "max": r["max_score"], "recommendation": r["recommendation"]}
        for r in rows
    ] or _fallback_levels()
    return _LEVEL_CACHE


def manual_indicators(conn=None) -> List[dict]:
    return [i for i in load_indicators(conn) if not i["is_auto"]]


def auto_indicators(conn=None) -> List[dict]:
    return [i for i in load_indicators(conn) if i["is_auto"]]


def classify(score: int, conn=None) -> dict:
    """ממפה ציון לרמת סיכון לפי הספים שבטבלת risk_levels."""
    levels = load_levels(conn)
    for level in levels:
        if level["min"] <= score <= level["max"]:
            return {"level_key": level["key"], "level": level["label"], "recommendation": level["recommendation"]}
    last = levels[-1]
    return {"level_key": last["key"], "level": last["label"], "recommendation": last["recommendation"]}


def calculate_risk(selected: dict, indicators: Optional[List[dict]] = None, conn=None, adjustment: int = 0) -> dict:
    """מחשב ציון סיכון 0-100 מתוך מיפוי key -> bool.

    הציון הוא סכום המשקלים של האינדיקציות שזוהו, מוגבל ל-100 - פשוט להסביר ולכייל:
    כל אינדיקציה מוסיפה את המשקל שלה בנקודות, והספים (30/60) הם נקודות מוחלטות.
    adjustment - תיקון שמופעל לאחר תוצאת Step-Up (אישור מוריד סיכון, כישלון מעלה).
    """
    indicator_set = indicators if indicators is not None else manual_indicators(conn)
    total = sum(i["weight"] for i in indicator_set if selected.get(i["key"]))
    raw = min(100, total)
    score = max(0, min(100, raw + adjustment))
    result = classify(score, conn)
    result["score"] = score
    result["raw_score"] = raw
    return result
