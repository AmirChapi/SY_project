# -*- coding: utf-8 -*-
"""בדיקות לאפליקציה - מסלולי מרצה, לוגין, מנוע סיכון, Step-Up, מדיניות ואודיט."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import app as flask_app_module  # noqa: E402
import db  # noqa: E402
import risk_engine  # noqa: E402
import simulator  # noqa: E402


@pytest.fixture
def client(tmp_path, monkeypatch):
    # בסיס נתונים זמני לכל בדיקה כדי לא לפגוע בנתונים האמיתיים
    monkeypatch.setattr(db, "DB_PATH", tmp_path / "test.db")
    db.init_db(flask_app_module.app)
    return flask_app_module.app.test_client()


def login(c):
    return c.post("/login", data={"username": "agent", "password": "1234"}, follow_redirects=True)


# ---------------------------------------------------------------- דרישות המרצה

def test_index_page(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "VeriCall".encode() in r.data


def test_user_dynamic_route(client):
    r = client.get("/user/efi")
    assert r.status_code == 200
    assert b"efi" in r.data


def test_404_page(client):
    assert client.get("/no-such-page").status_code == 404


def test_compare_is_public(client):
    r = client.get("/compare")
    assert r.status_code == 200
    assert "הבעיה מול השוק".encode() not in r.data
    assert "VeriCall".encode() in r.data


# ---------------------------------------------------------------- אימות

def test_login_required_redirects(client):
    r = client.get("/dashboard")
    assert r.status_code == 302 and "/login" in r.headers["Location"]


def test_login_flow_writes_audit(client):
    r = login(client)
    assert r.status_code == 200
    r = client.get("/audit")
    assert "login".encode() in r.data


# ---------------------------------------------------------------- מנוע סיכון

def test_thresholds_from_db(client):
    with flask_app_module.app.app_context():
        conn = db.get_db()
        levels = risk_engine.load_levels(conn)
    assert [lv["key"] for lv in levels] == ["low", "medium", "high"]
    assert risk_engine.classify(0)["level_key"] == "low"
    assert risk_engine.classify(45)["level_key"] == "medium"
    assert risk_engine.classify(60)["level_key"] == "high"


def test_step_up_adjustment_changes_level():
    auto = risk_engine.auto_indicators()
    selected = {"caller_number_mismatch": True, "foreign_call": True}
    base = risk_engine.calculate_risk(selected, auto)
    assert base["level_key"] == "medium"
    approved = risk_engine.calculate_risk(selected, auto, adjustment=risk_engine.STEP_UP_APPROVED_ADJUSTMENT)
    failed = risk_engine.calculate_risk(selected, auto, adjustment=risk_engine.STEP_UP_FAILED_ADJUSTMENT)
    assert approved["level_key"] == "low"
    assert failed["level_key"] == "high"


# ---------------------------------------------------------------- Step-Up

def test_otp_only_for_medium():
    import otp_service
    assert otp_service.build_step_up("medium")["required"] is True
    assert otp_service.build_step_up("low")["required"] is False
    assert otp_service.build_step_up("high")["required"] is False
    code = otp_service.generate_otp_code()
    assert otp_service.verify_code(otp_service.hash_code(code), code)


# ---------------------------------------------------------------- מדיניות

def test_policy_blocks_sensitive_actions_at_medium():
    import policy
    medium = {a["action_key"]: a["allowed"] for a in policy.actions_for_level("medium")}
    assert medium["balance_inquiry"] is True
    assert medium["transfer"] is False
    assert medium["contact_change"] is False
    high = {a["action_key"]: a["allowed"] for a in policy.actions_for_level("high")}
    assert high["card_block"] is True  # חסימת כרטיס מותרת תמיד - מגנה על הלקוח


# ---------------------------------------------------------------- זרימות

def test_manual_call_medium_triggers_step_up(client):
    login(client)
    r = client.post("/call/new", data={
        "customer_name": "ישראל ישראלי", "agent_name": "נציג בדיקה",
        "previous_fraud_flag": "on", "pressure_to_bypass": "on",
    }, follow_redirects=True)
    assert r.status_code == 200
    assert "Step-Up".encode() in r.data
    assert "בינוני".encode() in r.data


def test_live_call_phases_and_step_up(client, monkeypatch):
    login(client)
    r = client.post("/dashboard/start/night_call_abroad", follow_redirects=True)
    assert r.status_code == 200
    call_key = r.request.path.rsplit("/", 1)[-1]

    # מדלגים על שלב ה-IVR בזמן
    entry = simulator._ACTIVE_CALLS[call_key]
    entry["started_at"] -= 8
    s = client.get(f"/api/live-call/{call_key}").get_json()
    assert s["phase"] == "step_up"
    assert s["step_up"]["required"] is True
    assert s["step_up"]["result"] == "pending"

    s = client.post(f"/api/live-call/{call_key}/step-up/failed").get_json()
    assert s["step_up"]["result"] == "failed"
    assert s["level_key"] == "high"
    assert s["phase"] == "resolved"

    r = client.post(f"/dashboard/call/{call_key}/finish", data={"agent_action": "escalate"}, follow_redirects=True)
    assert r.status_code == 200
    assert "הסלים".encode() in r.data
    assert "failed".encode() in r.data or "לא אישר".encode() in r.data


def test_false_positive_scenario_resolves_to_low(client):
    login(client)
    r = client.post("/dashboard/start/legit_customer_abroad", follow_redirects=True)
    call_key = r.request.path.rsplit("/", 1)[-1]
    simulator._ACTIVE_CALLS[call_key]["started_at"] -= 8
    client.get(f"/api/live-call/{call_key}")
    s = client.post(f"/api/live-call/{call_key}/step-up/approved").get_json()
    assert s["level_key"] == "low"
    assert s["score"] < s["raw_score"]


def test_analytics_page(client):
    login(client)
    r = client.get("/analytics")
    assert r.status_code == 200
    assert "False-Positive".encode() in r.data
