from unittest.mock import patch

from app.backend.memory_store import session_store
from app.backend.models import ChatRequest
from app.backend.orchestrator import handle_chat


@patch("app.backend.orchestrator.answer_question")
def test_orchestrator_routes_knowledge_questions(mock_answer_question) -> None:
    session_id = "knowledge-session"
    mock_answer_question.return_value = (
        "Most items may be returned within 30 calendar days of delivery.",
        [
            {
                "source_id": "returns-policy-overview",
                "title": "Returns Policy",
                "snippet": "Most items may be returned within 30 calendar days of delivery.",
            }
        ],
    )
    response = handle_chat(ChatRequest(session_id=session_id, message="What is the return policy?"))

    assert response.intent.value == "KNOWLEDGE_QA"
    assert response.next_action.value == "RESPOND"
    assert response.sources

    stored_state = session_store.load(session_id)
    assert stored_state.recent_messages[-1].retrieval_refs == ["returns-policy-overview"]
    assert stored_state.recent_messages[-1].contains_pii is False


def test_orchestrator_continues_order_flow_without_repeating_keywords() -> None:
    session_id = "order-session"
    first = handle_chat(ChatRequest(session_id=session_id, message="Where is my order?"))
    second = handle_chat(ChatRequest(session_id=session_id, message="John Doe"))
    third = handle_chat(ChatRequest(session_id=session_id, message="15-06-1990"))
    fourth = handle_chat(ChatRequest(session_id=session_id, message="1234"))

    assert first.intent.value == "ORDER_STATUS"
    assert second.intent.value == "ORDER_STATUS"
    assert third.intent.value == "ORDER_STATUS"
    assert fourth.intent.value == "ORDER_STATUS"
    assert "ORD-1001" in fourth.answer

    stored_state = session_store.load(session_id)
    assert stored_state.collected_fields.full_name == "John Doe"
    assert stored_state.collected_fields.date_of_birth == "1990-06-15"
    assert stored_state.collected_fields.ssn_last4 == "1234"
    assert stored_state.recent_messages[-1].tool_name == "mock_order_lookup"
    assert stored_state.recent_messages[-1].tool_result_summary == "order_found"
