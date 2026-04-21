from app.backend.observability import build_log_event, contains_possible_pii, redact_pii


def test_redact_pii_masks_dates_and_last4() -> None:
    redacted = redact_pii("DOB 15-06-1990 and SSN 1234")

    assert "15-06-1990" not in redacted
    assert "1234" not in redacted
    assert "[REDACTED_DATE]" in redacted
    assert "[REDACTED_4_DIGITS]" in redacted


def test_contains_possible_pii_detects_expected_patterns() -> None:
    assert contains_possible_pii("My DOB is 1990-06-15") is True
    assert contains_possible_pii("Last 4 is 1234") is True
    assert contains_possible_pii("What is the return policy?") is False


def test_build_log_event_omits_none_values() -> None:
    event = build_log_event("chat_request_completed", session_id="session-1", intent=None)

    assert event["event_type"] == "chat_request_completed"
    assert event["session_id"] == "session-1"
    assert "intent" not in event
    assert "timestamp" in event


def test_build_log_event_preserves_request_and_tool_fields() -> None:
    event = build_log_event(
        "order_workflow_succeeded",
        request_id="req-123",
        tool_name="order_status_tool",
        tool_result_summary="order_found",
        fallback_used=False,
    )

    assert event["request_id"] == "req-123"
    assert event["tool_name"] == "order_status_tool"
    assert event["tool_result_summary"] == "order_found"
    assert event["fallback_used"] is False
