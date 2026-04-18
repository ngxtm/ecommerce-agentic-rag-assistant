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
                        "doc_id": "shipping_policy",
                        "title": "Shipping Policy",
                        "section": "Tracking Information",
                        "content": "Tracking information is usually available within 24 hours.",
                        "source_path": "shipping_policy.md",
                        "source_uri": "s3://agentic-embedding-us/phase1-kb/shipping_policy.md",
                    },
                }
            ]
        }
    }
    mock_build_client.return_value = mock_client

    chunks = search_chunks("When is tracking available?")

    assert len(chunks) == 1
    assert chunks[0].title == "Shipping Policy"
    assert chunks[0].score == 4.2


@patch("app.backend.search_client._build_client")
@patch("app.backend.search_client.os.getenv")
def test_search_chunks_returns_empty_when_no_hits(mock_getenv: Mock, mock_build_client: Mock) -> None:
    mock_getenv.return_value = "policy-faq-chunks"
    mock_client = Mock()
    mock_client.search.return_value = {"hits": {"hits": []}}
    mock_build_client.return_value = mock_client

    assert search_chunks("unknown question") == []
