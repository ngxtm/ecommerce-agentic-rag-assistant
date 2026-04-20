from unittest.mock import Mock, patch

from app.backend.knowledge_base import (
    CONSERVATIVE_FALLBACK,
    _build_sources,
    answer_question,
    generate_grounded_answer,
    retrieve_relevant_chunks,
    stream_answer_question,
)
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


def _profile_row_chunk(score: float = 5.0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="exec-row-1",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Executive Officers and Directors",
        content="Andrew R. Jassy, age 52, serves as CEO Amazon Web Services.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=score,
        subsection="Information About Our Executive Officers",
        content_type="profile_row",
        entity_name="Andrew R. Jassy",
        entity_role="CEO Amazon Web Services",
    )


def _profile_bio_chunk(score: float = 4.0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="exec-bio-1",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Executive Officers and Directors",
        content="Andrew R. Jassy. Mr. Jassy has served as CEO Amazon Web Services since April 2016.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=score,
        subsection="Executive Officer Biographies",
        content_type="profile_bio",
        entity_name="Andrew R. Jassy",
    )


@patch("app.backend.knowledge_base.generate_chat_completion")
def test_generate_grounded_answer_returns_llm_text(mock_generate_chat_completion: Mock) -> None:
    mock_generate_chat_completion.return_value = "Amazon focuses on low prices, selection, and convenience."

    answer = generate_grounded_answer("What does the business focus on?", [_sample_chunk()])

    assert "low prices" in answer


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


@patch("app.backend.knowledge_base.search_chunks")
def test_retrieve_relevant_chunks_prefers_table_rows_for_numeric_questions(mock_search_chunks: Mock) -> None:
    mock_search_chunks.return_value = [_sample_chunk(), _table_row_chunk()]

    chunks = retrieve_relevant_chunks("What were net sales in 2019?")

    assert chunks[0].content_type == "table_row"


@patch("app.backend.knowledge_base.search_chunks")
def test_retrieve_relevant_chunks_prefers_profile_rows_for_entity_questions(mock_search_chunks: Mock) -> None:
    noisy = RetrievedChunk(
        chunk_id="noise-1",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1A. Risk Factors",
        content="Please carefully consider the following discussion of significant factors.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=4.8,
        lexical_score=4.8,
        vector_score=0.0,
        content_type="narrative",
    )
    mock_search_chunks.return_value = [noisy, _profile_bio_chunk(), _profile_row_chunk()]

    chunks = retrieve_relevant_chunks("Who is Andrew R. Jassy?")

    assert chunks[0].content_type == "profile_row"
    assert chunks[1].content_type == "profile_bio"


@patch("app.backend.knowledge_base.search_chunks")
def test_retrieve_relevant_chunks_prefers_item7_narrative_for_explainer_questions(mock_search_chunks: Mock) -> None:
    item7 = RetrievedChunk(
        chunk_id="item7-1",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations",
        content="Net sales increased primarily due to higher unit sales.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=4.0,
        lexical_score=4.0,
        vector_score=0.0,
        item="Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations",
        subsection="Results of Operations",
        content_type="narrative",
    )
    mock_search_chunks.return_value = [_table_row_chunk(score=4.5), item7]

    chunks = retrieve_relevant_chunks("Explain the results of operations")

    assert chunks[0].chunk_id == "item7-1"


def test_build_sources_deduplicates_by_semantic_key_for_profile_rows() -> None:
    first = _profile_row_chunk()
    duplicate = RetrievedChunk(**{**first.__dict__, "chunk_id": "exec-row-2", "score": 4.5})

    sources = _build_sources([first, duplicate])

    assert len(sources) == 1
    assert sources[0].title == "Executive Officers and Directors - Andrew R. Jassy"
    assert sources[0].entity_name == "Andrew R. Jassy"


def test_build_sources_formats_profile_bio_title() -> None:
    sources = _build_sources([_profile_bio_chunk()])

    assert sources[0].title == "Executive Officers and Directors - Andrew R. Jassy - Biography"
    assert sources[0].content_type == "profile_bio"


def test_build_sources_formats_table_row_title() -> None:
    sources = _build_sources([_table_row_chunk()])

    assert sources[0].title == "Item 6. Selected Consolidated Financial Data - Net sales (2019)"


@patch("app.backend.knowledge_base.generate_grounded_answer_stream")
@patch("app.backend.knowledge_base.retrieve_relevant_chunks")
def test_stream_answer_question_returns_stream_and_sources(mock_retrieve: Mock, mock_stream: Mock) -> None:
    mock_retrieve.return_value = [_table_row_chunk()]
    mock_stream.return_value = iter(["Net sales ", "were 280,522 in 2019."])

    answer_stream, sources = stream_answer_question("What were net sales in 2019?")

    assert "".join(answer_stream) == "Net sales were 280,522 in 2019."
    assert sources[0].metric == "Net sales"


@patch("app.backend.knowledge_base.retrieve_relevant_chunks")
def test_stream_answer_question_returns_fallback_when_no_chunks(mock_retrieve: Mock) -> None:
    mock_retrieve.return_value = []

    answer_stream, sources = stream_answer_question("Question without support")

    assert "".join(answer_stream) == CONSERVATIVE_FALLBACK
    assert sources == []


@patch("app.backend.knowledge_base.generate_chat_completion")
def test_generate_grounded_answer_returns_fallback_when_generation_returns_empty(mock_generate_chat_completion: Mock) -> None:
    mock_generate_chat_completion.return_value = ""

    answer = generate_grounded_answer("When is tracking available?", [_sample_chunk()])

    assert answer == CONSERVATIVE_FALLBACK


@patch("app.backend.knowledge_base.retrieve_relevant_chunks")
def test_answer_question_returns_fallback_when_runtime_fails(mock_retrieve: Mock) -> None:
    mock_retrieve.side_effect = LLMClientError("Denied")

    answer, sources = answer_question("When is tracking available?")

    assert answer == CONSERVATIVE_FALLBACK
    assert sources == []
