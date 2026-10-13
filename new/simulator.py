# -*- coding: utf-8 -*-
"""סימולטור שיחות חי למוקד השירות - לצורך הדגמה בלבד (ללא טלפוניה אמיתית).

כל שיחה עוברת שלבים:
  ivr      - הלקוח בהמתנה/IVR. המערכת אוספת אותות ומחשבת סיכון עוד לפני שהנציג ענה (X-Factor).
  agent    - הנציג ענה. הציון והפעולות המותרות כבר מוכנים על המסך.
  step_up  - נשלח אישור Push לערוץ הרשום; ממתינים לתוצאה (הנציג מסמן אישר/נכשל).
  resolved - Step-Up הוכרע; הציון תוקן בהתאם.

המצב מחושב תמיד לפי הזמן שחלף מרגע ההתחלה - ללא תהליכי רקע.
"""
import secrets
import time
from typing import Dict, List, Optional

import otp_service
import risk_engine

IVR_SECONDS = 6  # משך שלב ההמתנה/IVR בסימולציה

SCENARIOS = {
    "normal_balance_check": {
        "title": "שיחה שגרתית - בירור יתרה",
        "description": "לקוח מוכר, מספר רשום, שעות היום. מדגים אפס חיכוך ללקוח תקין.",
        "icon": "💳",
        "expected_path": "ירוק - ללא Step-Up",
        "customer_name": "דנה כהן",
        "caller_number": "050-1234567",
        "caller_geo": "ישראל (מספר רשום)",
        "caller_number_status": "תואם למספר הרשום בבנק",
        "ivr_status": "המספר הרשום אומת אוטומטית בשלב ההמתנה",
        "location_source": "קידומת מספר + CLI",
        "requested_action": "balance_inquiry",
        "duration": 14,
        "script": [],
        "auto_step_up_result": None,
    },
    "legit_customer_abroad": {
        "title": "לקוח לגיטימי מתקשר מחו\"ל",
        "description": "לקוח אמיתי בנסיעה. אותות הרשת מעלים חשד - Step-Up לאפליקציה מאשר את זהותו והסיכון יורד. מדגים False-Positive מטופל.",
        "icon": "✈️",
        "expected_path": "צהוב → Push אושר → ירוק",
        "customer_name": "מיכל ברק",
        "caller_number": "+1 212 555 0148",
        "caller_geo": "ארה\"ב (ניו יורק)",
        "caller_number_status": "לא תואם למספר הרשום בבנק",
        "ivr_status": "הלקוחה הזינה את המספר הרשום בהצלחה",
        "location_source": "קידומת בינלאומית + GeoIP",
        "requested_action": "transfer",
        "duration": 20,
        "script": [
            (2, "caller_number_mismatch"),
            (4, "foreign_call"),
        ],
        "auto_step_up_result": "approved",
    },
    "night_call_abroad": {
        "title": "שיחת לילה ממספר בינלאומי",
        "description": "שעה חריגה, מספר זר, שינוי מיקום. Step-Up נשלח לאפליקציה הרשומה - הלקוח האמיתי לא מאשר, והסיכון קופץ לגבוה.",
        "icon": "🌍",
        "expected_path": "צהוב → Push נכשל → אדום",
        "customer_name": "יוסי לוי",
        "caller_number": "+995 32 555 0199",
        "caller_geo": "גאורגיה",
        "caller_number_status": "לא תואם למספר הרשום בבנק",
        "ivr_status": "הוזן מספר רשום - אך ממכשיר לא מוכר",
        "location_source": "קידומת בינלאומית + GeoIP",
        "requested_action": "contact_change",
        "duration": 20,
        "script": [
            (2, "caller_number_mismatch"),
            (3, "unusual_hour"),
            (5, "foreign_call"),
        ],
        "auto_step_up_result": "failed",
    },
    "pretexting_pressure": {
        "title": "Pretexting - לחץ ודחיפות על הנציג",
        "description": "המתקשר יודע פרטים אמיתיים, אך יוצר דחיפות ולוחץ לעקוף נהלים. המערכת מזהה את הדפוס ההתנהגותי.",
        "icon": "🎭",
        "expected_path": "צהוב → Push נשלח → אדום לפני תגובה → הסלמה",
        "customer_name": "אבי מזרחי",
        "caller_number": "052-9876543",
        "caller_geo": "ישראל",
        "caller_number_status": "לא תואם למספר הרשום בבנק",
        "ivr_status": "שני ניסיונות שגויים בהזנת המספר הרשום",
        "location_source": "קידומת מספר + CLI",
        "requested_action": "transfer",
        "duration": 18,
        "script": [
            (2, "caller_number_mismatch"),
            (7, "rapid_repeat_calls"),
            (10, "urgency_pressure"),
        ],
        "auto_step_up_result": None,
    },
    "account_takeover": {
        "title": "Account Takeover - החלפת SIM וקול סינתטי",
        "description": "שרשרת אינדיקציות שמצטברת במהירות: מספר זר, SIM שהוחלף, ריבוי שיחות, קול סינתטי ובקשה לשינוי טלפון. פעולה רגישה נחסמת.",
        "icon": "🚨",
        "expected_path": "אדום - פעולה חסומה + הסלמה",
        "customer_name": "לקוח לא מזוהה",
        "caller_number": "+44 7700 900123",
        "caller_geo": "בריטניה",
        "caller_number_status": "לא תואם למספר הרשום בבנק",
        "ivr_status": "אימות המספר הרשום נכשל לאחר מספר ניסיונות",
        "location_source": "קידומת בינלאומית + GeoIP + SIM Swap API",
        "requested_action": "contact_change",
        "duration": 18,
        "script": [
            (1, "caller_number_mismatch"),
            (2, "foreign_call"),
            (4, "device_sim_swap"),
            (7, "rapid_repeat_calls"),
            (10, "synthetic_voice"),
        ],
        "auto_step_up_result": None,
    },
}

# מאגר שיחות פעילות בזיכרון התהליך - מספיק להדגמה, אינו מיועד ל-production מרובה תהליכים
_ACTIVE_CALLS: Dict[str, dict] = {}


def start_call(scenario_id: str, agent_name: str) -> str:
    call_key = secrets.token_urlsafe(8)
    _ACTIVE_CALLS[call_key] = {
        "scenario_id": scenario_id,
        "agent_name": agent_name,
        "started_at": time.time(),
        "step_up": None,          # dict: code, code_hash, channel, sent_at_sec, result, resolved_at_sec
        "events": [],             # יומן אירועים של השיחה להצגה חיה
    }
    _log(_ACTIVE_CALLS[call_key], 0, "system", "שיחה נכנסת - נכנסה לשלב IVR/המתנה")
    return call_key


def _log(entry: dict, at_sec: float, actor: str, text: str) -> None:
    entry["events"].append({"at": round(at_sec, 1), "actor": actor, "text": text})


def _elapsed(entry: dict) -> float:
    return time.time() - entry["started_at"]


def resolve_step_up(call_key: str, result: str) -> Optional[dict]:
    """הנציג (או ה-Push המדומה) מסמן: approved / failed."""
    entry = _ACTIVE_CALLS.get(call_key)
    if entry is None or entry["step_up"] is None or entry["step_up"]["result"] != "pending":
        return None
    now = _elapsed(entry)
    entry["step_up"]["result"] = result
    entry["step_up"]["resolved_at_sec"] = round(now, 1)
    label = "הלקוח אישר את הבקשה באפליקציה - הזהות אומתה" if result == "approved" \
        else "הלקוח לא אישר / דחה את הבקשה באפליקציה - החשד מתחזק"
    _log(entry, now, "step_up", label)
    return _build_status(call_key, entry)


def _build_status(call_key: str, entry: dict) -> dict:
    scenario = SCENARIOS[entry["scenario_id"]]
    elapsed = _elapsed(entry)
    elapsed_clamped = min(elapsed, scenario["duration"])
    finished = elapsed >= scenario["duration"]

    catalog = risk_engine.auto_indicators()
    trigger_time = {k: t for (t, k) in scenario["script"]}
    triggered = {k for (t, k) in scenario["script"] if t <= elapsed_clamped}

    indicators, selected = [], {}
    for ind in catalog:
        present = ind["key"] in triggered
        selected[ind["key"]] = present
        t = trigger_time.get(ind["key"])
        indicators.append({
            "key": ind["key"], "label": ind["label"], "weight": ind["weight"],
            "category": ind["category"], "source": ind["source"],
            "is_present": present, "triggered_at": t,
            "detected_phase": ("ivr" if t is not None and t < IVR_SECONDS else "agent") if present else None,
        })

    # לוג אירועים של אינדיקציות שהתגלו (פעם אחת לכל אינדיקציה)
    logged = {e["text"] for e in entry["events"]}
    for ind in indicators:
        if ind["is_present"]:
            text = f"זוהה: {ind['label']} (משקל {ind['weight']}, מקור: {ind['source']})"
            if text not in logged:
                _log(entry, ind["triggered_at"], "system", text)

    # תוצאת Step-Up משנה את הציון
    adjustment = 0
    su = entry["step_up"]
    if su and su["result"] == "approved":
        adjustment = risk_engine.STEP_UP_APPROVED_ADJUSTMENT
    elif su and su["result"] == "failed":
        adjustment = risk_engine.STEP_UP_FAILED_ADJUSTMENT

    result = risk_engine.calculate_risk(selected, catalog, adjustment=adjustment)

    # שלב השיחה
    if elapsed_clamped < IVR_SECONDS:
        phase = "ivr"
    elif su and su["result"] == "pending":
        phase = "step_up"
    elif su:
        phase = "resolved"
    else:
        phase = "agent"

    if phase != "ivr" and "נציג ענה" not in " ".join(e["text"] for e in entry["events"]):
        _log(entry, IVR_SECONDS, "system",
             f"נציג ענה לשיחה - ציון הסיכון ({result['raw_score']}) כבר מוכן על המסך")

    # שליחת Step-Up פעם אחת כשעולים לבינוני (רק אחרי שהנציג ענה)
    if su is None and result["level_key"] == "medium" and phase == "agent":
        step = otp_service.build_step_up("medium")
        entry["step_up"] = {
            "code": step["code"], "code_hash": otp_service.hash_code(step["code"]),
            "channel": step["channel"], "channel_label": step["channel_label"],
            "sent_at_sec": round(elapsed_clamped, 1), "result": "pending", "resolved_at_sec": None,
        }
        _log(entry, elapsed_clamped, "system",
             "רמת סיכון בינונית - נשלחה בקשת אישור Push לאפליקציית הבנק הרשומה (לא למספר המתקשר)")
        su = entry["step_up"]
        phase = "step_up"

    # תוצאת Step-Up אוטומטית בתרחישים שמגדירים אותה, 4 שניות אחרי השליחה
    if su and su["result"] == "pending" and scenario["auto_step_up_result"] \
            and elapsed_clamped >= su["sent_at_sec"] + 4:
        resolve_step_up(call_key, scenario["auto_step_up_result"])
        return _build_status(call_key, entry)

    import policy  # ייבוא מקומי כדי להימנע ממעגליות
    actions = policy.actions_for_level(result["level_key"])
    requested = next((a for a in actions if a["action_key"] == scenario["requested_action"]), None)

    return {
        "call_key": call_key,
        "scenario_id": entry["scenario_id"],
        "scenario_title": scenario["title"],
        "expected_path": scenario["expected_path"],
        "customer_name": scenario["customer_name"],
        "caller_number": scenario["caller_number"],
        "caller_geo": scenario["caller_geo"],
        "phone_display": f"{scenario['caller_number']} ({scenario['caller_geo']})",
        "caller_number_status": scenario["caller_number_status"],
        "ivr_status": scenario["ivr_status"],
        "location_source": scenario["location_source"],
        "agent_name": entry["agent_name"],
        "elapsed": round(elapsed_clamped, 1),
        "duration": scenario["duration"],
        "ivr_seconds": IVR_SECONDS,
        "phase": phase,
        "finished": finished,
        "indicators": indicators,
        "score": result["score"],
        "raw_score": result["raw_score"],
        "level": result["level"],
        "level_key": result["level_key"],
        "recommendation": result["recommendation"],
        "actions": actions,
        "requested_action": requested,
        "step_up": {
            "required": su is not None,
            "channel_label": su["channel_label"] if su else None,
            "sent_at": su["sent_at_sec"] if su else None,
            "result": su["result"] if su else None,
            "resolved_at": su["resolved_at_sec"] if su else None,
        },
        "events": sorted(entry["events"], key=lambda e: e["at"]),
    }


def get_call_status(call_key: str) -> Optional[dict]:
    entry = _ACTIVE_CALLS.get(call_key)
    return None if entry is None else _build_status(call_key, entry)


def list_active_calls() -> List[dict]:
    return [_build_status(k, e) for k, e in _ACTIVE_CALLS.items()]


def finish_call(call_key: str) -> Optional[dict]:
    entry = _ACTIVE_CALLS.pop(call_key, None)
    if entry is None:
        return None
    final = _build_status(call_key, entry)
    final["step_up"]["code_hash"] = entry["step_up"]["code_hash"] if entry["step_up"] else None
    return final
