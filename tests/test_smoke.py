from unittest.mock import patch

from fastapi.testclient import TestClient

from app.backend.main import app
from app.backend.models import SourceItem


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
    assert payload["verification_state"]["missing_fields"] == ["full_name", "date_of_birth", "ssn_last4"]


@patch("app.backend.orchestrator.answer_question")
def test_chat_returns_numeric_knowledge_response_with_source_metadata(mock_answer_question) -> None:
    mock_answer_question.return_value = (
        "Net sales were 280,522 in 2019.",
        [
            SourceItem(
                source_id="amazon-row-1",
                title="Item 6. Selected Consolidated Financial Data - Net sales (2019)",
                snippet="Net sales for 2019: 280,522",
                item="Item 6. Selected Consolidated Financial Data",
                page_start=8,
                page_end=8,
                metric="Net sales",
                year="2019",
                table_name="Item 6. Selected Consolidated Financial Data",
            )
        ],
    )

    response = client.post(
        "/chat",
        json={
            "session_id": "session-numeric-001",
            "message": "What were net sales in 2019?",
        },
    )

    assert response.status_code == 200

    payload = response.json()
    assert payload["intent"] == "KNOWLEDGE_QA"
    assert payload["next_action"] == "RESPOND"
    assert "280,522" in payload["answer"]
    assert len(payload["sources"]) == 1
    assert payload["sources"][0]["metric"] == "Net sales"
    assert payload["sources"][0]["year"] == "2019"
    assert payload["sources"][0]["page_start"] == 8
    assert payload["sources"][0]["page_end"] == 8

    mock_answer_question.assert_called_once_with("What were net sales in 2019?")
