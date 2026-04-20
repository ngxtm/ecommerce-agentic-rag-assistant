import json
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.backend.main import app
from app.backend.models import Intent, SessionState, SourceItem


EVENT_VERSION = 1
STREAMING_ORDER_FALLBACK_MESSAGE = "Streaming is only available for knowledge questions."
client = TestClient(app)


def _session_state() -> SessionState:
    return SessionState(session_id="test-session", current_intent=Intent.KNOWLEDGE_QA)


def test_health_returns_ok() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@patch("app.backend.orchestrator.session_store.save")
@patch("app.backend.orchestrator.session_store.append_message")
@patch("app.backend.orchestrator.session_store.load")
def test_chat_returns_mock_order_flow_response(mock_load, mock_append, mock_save) -> None:
    mock_load.return_value = _session_state()
    mock_append.return_value = _session_state()
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


@patch("app.backend.orchestrator.session_store.save")
@patch("app.backend.orchestrator.session_store.append_message")
@patch("app.backend.orchestrator.session_store.load")
@patch("app.backend.orchestrator.answer_question")
def test_chat_returns_numeric_knowledge_response_with_source_metadata(mock_answer_question, mock_load, mock_append, mock_save) -> None:
    mock_load.return_value = _session_state()
    mock_append.return_value = _session_state()
    mock_answer_question.return_value = (
        "Net sales were 280,522 in 2019.",
        [
            SourceItem(
                source_id="amazon-row-1",
                title="Item 6. Selected Consolidated Financial Data - Net sales (2019)",
                snippet="Net sales for 2019: 280,522",
                content_type="table_row",
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


@patch("app.backend.orchestrator.session_store.save")
@patch("app.backend.orchestrator.session_store.append_message")
@patch("app.backend.orchestrator.session_store.load")
@patch("app.backend.orchestrator.stream_answer_question")
def test_chat_stream_returns_sse_delta_and_final_events(mock_stream_answer_question, mock_load, mock_append, mock_save) -> None:
    mock_load.return_value = _session_state()
    mock_append.return_value = _session_state()
    mock_stream_answer_question.return_value = (
        iter(["Net sales ", "were 280,522 in 2019."]),
        [
            SourceItem(
                source_id="amazon-row-1",
                title="Item 6. Selected Consolidated Financial Data - Net sales (2019)",
                snippet="Net sales for 2019: 280,522",
                content_type="table_row",
                item="Item 6. Selected Consolidated Financial Data",
                page_start=8,
                page_end=8,
                metric="Net sales",
                year="2019",
                table_name="Item 6. Selected Consolidated Financial Data",
            )
        ],
    )

    with client.stream(
        "POST",
        "/chat/stream",
        json={"session_id": "stream-session-1", "message": "What were net sales in 2019?"},
    ) as response:
        assert response.status_code == 200
        body = "\n".join(
            line.decode("utf-8") if isinstance(line, bytes) else line
            for line in response.iter_lines()
            if line
        )

    assert "event: delta" in body
    assert "event: final" in body
    assert '"event_version": 1' in body
    assert '"session_update_status": "committed"' in body
    assert '"full_answer": "Net sales were 280,522 in 2019."' in body


@patch("app.backend.orchestrator.session_store.append_message")
@patch("app.backend.orchestrator.session_store.load")
@patch("app.backend.orchestrator.stream_answer_question")
def test_chat_stream_returns_terminal_error_event_when_stream_fails(mock_stream_answer_question, mock_load, mock_append) -> None:
    mock_load.return_value = _session_state()
    mock_append.return_value = _session_state()
    def failing_stream():
        yield "partial"
        raise RuntimeError("boom")

    mock_stream_answer_question.return_value = (failing_stream(), [])

    with client.stream(
        "POST",
        "/chat/stream",
        json={"session_id": "stream-session-2", "message": "What were net sales in 2019?"},
    ) as response:
        assert response.status_code == 200
        body = "\n".join(
            line.decode("utf-8") if isinstance(line, bytes) else line
            for line in response.iter_lines()
            if line
        )

    assert "event: delta" in body
    assert "event: error" in body
    assert '"event_version": 1' in body
    assert '"session_update_status": "not_committed"' in body


@patch("app.backend.orchestrator.session_store.load")
def test_chat_stream_rejects_order_status_requests(mock_load) -> None:
    mock_load.return_value = _session_state()
    response = client.post(
        "/chat/stream",
        json={
            "session_id": "session-order-stream",
            "message": "Where is my order?",
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": STREAMING_ORDER_FALLBACK_MESSAGE}


@patch("app.backend.orchestrator.session_store.save")
@patch("app.backend.orchestrator.session_store.append_message")
@patch("app.backend.orchestrator.session_store.load")
@patch("app.backend.orchestrator.stream_answer_question")
def test_chat_stream_final_event_contains_sources_metadata(mock_stream_answer_question, mock_load, mock_append, mock_save) -> None:
    mock_load.return_value = _session_state()
    mock_append.return_value = _session_state()
    mock_stream_answer_question.return_value = (
        iter(["Item 6 includes net sales."]),
        [
            SourceItem(
                source_id="amazon-row-1",
                title="Item 6. Selected Consolidated Financial Data - Net sales (2019)",
                snippet="Net sales for 2019: 280,522",
                content_type="table_row",
                item="Item 6. Selected Consolidated Financial Data",
                page_start=8,
                page_end=8,
                metric="Net sales",
                year="2019",
                table_name="Item 6. Selected Consolidated Financial Data",
            )
        ],
    )

    with client.stream(
        "POST",
        "/chat/stream",
        json={"session_id": "stream-session-3", "message": "What is Item 6?"},
    ) as response:
        assert response.status_code == 200
        lines = [
            line.decode("utf-8") if isinstance(line, bytes) else line
            for line in response.iter_lines()
            if line
        ]

    final_data_lines = [line for line in lines if line.startswith("data:") and '"full_answer"' in line]
    assert len(final_data_lines) == 1
    payload = json.loads(final_data_lines[0].split(":", 1)[1].strip())
    assert payload["event_version"] == EVENT_VERSION
    assert payload["session_update_status"] == "committed"
    assert payload["sources"][0]["metric"] == "Net sales"
    assert payload["sources"][0]["year"] == "2019"
    assert payload["sources"][0]["page_start"] == 8
    assert payload["sources"][0]["page_end"] == 8
    assert payload["full_answer"] == "Item 6 includes net sales."

    mock_stream_answer_question.assert_called_once_with("What is Item 6?")


@patch("app.backend.orchestrator.session_store.save")
@patch("app.backend.orchestrator.session_store.append_message")
@patch("app.backend.orchestrator.session_store.load")
@patch("app.backend.orchestrator.answer_question")
def test_chat_order_flow_still_works_after_stream_addition(mock_answer_question, mock_load, mock_append, mock_save) -> None:
    mock_load.return_value = _session_state()
    mock_append.return_value = _session_state()
    response = client.post(
        "/chat",
        json={
            "session_id": "session-123-order-regression",
            "message": "Where is my order?",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["intent"] == "ORDER_STATUS"
    assert payload["next_action"] == "ASK_USER"
    assert payload["verification_state"]["missing_fields"] == ["full_name", "date_of_birth", "ssn_last4"]
    mock_answer_question.assert_not_called()
