from fastapi.testclient import TestClient

from tradecore.app import app


def test_health_endpoint():
    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["mode"] in ("paper", "backtest", "live")
