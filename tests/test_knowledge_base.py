from unittest.mock import Mock, patch

from app.backend.knowledge_base import CONSERVATIVE_FALLBACK, answer_question, generate_grounded_answer, retrieve_relevant_chunks
from app.backend.llm_client import LLMClientError
from app.backend.search_client import RetrievedChunk


def _sample_chunk() -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="chunk-1",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1. Business",
        content="We serve consumers through our online and physical stores and focus on low prices, selection, and convenience.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=5.0,
        lexical_score=3.0,
        vector_score=2.0,
        item="Item 1. Business",
        content_type="narrative",
    )


def _table_row_chunk(score: float = 5.0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="amazon-row-1",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 6. Selected Consolidated Financial Data",
        content="Net sales for 2019: 280,522",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=score,
        item="Item 6. Selected Consolidated Financial Data",
        page_start=8,
        page_end=8,
        content_type="table_row",
        table_name="Item 6. Selected Consolidated Financial Data",
        metric="Net sales",
        year="2019",
        value_raw="280,522",
        value_normalized=280522.0,
        unit="million USD",
    )


def _table_block_chunk(score: float = 4.0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="amazon-block-1",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 6. Selected Consolidated Financial Data",
        content="Selected Consolidated Financial Data\nNet sales 280,522 232,887 177,866 135,987 107,006",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=score,
        item="Item 6. Selected Consolidated Financial Data",
        page_start=8,
        page_end=8,
        content_type="table_block",
        table_name="Item 6. Selected Consolidated Financial Data",
    )


@patch("app.backend.knowledge_base.generate_chat_completion")
def test_generate_grounded_answer_returns_llm_text(mock_generate_chat_completion: Mock) -> None:
    mock_generate_chat_completion.return_value = "Amazon focuses on low prices, selection, and convenience."

    answer = generate_grounded_answer("What does the business focus on?", [_sample_chunk()])

    assert "low prices" in answer
    assert "convenience" in answer


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
    mock_generate.return_value = "Amazon focuses on low prices, selection, and convenience."

    answer, sources = answer_question("What does the business focus on?")

    assert "low prices" in answer
    assert len(sources) == 1
    assert sources[0].title == "Amazon.com, Inc. Form 10-K - Item 1. Business"


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


@patch("app.backend.knowledge_base.search_chunks")
def test_retrieve_relevant_chunks_prefers_table_rows_for_numeric_questions(mock_search_chunks: Mock) -> None:
    mock_search_chunks.return_value = [_sample_chunk(), _table_block_chunk(), _table_row_chunk()]

    chunks = retrieve_relevant_chunks("What were net sales in 2019?")

    assert chunks[0].content_type == "table_row"
    assert chunks[0].metric == "Net sales"
    assert chunks[0].year == "2019"


@patch("app.backend.knowledge_base.search_chunks")
def test_retrieve_relevant_chunks_prefers_narrative_for_narrative_questions(mock_search_chunks: Mock) -> None:
    narrative = RetrievedChunk(
        chunk_id="chunk-2",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1A. Risk Factors",
        content="We face intense competition across lines of business.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=4.5,
        item="Item 1A. Risk Factors",
        content_type="narrative",
        subsection="We Face Intense Competition",
    )
    mock_search_chunks.return_value = [_table_row_chunk(score=4.0), _table_block_chunk(score=4.4), narrative]

    chunks = retrieve_relevant_chunks("What does the report say about competition?")

    assert chunks[0].content_type == "narrative"
    assert chunks[0].section == "Item 1A. Risk Factors"


@patch("app.backend.knowledge_base.generate_grounded_answer")
@patch("app.backend.knowledge_base.retrieve_relevant_chunks")
def test_answer_question_returns_structured_table_source(mock_retrieve: Mock, mock_generate: Mock) -> None:
    mock_retrieve.return_value = [_table_row_chunk()]
    mock_generate.return_value = "Net sales were 280,522 in 2019."

    answer, sources = answer_question("What were net sales in 2019?")

    assert "280,522" in answer
    assert len(sources) == 1
    assert sources[0].title == "Item 6. Selected Consolidated Financial Data - Net sales (2019)"
    assert sources[0].metric == "Net sales"
    assert sources[0].year == "2019"
