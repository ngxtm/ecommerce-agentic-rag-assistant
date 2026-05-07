from unittest.mock import Mock, patch

from app.backend.knowledge_index_schema import INDEX_SCHEMA_VERSION
from app.backend.knowledge_base import _rerank_chunks
from app.backend.llm_client import LLMClientError
from app.backend.search_client import (
    RetrievedChunk,
    _build_lexical_query,
    _build_vector_query,
    _classify_query_intent,
    _get_retrieval_profile,
    _merge_candidates,
    _run_vector_search,
    _search_with_query_variants,
    _should_run_vector_search,
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
    assert _classify_query_intent("Risk factor") == "section_overview"
    assert _classify_query_intent("Risk Factors") == "section_overview"
    assert _classify_query_intent("Item 1A Risk Factor") == "section_overview"
    assert _classify_query_intent("Item 1A Risk Factors") == "section_overview"
    assert _classify_query_intent('Can you tell me more about: "Risk factor"') == "section_overview"
    assert _classify_query_intent('Can you tell me more about: "Risk Factors"') == "section_overview"
    assert _classify_query_intent("The Loss of Key Senior Management Personnel Could Harm Our Business") == "heading_lookup"
    assert _classify_query_intent("Risks Related to Successfully Optimizing and Operating Our Fulfillment Network and Data Centers") == "heading_lookup"
    assert _classify_query_intent("Can you tell me more about We Face Intense Competition") == "heading_lookup"
    assert _classify_query_intent("Can you tell me more about Our Supplier Relationships Subject Us to a Number of Risks") == "heading_lookup"
    assert _classify_query_intent("Summarize the risk factors described in Item 1A of Amazon's filing.") == "narrative_explainer"
    assert _classify_query_intent("What facilities did Amazon operate?") == "narrative_explainer"
    assert _classify_query_intent("Market for the Registrant's Common Stock, Related Shareholder Matters, and Issuer Purchases of Equity Securities") == "section_overview"


def test_build_lexical_query_boosts_entity_fields_for_entity_lookup() -> None:
    query = _build_lexical_query("Who is Andrew R. Jassy?", top_k=4)
    best_fields = query["query"]["bool"]["should"][0]["multi_match"]["fields"]

    assert "entity_name^14" in best_fields


def test_build_lexical_query_boosts_subsection_for_heading_lookup() -> None:
    query = _build_lexical_query("The Loss of Key Senior Management Personnel Could Harm Our Business", top_k=4)
    phrase_fields = query["query"]["bool"]["should"][1]["multi_match"]["fields"]

    assert "subsection^16" in phrase_fields or "subsection^12" in phrase_fields


def test_build_lexical_query_strips_conversational_wrapper_for_heading_lookup() -> None:
    query = _build_lexical_query("Can you tell me more about We Face Intense Competition", top_k=4)
    expanded = query["query"]["bool"]["should"][0]["multi_match"]["query"]

    assert expanded.startswith("We Face Intense Competition Item 1A Risk Factors")


def test_build_lexical_query_adds_exact_heading_boost_for_conversational_heading_lookup() -> None:
    query = _build_lexical_query("Can you tell me more about We Face Intense Competition", top_k=4)
    should_clauses = query["query"]["bool"]["should"]

    assert {"term": {"subsection.keyword": {"value": "We Face Intense Competition", "boost": 60}}} in should_clauses

def test_build_lexical_query_routes_generic_risk_factors_to_section_overview() -> None:
    for question in (
        'Can you tell me more about: "Risk factor"',
        'Can you tell me more about: "Risk Factors"',
    ):
        query = _build_lexical_query(question, top_k=4)
        best_fields = query["query"]["bool"]["should"][0]["multi_match"]["fields"]
        should_clauses = query["query"]["bool"]["should"]

        assert "item^14" in best_fields
        assert any(clause.get("term", {}).get("item.keyword", {}).get("value") == "Item 1A. Risk Factors" for clause in should_clauses)
        assert not any("subsection.keyword" in clause.get("term", {}) for clause in should_clauses)

def test_build_lexical_query_routes_generic_properties_title_to_item2() -> None:
    query = _build_lexical_query("Properties", top_k=4)
    should_clauses = query["query"]["bool"]["should"]

    assert any(clause.get("term", {}).get("item.keyword", {}).get("value") == "Item 2. Properties" for clause in should_clauses)


def test_build_lexical_query_filters_by_shared_index_schema_version() -> None:
    query = _build_lexical_query("What does Amazon's business focus on?", top_k=4)

    assert {"term": {"index_version": INDEX_SCHEMA_VERSION}} in query["query"]["bool"]["filter"]

def test_build_vector_query_uses_knn_and_item_filter_for_explicit_item_query() -> None:
    query = _build_vector_query([0.1] * 8, top_k=4, question="Item 2 properties", intent="narrative_explainer")
    knn_query = query["query"]["knn"]["embedding"]

    assert knn_query["k"] == 12
    assert {"term": {"index_version": INDEX_SCHEMA_VERSION}} in knn_query["filter"]["bool"]["filter"]
    assert {"term": {"item.keyword": "Item 2. Properties"}} in knn_query["filter"]["bool"]["filter"]

def test_build_vector_query_filters_generic_section_overview_by_item() -> None:
    for question in ("Risk factor", "Risk Factors"):
        query = _build_vector_query([0.1] * 8, top_k=4, question=question, intent="section_overview")
        knn_query = query["query"]["knn"]["embedding"]

        assert {"term": {"item.keyword": "Item 1A. Risk Factors"}} in knn_query["filter"]["bool"]["filter"]

def test_get_retrieval_profile_keeps_heading_lookup_lexical_only() -> None:
    profile = _get_retrieval_profile("Can you tell me more about We Face Intense Competition")

    assert profile.intent == "heading_lookup"
    assert profile.lexical_weight == 1.0
    assert profile.vector_weight == 0.0

def test_get_retrieval_profile_prefers_lexical_but_keeps_vector_for_section_overview() -> None:
    for question in ("Risk factor", "Risk Factors"):
        profile = _get_retrieval_profile(question)

        assert profile.intent == "section_overview"
        assert profile.lexical_weight > profile.vector_weight
        assert profile.vector_weight > 0.0

def test_should_run_vector_search_skips_strong_entity_lookup_match() -> None:
    profile = _get_retrieval_profile("Who is Andrew R. Jassy?")
    lexical_chunks = [
        RetrievedChunk(
            chunk_id="exec-row",
            doc_id="amazon_10k_2019",
            title="Amazon.com, Inc. Form 10-K",
            section="Executive Officers and Directors",
            content="Andrew R. Jassy, age 52, serves as CEO Amazon Web Services.",
            source_path="Company-10k-18pages.pdf",
            source_uri="docs/company/Company-10k-18pages.pdf",
            score=4.2,
            lexical_score=4.2,
            vector_score=0.0,
            content_type="profile_row",
            entity_name="Andrew R. Jassy",
            entity_role="CEO Amazon Web Services",
        )
    ]

    assert _should_run_vector_search("Who is Andrew R. Jassy?", lexical_chunks, profile) is False


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

@patch("app.backend.search_client.generate_embedding")
def test_run_vector_search_uses_native_knn_hits(mock_generate_embedding: Mock) -> None:
    mock_generate_embedding.return_value = [0.1] * 8
    client = Mock()
    client.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_id": "chunk-1",
                    "_score": 0.87,
                    "_source": {
                        "chunk_id": "chunk-1",
                        "doc_id": "amazon_10k_2019",
                        "title": "Amazon.com, Inc. Form 10-K",
                        "section": "Item 1. Business",
                        "content": "We serve consumers through our online and physical stores.",
                        "source_path": "Company-10k-18pages.pdf",
                        "source_uri": "docs/company/Company-10k-18pages.pdf",
                        "content_type": "narrative",
                    },
                }
            ]
        }
    }

    profile = _get_retrieval_profile("What does Amazon's business focus on?")
    chunks = _run_vector_search(client, "policy-faq-chunks", "What does Amazon's business focus on?", 4, profile, [])

    assert len(chunks) == 1
    assert chunks[0].vector_score == 0.87
    assert "knn" in client.search.call_args.kwargs["body"]["query"]

@patch("app.backend.search_client.generate_embedding")
def test_run_vector_search_falls_back_when_embedding_generation_fails(mock_generate_embedding: Mock) -> None:
    mock_generate_embedding.side_effect = LLMClientError("embedding failed")
    client = Mock()

    profile = _get_retrieval_profile("What does Amazon's business focus on?")
    chunks = _run_vector_search(client, "policy-faq-chunks", "What does Amazon's business focus on?", 4, profile, [])

    assert chunks == []
    client.search.assert_not_called()


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
