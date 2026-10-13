# -*- coding: utf-8 -*-
"""אימות בסיסי להדגמה - משתמש קבוע אחד, ללא ניהול הרשמה מלא."""
from functools import wraps

from flask import redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

# משתמש יחיד קבוע להדגמה בכיתה. במערכת אמיתית יש לנהל משתמשים בבסיס הנתונים עם סיסמאות מוצפנות בלבד.
_AGENTS = {
    "agent": generate_password_hash("1234"),
}


def verify_login(username: str, password: str) -> bool:
    hashed = _AGENTS.get(username)
    return hashed is not None and check_password_hash(hashed, password)


def login_required(view_func):
    """דקורטור שמגן על נתיבים פנימיים של המערכת ומחייב התחברות."""

    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if not session.get("agent_name"):
            return redirect(url_for("login", next=request.path))
        return view_func(*args, **kwargs)

    return wrapped
