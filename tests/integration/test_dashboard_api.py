from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from tradecore.app import app, get_session_token
from tradecore.core.config import get_settings
from tradecore.core.state import get_state


@pytest.fixture
def client():
    # Force reload/cleanup state
    state = get_state()
    state.set_kill_switch(False)
    state.reset_rejections()
    state.set_strategy_paused(False)

    # Ensure config has default settings
    settings = get_settings()
    settings.trading.mode = "paper"

    with TestClient(app) as c:
        yield c


def test_api_health(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_api_status(client):
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "equity" in data
    assert "balance" in data
    assert "killswitch" in data
    assert "paused" in data


def test_api_positions(client):
    response = client.get("/api/positions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_api_trades(client):
    response = client.get("/api/trades?mode=paper&page=1&page_size=10")
    assert response.status_code == 200
    data = response.json()
    assert "items" in data
    assert "total" in data


def test_api_trades_csv_export(client):
    response = client.get("/api/trades/export.csv?mode=paper")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "trades_export_paper.csv" in response.headers["content-disposition"]


def test_api_equity(client):
    response = client.get("/api/equity?range=all")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_api_signals(client):
    response = client.get("/api/signals?limit=10")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_api_preflight(client):
    response = client.get("/api/mode/preflight")
    assert response.status_code == 200
    data = response.json()
    assert "checks" in data
    assert "can_go_live" in data


def test_api_mode_transitions(client):
    # Transition to paper should be auto-approved
    response = client.post("/api/mode", json={"target": "paper"})
    assert response.status_code == 200
    assert response.json()["mode"] == "paper"

    # Transition to live with wrong confirmation should fail
    response = client.post("/api/mode", json={"target": "live", "confirmation": "BAD"})
    assert response.status_code == 409


def test_api_killswitch_trigger_and_rearm(client):
    response = client.post("/api/killswitch")
    assert response.status_code == 200
    assert response.json()["status"] == "triggered"
    assert get_state().kill_switch_active is True

    # Rearm with invalid text should fail
    response = client.post("/api/killswitch/rearm", json={"confirmation": "INVALID"})
    assert response.status_code == 409

    # Rearm with correct text should succeed
    response = client.post("/api/killswitch/rearm", json={"confirmation": "RE-ARM"})
    assert response.status_code == 200
    assert response.json()["status"] == "armed"
    assert get_state().kill_switch_active is False


def test_api_pause_resume_strategy(client):
    response = client.post("/api/strategy/pause")
    assert response.status_code == 200
    assert response.json()["paused"] is True
    assert get_state().strategy_paused is True

    response = client.post("/api/strategy/resume")
    assert response.status_code == 200
    assert response.json()["paused"] is False
    assert get_state().strategy_paused is False


def test_api_paper_reset_validation(client):
    # Should work in paper mode
    response = client.post("/api/paper/reset")
    assert response.status_code == 200
    assert response.json()["status"] == "reset"


def test_api_system_info(client):
    response = client.get("/api/system")
    assert response.status_code == 200
    data = response.json()
    assert "feeds" in data
    assert "jobs" in data
    assert "version" in data


def test_security_protection_on_0_0_0_0(client):
    settings = get_settings()

    # Temporarily force host to 0.0.0.0 to trigger security checks
    with patch.object(settings.dashboard, "host", "0.0.0.0"):
        # Without cookie, API request should return 401
        response = client.get("/api/status")
        assert response.status_code == 401
        assert "Unauthorized" in response.text

        # Without cookie, HTML request should redirect to /login
        response = client.get("/dashboard/static/index.html", follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"] == "/login"

        # Accessing with active correct session cookie should return 200
        client.cookies.set("session_id", get_session_token())
        response = client.get("/api/status")
        assert response.status_code == 200

        # Post request to /login should set sessioncookie and redirect
        client.cookies.clear()
        with patch.dict("os.environ", {"DASHBOARD_PASSWORD": "supersecretpassword"}):
            response = client.post(
                "/login",
                data={"password": "supersecretpassword"},
                follow_redirects=False,
            )
            assert response.status_code == 303
            assert response.headers["location"] == "/"
            assert "session_id=" in response.headers["set-cookie"]
