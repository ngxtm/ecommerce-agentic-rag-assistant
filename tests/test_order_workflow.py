from app.backend.models import NextAction, SessionState
from app.backend.order_workflow import handle_order_workflow


def test_order_workflow_collects_missing_fields() -> None:
    response, state = handle_order_workflow("Where is my order?", SessionState())

    assert response.next_action is NextAction.ASK_USER
    assert state.verification_state.missing_fields == ["full_name", "date_of_birth", "ssn_last4"]


def test_order_workflow_rejects_invalid_dob_format() -> None:
    response, state = handle_order_workflow("My DOB is 1990-06-15", SessionState())

    assert response.next_action is NextAction.ASK_USER
    assert "date of birth in DD-MM-YYYY format" in response.answer
    assert "date_of_birth" in state.verification_state.missing_fields


def test_order_workflow_returns_shipment_result_after_verification() -> None:
    state = SessionState()

    response, state = handle_order_workflow("John Doe", state)
    assert response.next_action is NextAction.ASK_USER

    response, state = handle_order_workflow("15-06-1990", state)
    assert response.next_action is NextAction.ASK_USER

    response, state = handle_order_workflow("1234", state)
    assert response.next_action is NextAction.RESPOND
    assert "ORD-1001" in response.answer
    assert "In Transit" in response.answer
