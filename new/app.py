# -*- coding: utf-8 -*-
"""VeriCall - אפליקציית Flask להערכת סיכון מבוססת RBA בשיחת שירות בנקאי."""
import os
from datetime import datetime

from flask import Flask, abort, jsonify, redirect, render_template, request, session, url_for

import analytics
import audit
import auth
import db
import otp_service
import policy
import risk_engine
import simulator

app = Flask(__name__)
# מפתח סשן להדגמה בלבד - בסביבת production יש להגדיר משתנה סביבה SECRET_KEY אמיתי וסודי
app.secret_key = os.environ.get("SECRET_KEY", "dev-only-secret-change-me")
db.init_db(app)


@app.before_request
def warm_caches():
    """טוען קטלוג/ספים/מדיניות מה-DB לזיכרון פעם אחת בכל בקשה (זול, ומאפשר כיול חי)."""
    conn = db.get_db()
    risk_engine.load_indicators(conn)
    risk_engine.load_levels(conn)
    policy.load_policy(conn)


@app.context_processor
def inject_agent():
    return {"current_agent": session.get("agent_name")}


# ---------------------------------------------------------------- ציבורי

@app.get("/")
def index():
    return render_template("index.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html", error=None)

    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    if auth.verify_login(username, password):
        session["agent_name"] = username
        conn = db.get_db()
        audit.write(conn, None, username, "login", "התחברות נציג למערכת")
        conn.commit()
        next_url = request.args.get("next") or url_for("dashboard")
        return redirect(next_url)

    return render_template("login.html", error="שם משתמש או סיסמה שגויים"), 401


@app.get("/logout")
def logout():
    session.pop("agent_name", None)
    return redirect(url_for("login"))


# נתיב דינמי לפי דרישת המרצה - שם המשתמש מועבר ל-Jinja2 ומוצג בעמוד
@app.get("/user/<name>")
def user(name):
    return render_template("user.html", name=name)


@app.get("/compare")
def compare():
    return render_template("compare.html")


# ---------------------------------------------------------------- תיעוד ידני

def _persist_call(conn, *, customer_name, phone, account_number, agent_name, notes,
                  call_type, caller_number, ivr_outcome, handle_seconds,
                  indicators, result, step_up, audit_events):
    """שומר שיחה + אינדיקציות + הערכה + Step-Up + יומן ביקורת. משמש גם לידני וגם לחי."""
    cur = conn.cursor()

    customer_id = None
    if account_number:
        row = cur.execute("SELECT customer_id FROM customers WHERE account_number = ?", (account_number,)).fetchone()
        if row:
            customer_id = row["customer_id"]
    if customer_id is None:
        cur.execute("INSERT INTO customers (full_name, phone, account_number) VALUES (?, ?, ?)",
                    (customer_name, phone or None, account_number or None))
        customer_id = cur.lastrowid

    call_time = datetime.now().isoformat(timespec="seconds")
    cur.execute(
        """INSERT INTO calls (customer_id, agent_name, call_time, notes, call_type,
                              caller_number, ivr_outcome, handle_seconds)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (customer_id, agent_name, call_time, notes, call_type, caller_number, ivr_outcome, handle_seconds),
    )
    call_id = cur.lastrowid

    for ind in indicators:
        cur.execute(
            """INSERT INTO risk_indicators
               (call_id, indicator_key, indicator_label, weight, is_present, detected_phase, detected_at_sec)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (call_id, ind["key"], ind["label"], ind["weight"], int(ind["is_present"]),
             ind.get("detected_phase"), ind.get("triggered_at")),
        )

    cur.execute(
        """INSERT INTO risk_assessments
           (call_id, total_score, risk_level, recommendation, created_at, otp_required, otp_code, otp_sent_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (call_id, result["score"], result["level"], result["recommendation"], call_time,
         int(step_up["required"]), None, call_time if step_up["required"] else None),
    )

    if step_up["required"]:
        cur.execute(
            """INSERT INTO step_up_challenges (call_id, channel_type, code_hash, sent_at, result, resolved_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (call_id, step_up["channel"], step_up["code_hash"], call_time,
             step_up.get("result") or "pending", call_time if step_up.get("result") else None),
        )

    for ev in audit_events:
        audit.write(conn, call_id, ev["actor"], ev["action"], ev.get("details", ""))

    conn.commit()
    return call_id


@app.route("/call/new", methods=["GET", "POST"])
@auth.login_required
def new_call():
    conn = db.get_db()
    indicators = risk_engine.manual_indicators(conn)

    if request.method == "GET":
        return render_template("call_form.html", indicators=indicators, error=None, form={})

    customer_name = request.form.get("customer_name", "").strip()
    agent_name = request.form.get("agent_name", "").strip()
    if not customer_name or not agent_name:
        return render_template("call_form.html", indicators=indicators,
                               error="יש למלא שם לקוח ושם נציג", form=request.form), 400

    selected = {i["key"]: bool(request.form.get(i["key"])) for i in indicators}
    result = risk_engine.calculate_risk(selected, indicators, conn)
    step = otp_service.build_step_up(result["level_key"])
    step_up = {"required": step["required"], "channel": step["channel"],
               "code_hash": otp_service.hash_code(step["code"]) if step["code"] else None, "result": None}

    ind_rows = [{**i, "is_present": selected[i["key"]], "detected_phase": "agent", "triggered_at": None}
                for i in indicators]

    events = [{"actor": agent_name, "action": "manual_record", "details": "תיעוד ידני של שיחה"},
              {"actor": "system", "action": "risk_scored",
               "details": f"ציון {result['score']} - רמה {result['level']}"}]
    if step["required"]:
        events.append({"actor": "system", "action": "step_up_sent", "details": otp_service.CHANNEL_LABEL})

    call_id = _persist_call(
        conn, customer_name=customer_name, phone=request.form.get("phone", "").strip(),
        account_number=request.form.get("account_number", "").strip(), agent_name=agent_name,
        notes=request.form.get("notes", "").strip(), call_type="manual",
        caller_number=request.form.get("phone", "").strip() or None, ivr_outcome=None, handle_seconds=None,
        indicators=ind_rows, result=result, step_up=step_up, audit_events=events,
    )
    return redirect(url_for("call_result", call_id=call_id))


@app.get("/call/<int:call_id>")
@auth.login_required
def call_result(call_id):
    conn = db.get_db()
    call = conn.execute(
        """SELECT calls.*, customers.full_name, customers.phone, customers.account_number
           FROM calls JOIN customers ON calls.customer_id = customers.customer_id
           WHERE call_id = ?""", (call_id,)).fetchone()
    if call is None:
        abort(404)

    indicators = conn.execute("SELECT * FROM risk_indicators WHERE call_id = ?", (call_id,)).fetchall()
    assessment = conn.execute("SELECT * FROM risk_assessments WHERE call_id = ?", (call_id,)).fetchone()
    challenge = conn.execute("SELECT * FROM step_up_challenges WHERE call_id = ?", (call_id,)).fetchone()
    level_key = next((lv["key"] for lv in risk_engine.load_levels(conn) if lv["label"] == assessment["risk_level"]), "low")

    return render_template("call_result.html", call=call, indicators=indicators, assessment=assessment,
                           challenge=challenge, actions=policy.actions_for_level(level_key, conn),
                           audit_rows=audit.for_call(conn, call_id))


@app.get("/calls")
@auth.login_required
def calls_list():
    conn = db.get_db()
    rows = conn.execute(
        """SELECT calls.call_id, calls.call_time, calls.agent_name, calls.call_type, customers.full_name,
                  risk_assessments.total_score, risk_assessments.risk_level
           FROM calls
           JOIN customers ON calls.customer_id = customers.customer_id
           LEFT JOIN risk_assessments ON calls.call_id = risk_assessments.call_id
           ORDER BY calls.call_id DESC""").fetchall()
    return render_template("calls_list.html", calls=rows)


# API לחישוב חי בטופס הידני
@app.post("/api/score")
@auth.login_required
def api_score():
    conn = db.get_db()
    indicators = risk_engine.manual_indicators(conn)
    data = request.get_json(silent=True) or {}
    selected = {i["key"]: bool(data.get(i["key"])) for i in indicators}
    return jsonify(risk_engine.calculate_risk(selected, indicators, conn))


# ---------------------------------------------------------------- סימולטור חי

@app.get("/dashboard")
@auth.login_required
def dashboard():
    return render_template("dashboard.html", scenarios=simulator.SCENARIOS)


@app.post("/dashboard/start/<scenario_id>")
@auth.login_required
def dashboard_start(scenario_id):
    if scenario_id not in simulator.SCENARIOS:
        abort(404)
    call_key = simulator.start_call(scenario_id, session["agent_name"])
    return redirect(url_for("live_call", call_key=call_key))


@app.get("/dashboard/call/<call_key>")
@auth.login_required
def live_call(call_key):
    status = simulator.get_call_status(call_key)
    if status is None:
        abort(404)
    return render_template("live_call.html", call_key=call_key, status=status)


@app.get("/api/dashboard/live")
@auth.login_required
def api_dashboard_live():
    calls = simulator.list_active_calls()
    for c in calls:
        c["url"] = url_for("live_call", call_key=c["call_key"])
    return jsonify(calls)


@app.get("/api/live-call/<call_key>")
@auth.login_required
def api_live_call(call_key):
    status = simulator.get_call_status(call_key)
    if status is None:
        return jsonify({"error": "not_found"}), 404
    return jsonify(status)


@app.post("/api/live-call/<call_key>/step-up/<result>")
@auth.login_required
def api_step_up_resolve(call_key, result):
    if result not in ("approved", "failed"):
        abort(400)
    status = simulator.resolve_step_up(call_key, result)
    if status is None:
        return jsonify({"error": "no_pending_step_up"}), 409
    return jsonify(status)


@app.post("/dashboard/call/<call_key>/finish")
@auth.login_required
def finish_live_call(call_key):
    final = simulator.finish_call(call_key)
    if final is None:
        abort(404)

    agent_action = request.form.get("agent_action", "continue")
    action_labels = {"continue": "הנציג המשיך בטיפול רגיל",
                     "step_up_wait": "הנציג המתין לתוצאת Step-Up",
                     "escalate": "הנציג עצר את הפעולה והסלים לבקרת הונאות"}

    events = [{"actor": "system", "action": ev["actor"], "details": f"[{ev['at']}s] {ev['text']}"}
              for ev in final["events"]]
    events.append({"actor": final["agent_name"], "action": "agent_decision",
                   "details": action_labels.get(agent_action, agent_action)})

    su = final["step_up"]
    step_up = {"required": su["required"], "channel": otp_service.CHANNEL_TYPE if su["required"] else None,
               "code_hash": su.get("code_hash"), "result": su["result"]}

    conn = db.get_db()
    call_id = _persist_call(
        conn, customer_name=final["customer_name"], phone=final["caller_number"], account_number=None,
        agent_name=final["agent_name"], notes=final["scenario_title"], call_type="live",
        caller_number=final["caller_number"], ivr_outcome=final["ivr_status"],
        handle_seconds=int(final["elapsed"]), indicators=final["indicators"],
        result={"score": final["score"], "level": final["level"], "recommendation": final["recommendation"]},
        step_up=step_up, audit_events=events,
    )
    return redirect(url_for("call_result", call_id=call_id))


# ---------------------------------------------------------------- אנליטיקה ואודיט

@app.get("/analytics")
@auth.login_required
def analytics_dashboard():
    conn = db.get_db()
    return render_template(
        "analytics.html",
        summary=analytics.get_summary(conn),
        kpis=analytics.get_kpis(conn),
        risk_distribution=analytics.get_risk_distribution(conn),
        top_indicators=analytics.get_top_indicators(conn),
        repeat_targets=analytics.get_repeat_targets(conn),
        recent_high_risk=analytics.get_recent_high_risk(conn),
    )


@app.get("/audit")
@auth.login_required
def audit_log_view():
    conn = db.get_db()
    return render_template("audit_log.html", rows=audit.recent(conn))


@app.errorhandler(404)
def not_found(_error):
    return render_template("404.html"), 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5050, debug=False)
