from unittest.mock import Mock, patch

from app.backend.search_client import search_chunks


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
    assert chunks[0].score == 4.2
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
