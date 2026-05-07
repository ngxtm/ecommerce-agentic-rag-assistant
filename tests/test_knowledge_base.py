from unittest.mock import Mock, patch

from app.backend.knowledge_base import (
    CONSERVATIVE_FALLBACK,
    _build_sources,
    _classify_question_intent,
    answer_question,
    generate_grounded_answer,
    retrieve_relevant_chunks,
    stream_answer_question,
)
from app.backend.llm_client import LLMClientError
from app.backend.risk_headings import extract_risk_heading_reference
from app.backend.search_client import RetrievedChunk


def test_classify_question_intent_treats_conversational_risk_heading_as_heading_lookup() -> None:
    assert _classify_question_intent("Can you tell me more about We Face Intense Competition") == "heading_lookup"
    assert _classify_question_intent("Can you tell me more about Our Supplier Relationships Subject Us to a Number of Risks") == "heading_lookup"


def test_extract_risk_heading_reference_strips_conversational_wrapper() -> None:
    assert extract_risk_heading_reference("Can you tell me more about We Face Intense Competition") == "We Face Intense Competition"
    assert (
        extract_risk_heading_reference("Can you tell me more about Our Supplier Relationships Subject Us to a Number of Risks")
        == "Our Supplier Relationships Subject Us to a Number of Risks"
    )


def test_generate_grounded_answer_uses_extracted_heading_for_conversational_risk_question() -> None:
    answer = generate_grounded_answer(
        "Can you tell me more about We Face Intense Competition",
        [
            _item1a_chunk(score=5.0),
            _item1a_chunk(
                score=4.8,
                subsection="Intellectual Property Rights and Being Accused of Infringing",
                content="Our digital content offerings depend in part on effective digital rights management technology.",
            ),
        ],
    )

    assert "I do not see **We Face Intense Competition**" in answer


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


def _item2_chunk(score: float = 5.0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="item2-facilities",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 2. Properties",
        content="We operate offices, fulfillment centers, sortation centers, and data centers worldwide.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=score,
        lexical_score=score,
        vector_score=0.0,
        item="Item 2. Properties",
        subsection="Properties",
        content_type="fact",
    )


def _item7a_chunk(score: float = 5.0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="item7a-risk",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 7A. Quantitative and Qualitative Disclosures About Market Risk",
        content="We are exposed to fluctuations in interest rates and foreign currency exchange rates.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=score,
        lexical_score=score,
        vector_score=0.0,
        item="Item 7A. Quantitative and Qualitative Disclosures About Market Risk",
        subsection="Interest Rate Risk",
        subsubsection="Foreign Exchange Risk",
        content_type="narrative",
    )


def _item1a_chunk(score: float = 5.0, subsection: str | None = None, content: str | None = None) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="item1a-risk",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1A. Risk Factors",
        content=content
        or "Government Regulation Is Evolving and Unfavorable Changes Could Harm Our Business\nWe are subject to general business regulations and laws.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=score,
        lexical_score=score,
        vector_score=0.0,
        item="Item 1A. Risk Factors",
        subsection=subsection or "Government Regulation Is Evolving and Unfavorable Changes Could Harm Our Business",
        content_type="narrative",
    )


def _item8_chunk(score: float = 5.0) -> RetrievedChunk:
    return RetrievedChunk(
        chunk_id="item8-statements",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 8. Financial Statements and Supplementary Data",
        content="Consolidated Statements of Operations\n2019 2018 2017\nNet sales 280,522 232,887 177,866",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=score,
        lexical_score=score,
        vector_score=0.0,
        item="Item 8. Financial Statements and Supplementary Data",
        subsection="Consolidated Statements of Operations",
        content_type="table_block",
        table_name="Consolidated Statements of Operations",
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


@patch("app.backend.knowledge_base.generate_chat_completion")
@patch("app.backend.knowledge_base.retrieve_relevant_chunks")
def test_answer_question_returns_answer_and_sources(mock_retrieve: Mock, mock_generate_chat_completion: Mock) -> None:
    mock_retrieve.return_value = [_sample_chunk()]
    mock_generate_chat_completion.return_value = "Amazon focuses on low prices, selection, and convenience."

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


@patch("app.backend.knowledge_base.search_chunks")
def test_retrieve_relevant_chunks_prefers_item2_for_properties_query(mock_search_chunks: Mock) -> None:
    mock_search_chunks.return_value = [_sample_chunk(), _item2_chunk()]

    chunks = retrieve_relevant_chunks("What facilities did Amazon operate?")

    assert chunks[0].chunk_id == "item2-facilities"


@patch("app.backend.knowledge_base.search_chunks")
def test_retrieve_relevant_chunks_prefers_item1_for_business_focus_query(mock_search_chunks: Mock) -> None:
    item2_blob = RetrievedChunk(
        chunk_id="item2-blob",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 2. Properties",
        content="We operated offices, stores, fulfillment centers, data centers, and other facilities worldwide. " * 8,
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=5.5,
        lexical_score=5.5,
        vector_score=0.0,
        item="Item 2. Properties",
        content_type="narrative",
    )
    item1 = RetrievedChunk(
        chunk_id="item1-general",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1. Business",
        content="We seek to be Earth's most customer-centric company and serve consumers, sellers, developers, enterprises, and content creators.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=4.6,
        lexical_score=4.6,
        vector_score=0.0,
        item="Item 1. Business",
        subsection="General",
        content_type="narrative",
    )
    mock_search_chunks.return_value = [item2_blob, item1]

    chunks = retrieve_relevant_chunks("What does Amazon's business focus on?")

    assert chunks[0].chunk_id == "item1-general"


@patch("app.backend.knowledge_base.search_chunks")
def test_retrieve_relevant_chunks_prefers_item3_for_legal_query(mock_search_chunks: Mock) -> None:
    item3 = RetrievedChunk(
        chunk_id="item3-legal",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 3. Legal Proceedings",
        content="See Item 8 of Part II, Note 7, Commitments and Contingencies - Legal Proceedings.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=4.2,
        lexical_score=4.2,
        vector_score=0.0,
        item="Item 3. Legal Proceedings",
        content_type="narrative",
    )
    item2_blob = RetrievedChunk(
        chunk_id="item2-blob",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 2. Properties",
        content="We operated offices, stores, fulfillment centers, data centers, and other facilities worldwide. " * 8,
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=4.9,
        lexical_score=4.9,
        vector_score=0.0,
        item="Item 2. Properties",
        content_type="narrative",
    )
    mock_search_chunks.return_value = [item2_blob, item3]

    chunks = retrieve_relevant_chunks("Were there any legal proceedings?")

    assert chunks[0].chunk_id == "item3-legal"


@patch("app.backend.knowledge_base.search_chunks")
def test_retrieve_relevant_chunks_prefers_item5_for_stock_query(mock_search_chunks: Mock) -> None:
    item5 = RetrievedChunk(
        chunk_id="item5-stock",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 5. Market for the Registrant's Common Stock, Related Shareholder Matters, and Issuer Purchases of Equity Securities",
        content="Our common stock is traded on the Nasdaq Global Select Market under the symbol AMZN.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=4.6,
        lexical_score=4.6,
        vector_score=0.0,
        item="Item 5. Market for the Registrant's Common Stock, Related Shareholder Matters, and Issuer Purchases of Equity Securities",
        subsection="Market Information",
        content_type="fact",
    )
    noisy_risk = _item1a_chunk(score=5.0)
    mock_search_chunks.return_value = [noisy_risk, item5]

    chunks = retrieve_relevant_chunks(
        "Market for the Registrant's Common Stock, Related Shareholder Matters, and Issuer Purchases of Equity Securities"
    )

    assert chunks[0].chunk_id == "item5-stock"


@patch("app.backend.knowledge_base.search_chunks")
def test_retrieve_relevant_chunks_prefers_item7a_for_market_risk_query(mock_search_chunks: Mock) -> None:
    noisy = RetrievedChunk(
        chunk_id="noise-risk",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1A. Risk Factors",
        content="We face a number of significant risks.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=5.2,
        lexical_score=5.2,
        vector_score=0.0,
        item="Item 1A. Risk Factors",
        subsection="General Risks",
        content_type="narrative",
    )
    mock_search_chunks.return_value = [noisy, _item7a_chunk()]

    chunks = retrieve_relevant_chunks("What does Item 7A say about market risk?")

    assert chunks[0].chunk_id == "item7a-risk"


@patch("app.backend.knowledge_base.search_chunks")
def test_retrieve_relevant_chunks_prefers_item1a_for_explicit_risk_factor_query(mock_search_chunks: Mock) -> None:
    mock_search_chunks.return_value = [
        _sample_chunk(),
        _item1a_chunk(score=5.1),
        _item1a_chunk(
            score=4.9,
            subsection="Intellectual Property Rights and Being Accused of Infringing",
            content="Our digital content offerings depend in part on effective digital rights management technology.",
        ),
    ]

    chunks = retrieve_relevant_chunks(
        "Summarize the risk factors described in Item 1A of Amazon's filing in a structured way, focusing on the major themes and how they could affect the business."
    )

    assert chunks
    assert all(chunk.item == "Item 1A. Risk Factors" for chunk in chunks)
    assert chunks[0].section == "Item 1A. Risk Factors"


@patch("app.backend.knowledge_base.search_chunks")
def test_retrieve_relevant_chunks_prefers_item1a_for_risks_related_heading_queries(mock_search_chunks: Mock) -> None:
    exact_heading = _item1a_chunk(
        score=5.1,
        subsection="Risks Related to Successfully Optimizing and Operating Our Fulfillment Network and Data Centers",
        content="If we do not optimize and operate our fulfillment network and data centers efficiently, our cost structure, service levels, and growth could be adversely affected.",
    )
    noise = _item2_chunk(score=5.6)
    mock_search_chunks.return_value = [noise, exact_heading]

    chunks = retrieve_relevant_chunks("Risks Related to Successfully Optimizing and Operating Our Fulfillment Network and Data Centers")

    assert chunks
    assert chunks[0].item == "Item 1A. Risk Factors"
    assert chunks[0].subsection == "Risks Related to Successfully Optimizing and Operating Our Fulfillment Network and Data Centers"


@patch("app.backend.knowledge_base.search_chunks")
def test_retrieve_relevant_chunks_prefers_item1a_for_generalized_risk_summary_queries(mock_search_chunks: Mock) -> None:
    mock_search_chunks.return_value = [
        _sample_chunk(),
        _item1a_chunk(score=5.1),
        _item1a_chunk(
            score=4.8,
            subsection="Risks Related to Competition and Execution",
            content="Competition, pricing pressure, and execution challenges could adversely affect operating results.",
        ),
    ]

    for question in (
        "Summarize the risk factors described in Item 1A of Amazon's filing.",
        "Provide a structured overview of the major risk factors in Item 1A and how they could affect the business.",
        "Explain the major themes in Item 1A Risk Factors and their business impact.",
    ):
        chunks = retrieve_relevant_chunks(question)

        assert chunks
        assert all(chunk.item == "Item 1A. Risk Factors" for chunk in chunks)
        assert chunks[0].section == "Item 1A. Risk Factors"


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


def test_build_sources_uses_subsubsection_for_narrative_titles() -> None:
    sources = _build_sources([_item7a_chunk()])

    assert sources[0].title == (
        "Amazon.com, Inc. Form 10-K - Item 7A. Quantitative and Qualitative Disclosures About Market Risk "
        "- Interest Rate Risk - Foreign Exchange Risk"
    )


def test_build_sources_formats_item8_table_block_with_specific_statement_title() -> None:
    sources = _build_sources([_item8_chunk()])

    assert sources[0].title == (
        "Amazon.com, Inc. Form 10-K - Item 8. Financial Statements and Supplementary Data - Consolidated Statements of Operations"
    )


def test_build_sources_trims_duplicate_narrative_from_same_subsection() -> None:
    first = RetrievedChunk(
        chunk_id="item2-narrative-1",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 2. Properties",
        content="As of December 31, 2019, we operated office space and data centers worldwide.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=5.0,
        lexical_score=5.0,
        vector_score=0.0,
        item="Item 2. Properties",
        content_type="narrative",
    )
    duplicate = RetrievedChunk(**{**first.__dict__, "chunk_id": "item2-narrative-2", "score": 4.8, "lexical_score": 4.8})

    sources = _build_sources([first, duplicate])

    assert len(sources) == 1
    assert sources[0].source_id == "item2-narrative-1"


def test_generate_grounded_answer_is_conservative_for_legal_cross_reference_only() -> None:
    legal_xref = RetrievedChunk(
        chunk_id="item3-xref",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 3. Legal Proceedings",
        content="See Item 8 of Part II, Financial Statements and Supplementary Data - Note 7 - Commitments and Contingencies - Legal Proceedings.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=4.2,
        lexical_score=4.2,
        vector_score=0.0,
        item="Item 3. Legal Proceedings",
        content_type="narrative",
    )

    answer = generate_grounded_answer("Were there any legal proceedings?", [legal_xref])

    assert "available context indicates there were legal proceedings" in answer.casefold()
    assert "cross-reference" in answer.casefold()
    assert "does not include enough grounded detail" in answer.casefold()


def test_build_sources_for_heading_lookup_keeps_only_best_matching_risk_heading() -> None:
    best_match = RetrievedChunk(
        chunk_id="risk-best",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1A. Risk Factors",
        content=(
            "The Loss of Key Senior Management Personnel or the Failure to Hire and Retain Highly Skilled and Other Key Personnel "
            "Could Negatively Affect Our Business\nWe depend on our senior management and other key personnel."
        ),
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=5.0,
        lexical_score=5.0,
        vector_score=0.0,
        item="Item 1A. Risk Factors",
        subsection="The Loss of Key Senior Management Personnel or the Failure to Hire and Retain Highly Skilled and Other Key Personnel Could Negatively Affect Our Business",
        content_type="narrative",
    )
    noisy_match = RetrievedChunk(
        chunk_id="risk-noise",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1A. Risk Factors",
        content="Our digital content offerings depend on effective digital rights management technology.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=4.7,
        lexical_score=4.7,
        vector_score=0.0,
        item="Item 1A. Risk Factors",
        subsection="Intellectual Property Rights and Being Accused of Infringing",
        content_type="narrative",
    )

    sources = _build_sources(
        [best_match, noisy_match],
        active_question="The Loss of Key Senior Management Personnel or the Inability to Hire and Retain Qualified Personnel Could Harm Our Business",
    )

    assert len(sources) == 1
    assert sources[0].source_id == "risk-best"


@patch("app.backend.knowledge_base.retrieve_relevant_chunks")
def test_stream_answer_question_returns_deterministic_stream_and_sources_for_numeric_lookup(mock_retrieve: Mock) -> None:
    mock_retrieve.return_value = [_table_row_chunk()]

    answer_stream, sources = stream_answer_question("What were net sales in 2019?")

    assert "".join(answer_stream) == "Net sales in 2019 were **280,522 million USD**."
    assert sources[0].metric == "Net sales"


@patch("app.backend.knowledge_base.retrieve_relevant_chunks")
def test_stream_answer_question_returns_fallback_when_no_chunks(mock_retrieve: Mock) -> None:
    mock_retrieve.return_value = []

    answer_stream, sources = stream_answer_question("Question without support")

    assert "".join(answer_stream) == CONSERVATIVE_FALLBACK
    assert sources == []


@patch("app.backend.knowledge_base.generate_grounded_answer_stream")
@patch("app.backend.knowledge_base.retrieve_relevant_chunks")
def test_stream_answer_question_uses_llm_stream_when_generation_is_needed(mock_retrieve: Mock, mock_stream: Mock) -> None:
    mock_retrieve.return_value = [_sample_chunk()]
    mock_stream.return_value = iter(["Amazon focuses ", "on low prices."])

    answer_stream, sources = stream_answer_question("What does the business focus on?")

    assert "".join(answer_stream) == "Amazon focuses on low prices."
    assert len(sources) == 1
    mock_stream.assert_called_once()


@patch("app.backend.knowledge_base.generate_chat_completion")
def test_generate_grounded_answer_returns_fallback_when_generation_returns_empty(mock_generate_chat_completion: Mock) -> None:
    mock_generate_chat_completion.return_value = ""

    answer = generate_grounded_answer("When is tracking available?", [_sample_chunk()])

    assert answer == CONSERVATIVE_FALLBACK


@patch("app.backend.knowledge_base.generate_chat_completion")
def test_generate_grounded_answer_synthesizes_summary_when_narrative_chunks_are_supported(mock_generate_chat_completion: Mock) -> None:
    mock_generate_chat_completion.return_value = CONSERVATIVE_FALLBACK

    answer = generate_grounded_answer(
        "Summarize the risk factors described in Item 1A of Amazon's filing in a structured way.",
        [
            _item1a_chunk(score=5.0),
            _item1a_chunk(
                score=4.8,
                subsection="Intellectual Property Rights and Being Accused of Infringing",
                content="Our digital content offerings depend in part on effective digital rights management technology.",
            ),
        ],
    )

    assert "supported themes" in answer
    assert "Government Regulation Is Evolving" in answer
    assert "Intellectual Property Rights and Being Accused of Infringing" in answer
    mock_generate_chat_completion.assert_called_once()


@patch("app.backend.knowledge_base.generate_chat_completion")
def test_generate_grounded_answer_marks_item1a_summary_as_limited_when_excerpt_is_narrow(mock_generate_chat_completion: Mock) -> None:
    mock_generate_chat_completion.return_value = "A narrow Item 1A summary"

    answer = generate_grounded_answer(
        "Summarize the risk factors described in Item 1A of Amazon's filing in a structured way.",
        [_item1a_chunk(score=5.0)],
    )

    assert "limited Item 1A excerpt" in answer


@patch("app.backend.knowledge_base.generate_chat_completion")
def test_generate_grounded_answer_rejects_missing_specific_item1a_heading(mock_generate_chat_completion: Mock) -> None:
    mock_generate_chat_completion.return_value = CONSERVATIVE_FALLBACK
    answer = generate_grounded_answer(
        "Risks Related to Successfully Optimizing and Operating Our Fulfillment Network and Data Centers",
        [
            _item1a_chunk(score=5.0),
            _item1a_chunk(
                score=4.8,
                subsection="Intellectual Property Rights and Being Accused of Infringing",
                content="Our digital content offerings depend in part on effective digital rights management technology.",
            ),
        ],
    )

    assert "do not see" in answer.casefold()
    assert "18-page filing extract" in answer


def test_build_sources_omits_misleading_sources_for_missing_item1a_heading() -> None:
    sources = _build_sources(
        [
            _item1a_chunk(score=5.0),
            _item1a_chunk(
                score=4.8,
                subsection="Intellectual Property Rights and Being Accused of Infringing",
                content="Our digital content offerings depend in part on effective digital rights management technology.",
            ),
        ],
        active_question="Risks Related to Successfully Optimizing and Operating Our Fulfillment Network and Data Centers",
    )

    assert sources == []


@patch("app.backend.knowledge_base.retrieve_relevant_chunks")
def test_stream_answer_question_returns_same_missing_heading_fallback_as_blocking_path(mock_retrieve: Mock) -> None:
    mock_retrieve.return_value = [
        _item1a_chunk(score=5.0),
        _item1a_chunk(
            score=4.8,
            subsection="Intellectual Property Rights and Being Accused of Infringing",
            content="Our digital content offerings depend in part on effective digital rights management technology.",
        ),
    ]

    answer_stream, sources = stream_answer_question("Can you tell me more about We Face Intense Competition")

    answer = "".join(answer_stream)
    assert "I do not see **We Face Intense Competition**" in answer
    assert sources == []


@patch("app.backend.knowledge_base.retrieve_relevant_chunks")
def test_answer_question_returns_fallback_when_runtime_fails(mock_retrieve: Mock) -> None:
    mock_retrieve.side_effect = LLMClientError("Denied")

    answer, sources = answer_question("When is tracking available?")

    assert answer == CONSERVATIVE_FALLBACK
    assert sources == []
