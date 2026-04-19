from unittest.mock import Mock, patch

from app.backend.search_client import RetrievedChunk, _merge_candidates, search_chunks


@patch("app.backend.search_client._build_client")
@patch("app.backend.search_client.os.getenv")
def test_search_chunks_returns_normalized_hits(mock_getenv: Mock, mock_build_client: Mock) -> None:
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
                        "section": "Item 1. Business",
                        "content": "Amazon serves consumers through online and physical stores.",
                        "source_path": "Company-10k-18pages.pdf",
                        "source_uri": "docs/company/Company-10k-18pages.pdf",
                        "embedding": [0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
                    },
                }
            ]
        }
    }
    mock_build_client.return_value = mock_client

    chunks = search_chunks("When is tracking available?")

    assert len(chunks) == 1
    assert chunks[0].title == "Amazon.com, Inc. Form 10-K"
    assert chunks[0].score > 0
    assert chunks[0].doc_id == "amazon_10k_2019"
    assert chunks[0].embedding is not None


@patch("app.backend.search_client._build_client")
@patch("app.backend.search_client.os.getenv")
def test_search_chunks_returns_extended_metadata(mock_getenv: Mock, mock_build_client: Mock) -> None:
    mock_getenv.return_value = "policy-faq-chunks"
    mock_client = Mock()
    mock_client.search.return_value = {
        "hits": {
            "hits": [
                {
                    "_id": "amazon-row-1",
                    "_score": 8.5,
                    "_source": {
                        "chunk_id": "amazon-row-1",
                        "doc_id": "amazon_10k_2019",
                        "title": "Amazon.com, Inc. Form 10-K",
                        "section": "Item 6. Selected Consolidated Financial Data",
                        "content": "Net sales for 2019: 280,522",
                        "source_path": "Company-10k-18pages.pdf",
                        "source_uri": "docs/company/Company-10k-18pages.pdf",
                        "item": "Item 6. Selected Consolidated Financial Data",
                        "page_start": 8,
                        "page_end": 8,
                        "content_type": "table_row",
                        "table_name": "Item 6. Selected Consolidated Financial Data",
                        "metric": "Net sales",
                        "year": "2019",
                        "value_raw": "280,522",
                        "value_normalized": 280522.0,
                        "unit": "million USD",
                    },
                }
            ]
        }
    }
    mock_build_client.return_value = mock_client

    chunks = search_chunks("What were net sales in 2019?")

    assert len(chunks) == 1
    assert chunks[0].content_type == "table_row"
    assert chunks[0].metric == "Net sales"
    assert chunks[0].year == "2019"
    assert chunks[0].unit == "million USD"


@patch("app.backend.search_client._build_client")
@patch("app.backend.search_client.os.getenv")
def test_search_chunks_returns_empty_when_no_hits(mock_getenv: Mock, mock_build_client: Mock) -> None:
    mock_getenv.return_value = "policy-faq-chunks"
    mock_client = Mock()
    mock_client.search.return_value = {"hits": {"hits": []}}
    mock_build_client.return_value = mock_client

    assert search_chunks("unknown question") == []


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
    assert merged[0].score > merged[1].score


def test_merge_candidates_falls_back_to_lexical_only_when_no_vector_scores_exist() -> None:
    stronger_lexical = RetrievedChunk(
        chunk_id="item-6",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 6. Selected Consolidated Financial Data",
        content="Item 6 summary",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=7.0,
        lexical_score=7.0,
        vector_score=0.0,
    )
    weaker_lexical = RetrievedChunk(
        chunk_id="item-7",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 7. Management Discussion and Analysis",
        content="Item 7 summary",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=3.0,
        lexical_score=3.0,
        vector_score=0.0,
    )

    merged = _merge_candidates([stronger_lexical, weaker_lexical], [], top_k=2)

    assert merged[0].chunk_id == "item-6"
    assert merged[1].chunk_id == "item-7"
    assert merged[0].score >= merged[1].score


def test_merge_candidates_combines_lexical_and_vector_scores_per_chunk() -> None:
    lexical = RetrievedChunk(
        chunk_id="combined-chunk",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 6. Selected Consolidated Financial Data",
        content="Net sales for 2019: 280,522",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=8.0,
        lexical_score=8.0,
        vector_score=0.0,
    )
    vector = RetrievedChunk(
        chunk_id="combined-chunk",
        doc_id="amazon_10k_2019",
        title="Amazon.com, Inc. Form 10-K",
        section="Item 6. Selected Consolidated Financial Data",
        content="Net sales for 2019: 280,522",
        source_path="Company-10k-18pages.pdf",
        source_uri="docs/company/Company-10k-18pages.pdf",
        score=0.9,
        lexical_score=0.0,
        vector_score=0.9,
    )

    merged = _merge_candidates([lexical], [vector], top_k=1)

    assert len(merged) == 1
    assert merged[0].lexical_score == 8.0
    assert merged[0].vector_score == 0.9
    assert merged[0].score > 0
    assert merged[0].chunk_id == "combined-chunk"
