from unittest.mock import Mock, patch

from app.backend.knowledge_base import CONSERVATIVE_FALLBACK, answer_question, generate_grounded_answer
from app.backend.llm_client import LLMClientError
from app.backend.search_client import RetrievedChunk


def _sample_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="chunk-1",
        doc_id="shipping_policy",
        title="Shipping Policy",
        section="Tracking Information",
        content="Tracking information is usually available within 24 hours after shipment.",
        source_path="shipping_policy.md",
        source_uri="s3://agentic-embedding-us/phase1-kb/shipping_policy.md",
        score=5.0,
    )


@patch("app.backend.knowledge_base.generate_chat_completion")
def test_generate_grounded_answer_returns_llm_text(mock_generate_chat_completion: Mock) -> None:
    mock_generate_chat_completion.return_value = "Tracking is usually available within 24 hours after shipment."

    answer = generate_grounded_answer("When is tracking available?", [_sample_chunk()])

    assert "24 hours" in answer


@patch("app.backend.knowledge_base.retrieve_relevant_chunks")
def test_answer_question_returns_fallback_when_no_chunks(mock_retrieve: Mock) -> None:
    mock_retrieve.return_value = []

    answer, sources = answer_question("Question without support")

    assert answer == CONSERVATIVE_FALLBACK
    assert sources == []


@patch("app.backend.knowledge_base.generate_grounded_answer")
@patch("app.backend.knowledge_base.retrieve_relevant_chunks")
def test_answer_question_returns_answer_and_sources(mock_retrieve: Mock, mock_generate: Mock) -> None:
    mock_retrieve.return_value = [_sample_chunk()]
    mock_generate.return_value = "Tracking is usually available within 24 hours after shipment."

    answer, sources = answer_question("When is tracking available?")

    assert "24 hours" in answer
    assert len(sources) == 1
    assert sources[0].title == "Shipping Policy - Tracking Information"


@patch("app.backend.knowledge_base.retrieve_relevant_chunks")
def test_answer_question_returns_fallback_when_runtime_fails(mock_retrieve: Mock) -> None:
    mock_retrieve.side_effect = LLMClientError("Denied")

    answer, sources = answer_question("When is tracking available?")

    assert answer == CONSERVATIVE_FALLBACK
    assert sources == []


@patch("app.backend.knowledge_base.generate_chat_completion")
def test_answer_question_returns_fallback_when_generation_returns_empty(mock_generate_chat_completion: Mock) -> None:
    mock_generate_chat_completion.return_value = ""

    answer = generate_grounded_answer("When is tracking available?", [_sample_chunk()])

    assert answer == CONSERVATIVE_FALLBACK
