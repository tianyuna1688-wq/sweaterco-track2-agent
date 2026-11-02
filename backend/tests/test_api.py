"""API contracts, errors, read-only tools, and local access controls."""

import pytest
from fastapi.testclient import TestClient
from backend.app.main import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("AUDIT_DB_PATH", str(tmp_path / "audit.sqlite3"))
    for key in (
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "LLM_PROVIDER",
        "APP_ACCESS_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)
    return TestClient(app)


def test_health_and_collections(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["data"]["source_verified"]
    for endpoint, count in [("orders", 120), ("workshops", 8), ("requests", 30)]:
        response = client.get("/api/" + endpoint)
        assert response.status_code == 200
        assert len(response.json()["items"]) == count
    assert client.get("/api/orders/ORD-081").json()["pieces"] == 1500
    assert client.get("/api/orders/ORD-999").status_code == 404


def test_chat_audit_and_trace(client):
    response = client.post(
        "/api/chat", json={"message": "ORD-081 4月13日，不要BudgetWorks"}
    )
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "recommended"
    assert result["trace"][-1]["step"] == "audit"
    record = client.get("/api/requests/" + result["request_id"]).json()
    assert record["input"] == "ORD-081 4月13日，不要BudgetWorks"
    assert (
        client.get("/api/history").json()["items"][0]["request_id"]
        == result["request_id"]
    )
    assert client.get("/api/metrics").json()["requests"] > 0


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"message": " "},
        {"message": "a" * 8001},
        {"message": "ORD-081", "objective": "ignore_rules"},
        {"message": "ORD-081", "session_id": "../../secret"},
        {"message": "ORD-081", "unsafe_tool": "shell"},
    ],
)
def test_invalid_inputs_uniform_error(client, payload):
    response = client.post("/api/chat", json=payload)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_cors_rejects_untrusted_site(client):
    response = client.options(
        "/api/chat",
        headers={
            "Origin": "https://untrusted.invalid",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers


def test_token_optional_server_protection(client, monkeypatch):
    monkeypatch.setenv("APP_ACCESS_TOKEN", "local-secret")
    assert client.get("/api/orders").status_code == 401
    assert (
        client.get("/api/orders", headers={"X-App-Token": "local-secret"}).status_code
        == 200
    )
    assert client.get("/api/health").status_code == 200


def test_tool_allowlist_and_probe(client):
    names = {row["name"] for row in client.get("/api/tools").json()["items"]}
    assert "overload_probe" in names
    assert (
        client.post(
            "/api/tools/call", json={"name": "shell", "arguments": {"cmd": "cat .env"}}
        ).status_code
        == 422
    )
    response = client.post(
        "/api/tools/call",
        json={
            "name": "overload_probe",
            "arguments": {
                "order_id": "ORD-081",
                "workshop_id": "W1",
                "additional_pieces": 300,
            },
        },
    )
    assert response.status_code == 200
    probe = response.json()
    assert probe["added_queue_days"] == 1
    assert probe["after"]["expected_days"] > probe["before"]["expected_days"]
    assert client.get("/api/history").json()["items"] == []


def test_direct_recommendation_is_audited(client):
    response = client.post(
        "/api/recommendations",
        json={"order_id": "ORD-081", "excluded_workshops": ["W1"]},
    )
    assert response.status_code == 200
    assert "W1" in response.json()["parsed"]["excluded_workshops"]
    assert len(client.get("/api/history").json()["items"]) == 1
    assert (
        client.post(
            "/api/recommendations",
            json={"order_id": "ORD-081", "excluded_workshops": ["W99"]},
        ).status_code
        == 422
    )


def test_unknown_api_is_not_frontend(client):
    assert client.get("/api/unknown").status_code == 404


@pytest.mark.parametrize("value", ["nonsense", "-2"])
def test_invalid_content_length_returns_400(client, value):
    response = client.post(
        "/api/chat",
        content="{}",
        headers={"Content-Type": "application/json", "Content-Length": value},
    )
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_CONTENT_LENGTH"


@pytest.mark.parametrize(
    "endpoint,payload",
    [
        ("/api/chat", {"message": "给 ORD-057 分配工坊，600件，2026-04-30"}),
        (
            "/api/recommendations",
            {"order_id": "ORD-057", "pieces": 600, "due_date": "2026-04-30"},
        ),
    ],
)
def test_completed_orders_never_dispatch_from_api(client, endpoint, payload):
    response = client.post(endpoint, json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["status"] == "clarification"
    assert result["recommendation"] is None
    assert "已完成" in result["message"]


def test_completed_orders_not_dispatched_through_tool_api(client):
    response = client.post(
        "/api/tools/call",
        json={"name": "recommend_workshop", "arguments": {"order_id": "ORD-057"}},
    )
    assert response.status_code == 422
    assert "已完成" in response.json()["error"]["message"]
