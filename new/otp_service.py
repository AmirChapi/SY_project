# -*- coding: utf-8 -*-
"""שירות אימות מוגבר (Step-Up) בערוץ בלתי-תלוי.

הסקירה: "יש לבחור גורם אימות נוסף שאינו תלוי, ככל האפשר, בערוץ שבו זוהה הסיכון."
לכן האישור נשלח לאפליקציית הבנק הרשומה (Push) - ולא למספר שממנו מתקשרים.

בהדגמה אין שער Push אמיתי; הקוד מוצג לנציג בתור סימולציה בלבד.
במערכת production הקוד ישלח אך ורק לערוץ הרשום ולעולם לא יוצג בממשק הנציג.
"""
import secrets

from werkzeug.security import check_password_hash, generate_password_hash

CODE_LENGTH = 6
CHANNEL_TYPE = "bank_app_push"
CHANNEL_LABEL = "אפליקציית הבנק (Push) - ערוץ רשום, בלתי-תלוי במספר המתקשר"


def generate_otp_code() -> str:
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


def hash_code(code: str) -> str:
    return generate_password_hash(code)


def verify_code(code_hash: str, submitted: str) -> bool:
    return check_password_hash(code_hash, submitted)


def build_step_up(level_key: str) -> dict:
    """נמוך - אין צורך. בינוני - שולחים Push. גבוה - לא שולחים, עוצרים ומסלימים."""
    if level_key == "medium":
        return {
            "required": True,
            "code": generate_otp_code(),
            "channel": CHANNEL_TYPE,
            "channel_label": CHANNEL_LABEL,
        }
    return {"required": False, "code": None, "channel": None, "channel_label": None}
