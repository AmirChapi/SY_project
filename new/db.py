# -*- coding: utf-8 -*-
"""שכבת גישה פשוטה לבסיס הנתונים SQLite."""
import sqlite3
from pathlib import Path

from flask import g

DB_PATH = Path(__file__).parent / "bank_risk.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
    full_name TEXT NOT NULL,
    phone TEXT,
    account_number TEXT UNIQUE
);

CREATE TABLE IF NOT EXISTS calls (
    call_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    agent_name TEXT NOT NULL,
    call_time TEXT NOT NULL,
    notes TEXT,
    call_type TEXT NOT NULL DEFAULT 'manual',
    FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
);

CREATE TABLE IF NOT EXISTS risk_indicators (
    indicator_id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id INTEGER NOT NULL,
    indicator_key TEXT NOT NULL,
    indicator_label TEXT NOT NULL,
    weight INTEGER NOT NULL,
    is_present INTEGER NOT NULL,
    FOREIGN KEY (call_id) REFERENCES calls (call_id)
);

CREATE TABLE IF NOT EXISTS risk_assessments (
    assessment_id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id INTEGER NOT NULL UNIQUE,
    total_score INTEGER NOT NULL,
    risk_level TEXT NOT NULL,
    recommendation TEXT NOT NULL,
    created_at TEXT NOT NULL,
    otp_required INTEGER NOT NULL DEFAULT 0,
    otp_code TEXT,
    otp_sent_at TEXT,
    FOREIGN KEY (call_id) REFERENCES calls (call_id)
);

-- קטלוג אינדיקציות - המשקלים נשמרים בטבלה כדי לאפשר כיול ללא שינוי קוד (Wiefling 2021)
CREATE TABLE IF NOT EXISTS indicator_catalog (
    indicator_key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    category TEXT NOT NULL,
    source TEXT NOT NULL,
    weight INTEGER NOT NULL,
    is_auto INTEGER NOT NULL DEFAULT 0
);

-- ספי רמות הסיכון - ניתנים לכיול
CREATE TABLE IF NOT EXISTS risk_levels (
    level_key TEXT PRIMARY KEY,
    label TEXT NOT NULL,
    min_score INTEGER NOT NULL,
    max_score INTEGER NOT NULL,
    recommendation TEXT NOT NULL,
    sort_order INTEGER NOT NULL
);

-- מטריצת פעולות מותרות/חסומות לפי רמת סיכון
CREATE TABLE IF NOT EXISTS policy_rules (
    rule_id INTEGER PRIMARY KEY AUTOINCREMENT,
    level_key TEXT NOT NULL,
    action_key TEXT NOT NULL,
    action_label TEXT NOT NULL,
    allowed INTEGER NOT NULL,
    FOREIGN KEY (level_key) REFERENCES risk_levels (level_key)
);

-- ערוצים רשומים של הלקוח - משמשים ל-Step-Up בערוץ בלתי-תלוי במספר המתקשר
CREATE TABLE IF NOT EXISTS registered_channels (
    channel_id INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    channel_type TEXT NOT NULL,
    channel_value TEXT NOT NULL,
    is_verified INTEGER NOT NULL DEFAULT 1,
    FOREIGN KEY (customer_id) REFERENCES customers (customer_id)
);

-- אתגר Step-Up לשיחה - נשמר hash בלבד, לעולם לא הקוד עצמו
CREATE TABLE IF NOT EXISTS step_up_challenges (
    challenge_id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id INTEGER NOT NULL UNIQUE,
    channel_type TEXT NOT NULL,
    code_hash TEXT NOT NULL,
    sent_at TEXT NOT NULL,
    result TEXT NOT NULL DEFAULT 'pending',
    resolved_at TEXT,
    FOREIGN KEY (call_id) REFERENCES calls (call_id)
);

-- יומן ביקורת - כל החלטה של המערכת וכל פעולה של הנציג מתועדות
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id INTEGER,
    actor TEXT NOT NULL,
    action TEXT NOT NULL,
    details TEXT,
    logged_at TEXT NOT NULL,
    FOREIGN KEY (call_id) REFERENCES calls (call_id)
);
"""


SEED_INDICATORS = [
    # (key, label, category, source, weight, is_auto)
    # אינדיקציות ידניות - הנציג מסמן בעצמו
    ("caller_id_mismatch", "מספר המתקשר אינו תואם את הטלפון הרשום", "רשת", "מרכזיית טלפוניה (CLI)", 25, 0),
    ("failed_security_answers", "תשובות שגויות לשאלות זיהוי", "אימות", "נציג", 25, 0),
    ("sensitive_change_request", "בקשה לשינוי פרטים רגישים (טלפון / דוא\"ל / כתובת)", "פעולה", "נציג", 15, 0),
    ("multiple_otp_failures", "כשלים חוזרים בהזנת קוד חד פעמי (OTP)", "אימות", "מערכת IVR", 20, 0),
    ("unusual_call_time", "שעת שיחה חריגה (לילה / שעות לא שגרתיות)", "זמן", "שעון מערכת", 5, 0),
    ("previous_fraud_flag", "קיים סימון הונאה קודם על החשבון", "היסטוריה", "מערכת בקרת הונאות", 30, 0),
    ("pressure_to_bypass", "הלקוח לוחץ על הנציג לעקוף את נהלי הזיהוי", "התנהגות", "נציג", 20, 0),
    # אינדיקציות אוטומטיות - מתגלות בשלב IVR / המתנה
    ("caller_number_mismatch", "המספר המתקשר אינו תואם למספר הרשום בבנק", "רשת", "מרכזיית טלפוניה (CLI)", 20, 1),
    ("unusual_hour", "שיחה בשעה חריגה (לילה / שעות לא שגרתיות)", "זמן", "שעון מערכת + היסטוריית לקוח", 15, 1),
    ("foreign_call", "השיחה מגיעה ממספר / כתובת IP בחו\"ל", "רשת", "קידומת בינלאומית + GeoIP", 20, 1),
    ("location_jump", "שינוי מיקום פתאומי לעומת שיחות קודמות", "היסטוריה", "היסטוריית מיקומים", 15, 1),
    ("device_sim_swap", "זוהה מכשיר / SIM שהוחלף לאחרונה", "מכשיר", "ספק סלולר (SIM Swap API)", 25, 1),
    ("rapid_repeat_calls", "ריבוי שיחות קצרות מאותו מספר בזמן קצר", "התנהגות", "יומן שיחות המוקד", 15, 1),
    ("synthetic_voice", "זוהה קול סינתטי / הקלטה (אינדיקציה קולית)", "ביומטריה", "ניתוח קול (placeholder)", 30, 1),
    ("urgency_pressure", "דחיפות ולחץ על הנציג לעקוף נהלים (Pretexting)", "התנהגות", "נציג / ניתוח שיחה", 25, 1),
]

SEED_LEVELS = [
    # (key, label, min, max, recommendation, sort_order)
    ("low", "נמוך", 0, 29, "ניתן להמשיך בתהליך הרגיל", 1),
    ("medium", "בינוני", 30, 59, "יש לדרוש אימות מוגבר (Step-Up) בערוץ רשום לפני המשך הטיפול", 2),
    ("high", "גבוה", 60, 100, "יש לעצור פעולות רגישות ולהסלים את האירוע לבקרת הונאות", 3),
]

# פעולות במוקד ומה מותר בכל רמה - מטריצת המדיניות המדורגת
SEED_POLICY = [
    # (level_key, action_key, action_label, allowed)
    ("low", "balance_inquiry", "בירור יתרה ותנועות", 1),
    ("low", "card_block", "חסימת כרטיס", 1),
    ("low", "transfer", "העברה בנקאית", 1),
    ("low", "contact_change", "שינוי פרטי קשר (טלפון / כתובת)", 1),
    ("medium", "balance_inquiry", "בירור יתרה ותנועות", 1),
    ("medium", "card_block", "חסימת כרטיס", 1),
    ("medium", "transfer", "העברה בנקאית", 0),
    ("medium", "contact_change", "שינוי פרטי קשר (טלפון / כתובת)", 0),
    ("high", "balance_inquiry", "בירור יתרה ותנועות", 0),
    ("high", "card_block", "חסימת כרטיס", 1),
    ("high", "transfer", "העברה בנקאית", 0),
    ("high", "contact_change", "שינוי פרטי קשר (טלפון / כתובת)", 0),
]


def _seed(conn):
    """מזין טבלאות קונפיגורציה. INSERT OR IGNORE - מוסיף מפתחות חדשים בלי לדרוס כיול שבוצע ידנית."""
    conn.executemany(
        "INSERT OR IGNORE INTO indicator_catalog (indicator_key, label, category, source, weight, is_auto) VALUES (?, ?, ?, ?, ?, ?)",
        SEED_INDICATORS,
    )
    conn.executemany(
        "INSERT OR IGNORE INTO risk_levels (level_key, label, min_score, max_score, recommendation, sort_order) VALUES (?, ?, ?, ?, ?, ?)",
        SEED_LEVELS,
    )
    if conn.execute("SELECT COUNT(*) FROM policy_rules").fetchone()[0] == 0:
        conn.executemany(
            "INSERT INTO policy_rules (level_key, action_key, action_label, allowed) VALUES (?, ?, ?, ?)",
            SEED_POLICY,
        )


def get_db():
    """מחזיר חיבור לבסיס הנתונים, אחד לכל בקשה (מאוחסן ב-g)."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(_exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


_teardown_registered = False


def init_db(app):
    """יוצר את הטבלאות אם אינן קיימות ורושם ניקוי חיבור בסיום כל בקשה."""
    global _teardown_registered
    with app.app_context():
        conn = sqlite3.connect(DB_PATH)
        conn.executescript(SCHEMA)
        # מיגרציה עבור בסיסי נתונים ישנים שנוצרו לפני הוספת העמודות החדשות
        migrations = [
            "ALTER TABLE calls ADD COLUMN call_type TEXT NOT NULL DEFAULT 'manual'",
            "ALTER TABLE risk_assessments ADD COLUMN otp_required INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE risk_assessments ADD COLUMN otp_code TEXT",
            "ALTER TABLE risk_assessments ADD COLUMN otp_sent_at TEXT",
            "ALTER TABLE calls ADD COLUMN caller_number TEXT",
            "ALTER TABLE calls ADD COLUMN ivr_outcome TEXT",
            "ALTER TABLE calls ADD COLUMN handle_seconds INTEGER",
            "ALTER TABLE risk_indicators ADD COLUMN detected_phase TEXT",
            "ALTER TABLE risk_indicators ADD COLUMN detected_at_sec REAL",
        ]
        for statement in migrations:
            try:
                conn.execute(statement)
            except sqlite3.OperationalError:
                pass  # העמודה כבר קיימת
        _seed(conn)
        conn.commit()
        conn.close()
    # רושמים את פונקציית הניקוי פעם אחת בלבד, כדי לתמוך בקריאה חוזרת ל-init_db (למשל בבדיקות)
    if not _teardown_registered:
        app.teardown_appcontext(close_db)
        _teardown_registered = True
