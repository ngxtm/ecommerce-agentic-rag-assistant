from unittest.mock import Mock, patch

from app.backend.knowledge_base import _rerank_chunks
from app.backend.search_client import (
    RetrievedChunk,
    _build_lexical_query,
    _classify_query_intent,
    _merge_candidates,
    _search_with_query_variants,
    rewrite_search_query,
    search_chunks,
)


@patch("app.backend.search_client._build_client")
@patch("app.backend.search_client.os.getenv")
def test_search_chunks_returns_normalized_hits_with_extended_metadata(mock_getenv: Mock, mock_build_client: Mock) -> None:
    mock_getenv.return_value = "policy-faq-chunks"
    mock_client = Mock()
    mock_client.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_id": "chunk-1",
                    "_score": 4.2,
                    "_source": {
                        "chunk_id": "chunk-1",
                        "doc_id": "amazon_10k_2019",
                        "title": "Amazon.com, Inc. Form 10-K",
                        "section": "Executive Officers and Directors",
                        "content": "Andrew R. Jassy, age 52, serves as CEO Amazon Web Services.",
                        "source_path": "Company-10k-18pages.pdf",
                        "source_uri": "docs/company/Company-10k-18pages.pdf",
                        "content_type": "profile_row",
                        "entity_name": "Andrew R. Jassy",
                        "entity_role": "CEO Amazon Web Services",
                        "embedding": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
                    },
                }
            ]
        }
    }
    mock_build_client.return_value = mock_client

    chunks = search_chunks("Who is Andrew R. Jassy?")

    assert len(chunks) == 1
    assert chunks[0].content_type == "profile_row"
    assert chunks[0].entity_name == "Andrew R. Jassy"
    assert chunks[0].entity_role == "CEO Amazon Web Services"


def test_classify_query_intent_handles_numeric_entity_and_heading_queries() -> None:
    assert _classify_query_intent("What were net sales in 2019?") == "numeric_table"
    assert _classify_query_intent("Who are the executive officers and directors?") == "entity_lookup"
    assert _classify_query_intent("The Loss of Key Senior Management Personnel Could Harm Our Business") == "heading_lookup"
    assert _classify_query_intent("Risks Related to Successfully Optimizing and Operating Our Fulfillment Network and Data Centers") == "heading_lookup"
    assert _classify_query_intent("Summarize the risk factors described in Item 1A of Amazon's filing.") == "narrative_explainer"
    assert _classify_query_intent("What facilities did Amazon operate?") == "narrative_explainer"
    assert _classify_query_intent("Market for the Registrant's Common Stock, Related Shareholder Matters, and Issuer Purchases of Equity Securities") == "narrative_explainer"


def test_build_lexical_query_boosts_entity_fields_for_entity_lookup() -> None:
    query = _build_lexical_query("Who is Andrew R. Jassy?", top_k=4)
    best_fields = query["query"]["bool"]["should"][0]["multi_match"]["fields"]

    assert "entity_name^14" in best_fields


def test_build_lexical_query_boosts_subsection_for_heading_lookup() -> None:
    query = _build_lexical_query("The Loss of Key Senior Management Personnel Could Harm Our Business", top_k=4)
    phrase_fields = query["query"]["bool"]["should"][1]["multi_match"]["fields"]

    assert "subsection^16" in phrase_fields or "subsection^12" in phrase_fields


def test_build_lexical_query_routes_explicit_item1a_summary_to_heading_lookup() -> None:
    query = _build_lexical_query("Summarize the risk factors described in Item 1A of Amazon's filing.", top_k=4)
    should_clauses = query["query"]["bool"]["should"]

    assert any(clause.get("term", {}).get("item.keyword", {}).get("value") == "Item 1A. Risk Factors" for clause in should_clauses)


@patch("app.backend.search_client.generate_chat_completion")
def test_rewrite_search_query_returns_short_keyword_query(mock_generate_chat_completion: Mock) -> None:
    mock_generate_chat_completion.return_value = "Item 1A Risk Factors fulfillment network data centers operational risk"

    rewritten = rewrite_search_query("Risks Related to Successfully Optimizing and Operating Our Fulfillment Network and Data Centers")

    assert rewritten == "Item 1A Risk Factors fulfillment network data centers operational risk"


@patch("app.backend.search_client.rewrite_search_query")
@patch("app.backend.search_client._run_vector_search")
@patch("app.backend.search_client._run_lexical_search")
def test_search_with_query_variants_retries_when_heading_match_is_weak(mock_run_lexical_search: Mock, mock_run_vector_search: Mock, mock_rewrite: Mock) -> None:
    weak_item1a = RetrievedChunk(
        chunk_id="risk-weak",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1A. Risk Factors",
        content="Generic risk language.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=1.5,
        lexical_score=1.5,
        vector_score=0.0,
        item="Item 1A. Risk Factors",
        subsection="Intellectual Property Rights and Being Accused of Infringing",
        content_type="narrative",
    )
    exact_heading = RetrievedChunk(
        chunk_id="risk-exact",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1A. Risk Factors",
        content="If we do not optimize and operate our fulfillment network and data centers efficiently, our business could be adversely affected.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=5.0,
        lexical_score=5.0,
        vector_score=0.0,
        item="Item 1A. Risk Factors",
        subsection="Risks Related to Successfully Optimizing and Operating Our Fulfillment Network and Data Centers",
        content_type="narrative",
    )
    mock_run_lexical_search.side_effect = [[weak_item1a], [exact_heading]]
    mock_run_vector_search.side_effect = [[], []]
    mock_rewrite.return_value = "Item 1A Risk Factors fulfillment network data centers operating risk"

    merged = _search_with_query_variants(Mock(), "policy-faq-chunks", "Risks Related to Successfully Optimizing and Operating Our Fulfillment Network and Data Centers", 4)

    assert merged[0].chunk_id == "risk-exact"
    mock_rewrite.assert_called_once()


@patch("app.backend.search_client.rewrite_search_query")
@patch("app.backend.search_client._run_vector_search")
@patch("app.backend.search_client._run_lexical_search")
def test_search_with_query_variants_skips_rewrite_when_first_pass_is_strong(mock_run_lexical_search: Mock, mock_run_vector_search: Mock, mock_rewrite: Mock) -> None:
    exact_heading = RetrievedChunk(
        chunk_id="risk-exact",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1A. Risk Factors",
        content="If we do not optimize and operate our fulfillment network and data centers efficiently, our business could be adversely affected.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=5.0,
        lexical_score=5.0,
        vector_score=0.0,
        item="Item 1A. Risk Factors",
        subsection="Risks Related to Successfully Optimizing and Operating Our Fulfillment Network and Data Centers",
        content_type="narrative",
    )
    mock_run_lexical_search.return_value = [exact_heading]
    mock_run_vector_search.return_value = []
    mock_rewrite.return_value = "unused rewrite"

    merged = _search_with_query_variants(Mock(), "policy-faq-chunks", "Risks Related to Successfully Optimizing and Operating Our Fulfillment Network and Data Centers", 4)

    assert merged[0].chunk_id == "risk-exact"
    mock_rewrite.assert_not_called()


def test_build_lexical_query_includes_subsubsection_for_narrative_queries() -> None:
    query = _build_lexical_query("What market risks does Amazon discuss?", top_k=4)
    best_fields = query["query"]["bool"]["should"][0]["multi_match"]["fields"]

    assert any(field.startswith("subsubsection^") for field in best_fields)


def test_build_lexical_query_adds_item1_boost_for_business_query() -> None:
    query = _build_lexical_query("What does Amazon's business focus on?", top_k=4)
    should_clauses = query["query"]["bool"]["should"]

    assert any(clause.get("term", {}).get("item.keyword", {}).get("value") == "Item 1. Business" for clause in should_clauses)


def test_build_lexical_query_adds_item5_boost_for_stock_query() -> None:
    query = _build_lexical_query(
        "Market for the Registrant's Common Stock, Related Shareholder Matters, and Issuer Purchases of Equity Securities",
        top_k=4,
    )
    should_clauses = query["query"]["bool"]["should"]

    assert any(
        clause.get("term", {}).get("item.keyword", {}).get("value")
        == "Item 5. Market for the Registrant's Common Stock, Related Shareholder Matters, and Issuer Purchases of Equity Securities"
        for clause in should_clauses
    )


def test_merge_candidates_keeps_exact_lexical_match_above_semantic_neighbor() -> None:
    exact_match = RetrievedChunk(
        chunk_id="exact-net-sales-2019",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 6. Selected Consolidated Financial Data",
        content="Net sales for 2019: 280,522",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=9.0,
        lexical_score=9.0,
        vector_score=0.2,
        content_type="table_row",
        metric="Net sales",
        year="2019",
    )
    semantic_neighbor = RetrievedChunk(
        chunk_id="semantic-sales-growth",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 7. Management Discussion and Analysis",
        content="Revenue continued to grow significantly in 2019.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=0.8,
        lexical_score=1.5,
        vector_score=0.9,
        content_type="narrative",
    )

    merged = _merge_candidates([exact_match], [semantic_neighbor], top_k=2)

    assert merged[0].chunk_id == "exact-net-sales-2019"


def test_rerank_chunks_prioritizes_profile_rows_for_entity_queries() -> None:
    profile_row = RetrievedChunk(
        chunk_id="exec-row",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Executive Officers and Directors",
        content="Andrew R. Jassy, age 52, serves as CEO Amazon Web Services.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=2.0,
        lexical_score=2.0,
        vector_score=0.0,
        subsection="Information About Our Executive Officers",
        content_type="profile_row",
        entity_name="Andrew R. Jassy",
        entity_role="CEO Amazon Web Services",
    )
    noisy_chunk = RetrievedChunk(
        chunk_id="risk-factor",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1A. Risk Factors",
        content="Please carefully consider the following discussion of significant factors.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=2.5,
        lexical_score=2.5,
        vector_score=0.0,
        content_type="narrative",
    )

    ranked = _rerank_chunks("Who is Andrew R. Jassy?", [noisy_chunk, profile_row])

    assert ranked[0].chunk_id == "exec-row"


def test_rerank_chunks_prioritizes_exact_risk_subsection_match() -> None:
    exact_heading = RetrievedChunk(
        chunk_id="risk-heading",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1A. Risk Factors",
        content="The Loss of Key Senior Management Personnel or the Inability to Hire and Retain Qualified Personnel Could Harm Our Business\nOur future success depends on our senior management.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=2.0,
        lexical_score=2.0,
        vector_score=0.0,
        content_type="narrative",
        subsection="The Loss of Key Senior Management Personnel or the Inability to Hire and Retain Qualified Personnel Could Harm Our Business",
    )
    general_risk = RetrievedChunk(
        chunk_id="risk-general",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1A. Risk Factors",
        content="We face a number of risks.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=2.1,
        lexical_score=2.1,
        vector_score=0.0,
        content_type="narrative",
    )

    ranked = _rerank_chunks(
        "The Loss of Key Senior Management Personnel or the Inability to Hire and Retain Qualified Personnel Could Harm Our Business",
        [general_risk, exact_heading],
    )

    assert ranked[0].chunk_id == "risk-heading"


def test_rerank_chunks_penalizes_generic_harm_heading_without_specific_overlap() -> None:
    specific_heading = RetrievedChunk(
        chunk_id="risk-specific",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1A. Risk Factors",
        content="We depend on our senior management and other key personnel.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=1.0,
        lexical_score=1.0,
        vector_score=0.0,
        content_type="narrative",
        subsection="The Loss of Key Senior Management Personnel or the Failure to Hire and Retain Highly Skilled and Other Key Personnel Could Negatively Affect Our Business",
    )
    generic_heading = RetrievedChunk(
        chunk_id="risk-generic",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1A. Risk Factors",
        content="We are subject to general business regulations and laws.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=2.0,
        lexical_score=2.0,
        vector_score=0.0,
        content_type="narrative",
        subsection="Government Regulation Is Evolving and Unfavorable Changes Could Harm Our Business",
    )

    ranked = _rerank_chunks(
        "The Loss of Key Senior Management Personnel or the Inability to Hire and Retain Qualified Personnel Could Harm Our Business",
        [generic_heading, specific_heading],
    )

    assert ranked[0].chunk_id == "risk-specific"


def test_rerank_chunks_prioritizes_item2_for_facilities_query() -> None:
    item2 = RetrievedChunk(
        chunk_id="item2-facilities",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 2. Properties",
        content="We operate offices, fulfillment centers, and data centers worldwide.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=2.0,
        lexical_score=2.0,
        vector_score=0.0,
        item="Item 2. Properties",
        subsection="Properties",
        content_type="fact",
    )
    item1 = RetrievedChunk(
        chunk_id="item1-noise",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1. Business",
        content="We serve consumers through our online and physical stores.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=2.4,
        lexical_score=2.4,
        vector_score=0.0,
        item="Item 1. Business",
        subsection="Overview",
        content_type="narrative",
    )

    ranked = _rerank_chunks("What facilities did Amazon operate?", [item1, item2])

    assert ranked[0].chunk_id == "item2-facilities"


def test_rerank_chunks_prioritizes_item7a_for_market_risk_query() -> None:
    item7a = RetrievedChunk(
        chunk_id="item7a-risk",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 7A. Quantitative and Qualitative Disclosures About Market Risk",
        content="We are exposed to fluctuations in foreign currency exchange rates and interest rates.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=2.0,
        lexical_score=2.0,
        vector_score=0.0,
        item="Item 7A. Quantitative and Qualitative Disclosures About Market Risk",
        subsection="Foreign Exchange Risk",
        content_type="narrative",
    )
    item1a = RetrievedChunk(
        chunk_id="item1a-risk",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 1A. Risk Factors",
        content="We face many risks in our business.",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=2.5,
        lexical_score=2.5,
        vector_score=0.0,
        item="Item 1A. Risk Factors",
        subsection="General Risks",
        content_type="narrative",
    )

    ranked = _rerank_chunks("What market risks does Amazon discuss?", [item1a, item7a])

    assert ranked[0].chunk_id == "item7a-risk"
