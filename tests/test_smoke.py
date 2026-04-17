from fastapi.testclient import TestClient

from app.backend.main import app


client = TestClient(app)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_chat_returns_mock_order_flow_response() -> None:
    response = client.post(
        "/chat",
        json={
            "session_id": "session-123",
            "message": "Where is my order?",
        },
    )

    assert response.status_code == 200

    payload = response.json()
    assert payload["intent"] == "ORDER_STATUS"
    assert payload["next_action"] == "ASK_USER"
    assert payload["verification_state"]["missing_fields"] == [
        "full_name",
        "date_of_birth",
        "ssn_last4",
    ]
