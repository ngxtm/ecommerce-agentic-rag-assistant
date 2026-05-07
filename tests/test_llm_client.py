from unittest.mock import MagicMock, Mock, patch

from app.backend.llm_client import LLMClientError, generate_chat_completion, generate_embedding, generate_embeddings

@patch("app.backend.llm_client.httpx.Client")
@patch("app.backend.llm_client.os.getenv")
def test_generate_chat_completion_returns_content(mock_getenv: Mock, mock_client_cls: Mock) -> None:
    values = {
        "LLM_API_KEY": "test-key",
        "LLM_BASE_URL": "https://example.com/v1",
        "LLM_MODEL": "cx/gpt-5.4",
        "LLM_TIMEOUT_SECONDS": "30",
    }
    mock_getenv.side_effect = lambda key, default=None: values.get(key, default)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Most items may be returned within 30 calendar days of delivery."
                }
            }
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_client.post.return_value = mock_response
    mock_client.__enter__.return_value = mock_client
    mock_client_cls.return_value = mock_client

    answer = generate_chat_completion([{"role": "user", "content": "Hello"}])

    assert "30 calendar days" in answer

@patch("app.backend.llm_client.httpx.Client")
@patch("app.backend.llm_client.os.getenv")
def test_generate_chat_completion_raises_on_empty_response(mock_getenv: Mock, mock_client_cls: Mock) -> None:
    values = {
        "LLM_API_KEY": "test-key",
        "LLM_BASE_URL": "https://example.com/v1",
        "LLM_MODEL": "cx/gpt-5.4",
        "LLM_TIMEOUT_SECONDS": "30",
    }
    mock_getenv.side_effect = lambda key, default=None: values.get(key, default)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": ""}}]}
    mock_response.raise_for_status.return_value = None
    mock_client.post.return_value = mock_response
    mock_client.__enter__.return_value = mock_client
    mock_client_cls.return_value = mock_client

    try:
        generate_chat_completion([{"role": "user", "content": "Hello"}])
    except LLMClientError as exc:
        assert "usable content" in str(exc)
    else:
        raise AssertionError("Expected LLMClientError for empty response content")

@patch("app.backend.llm_client.get_secret_string")
@patch("app.backend.llm_client.httpx.Client")
@patch("app.backend.llm_client.os.getenv")
def test_generate_chat_completion_loads_api_key_from_secret_when_env_missing(
    mock_getenv: Mock, mock_client_cls: Mock, mock_get_secret_string: Mock
) -> None:
    values = {
        "LLM_API_KEY": None,
        "LLM_API_KEY_SECRET_NAME": "agentic-commerce-llm-api-key-dev",
        "LLM_BASE_URL": "https://example.com/v1",
        "LLM_MODEL": "cx/gpt-5.4",
        "LLM_TIMEOUT_SECONDS": "30",
    }
    mock_getenv.side_effect = lambda key, default=None: values.get(key, default)
    mock_get_secret_string.return_value = "secret-key"

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "choices": [
            {
                "message": {
                    "content": "Grounded answer from secret-backed key."
                }
            }
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_client.post.return_value = mock_response
    mock_client.__enter__.return_value = mock_client
    mock_client_cls.return_value = mock_client

    answer = generate_chat_completion([{"role": "user", "content": "Hello"}])

    assert answer == "Grounded answer from secret-backed key."
    mock_get_secret_string.assert_called_once_with("agentic-commerce-llm-api-key-dev")

@patch("app.backend.llm_client.get_secret_string")
@patch("app.backend.llm_client.httpx.Client")
@patch("app.backend.llm_client.os.getenv")
def test_generate_embedding_uses_embedding_specific_base_url_and_secret(
    mock_getenv: Mock, mock_client_cls: Mock, mock_get_secret_string: Mock
) -> None:
    values = {
        "LLM_API_KEY": "chat-key",
        "LLM_BASE_URL": "https://chat.example.com/v1",
        "LLM_MODEL": "cx/gpt-5.4",
        "LLM_EMBEDDING_API_KEY": None,
        "LLM_EMBEDDING_API_KEY_SECRET_NAME": "embedding-secret",
        "LLM_EMBEDDING_BASE_URL": "https://openrouter.ai/api/v1",
        "LLM_EMBEDDING_MODEL": "qwen/qwen3-embedding-8b",
        "LLM_TIMEOUT_SECONDS": "30",
    }
    mock_getenv.side_effect = lambda key, default=None: values.get(key, default)
    mock_get_secret_string.side_effect = lambda name: "embedding-key" if name == "embedding-secret" else "chat-secret"

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": [{"embedding": [0.1, 0.2, 0.3]}]}
    mock_response.raise_for_status.return_value = None
    mock_client.post.return_value = mock_response
    mock_client.__enter__.return_value = mock_client
    mock_client_cls.return_value = mock_client

    embedding = generate_embedding("Amazon risk factors")

    assert embedding == [0.1, 0.2, 0.3]
    call = mock_client.post.call_args
    assert call.args[0] == "https://openrouter.ai/api/v1/embeddings"
    assert call.kwargs["headers"]["Authorization"] == "Bearer embedding-key"
    assert call.kwargs["json"]["model"] == "qwen/qwen3-embedding-8b"

@patch("app.backend.llm_client.httpx.Client")
@patch("app.backend.llm_client.os.getenv")
def test_generate_embedding_falls_back_to_chat_config_when_embedding_specific_values_missing(
    mock_getenv: Mock, mock_client_cls: Mock
) -> None:
    values = {
        "LLM_API_KEY": "chat-key",
        "LLM_BASE_URL": "https://chat.example.com/v1",
        "LLM_MODEL": "cx/gpt-5.4",
        "LLM_EMBEDDING_API_KEY": None,
        "LLM_EMBEDDING_API_KEY_SECRET_NAME": None,
        "LLM_EMBEDDING_BASE_URL": None,
        "LLM_EMBEDDING_MODEL": None,
        "LLM_TIMEOUT_SECONDS": "30",
    }
    mock_getenv.side_effect = lambda key, default=None: values.get(key, default)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {"data": [{"embedding": [0.4, 0.5, 0.6]}]}
    mock_response.raise_for_status.return_value = None
    mock_client.post.return_value = mock_response
    mock_client.__enter__.return_value = mock_client
    mock_client_cls.return_value = mock_client

    embedding = generate_embedding("Amazon business overview")

    assert embedding == [0.4, 0.5, 0.6]
    call = mock_client.post.call_args
    assert call.args[0] == "https://chat.example.com/v1/embeddings"
    assert call.kwargs["headers"]["Authorization"] == "Bearer chat-key"
    assert call.kwargs["json"]["model"] == "cx/gpt-5.4"

@patch("app.backend.llm_client.httpx.Client")
@patch("app.backend.llm_client.os.getenv")
def test_generate_chat_completion_ignores_embedding_specific_config(mock_getenv: Mock, mock_client_cls: Mock) -> None:
    values = {
        "LLM_API_KEY": "chat-key",
        "LLM_BASE_URL": "https://chat.example.com/v1",
        "LLM_MODEL": "cx/gpt-5.4",
        "LLM_EMBEDDING_API_KEY": "embedding-key",
        "LLM_EMBEDDING_BASE_URL": "https://openrouter.ai/api/v1",
        "LLM_EMBEDDING_MODEL": "qwen/qwen3-embedding-8b",
        "LLM_TIMEOUT_SECONDS": "30",
    }
    mock_getenv.side_effect = lambda key, default=None: values.get(key, default)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {"choices": [{"message": {"content": "Grounded answer."}}]}
    mock_response.raise_for_status.return_value = None
    mock_client.post.return_value = mock_response
    mock_client.__enter__.return_value = mock_client
    mock_client_cls.return_value = mock_client

    answer = generate_chat_completion([{"role": "user", "content": "Hello"}])

    assert answer == "Grounded answer."
    call = mock_client.post.call_args
    assert call.args[0] == "https://chat.example.com/v1/chat/completions"
    assert call.kwargs["headers"]["Authorization"] == "Bearer chat-key"
    assert call.kwargs["json"]["model"] == "cx/gpt-5.4"

@patch("app.backend.llm_client.httpx.Client")
@patch("app.backend.llm_client.os.getenv")
def test_generate_embeddings_uses_embedding_specific_batch_config(mock_getenv: Mock, mock_client_cls: Mock) -> None:
    values = {
        "LLM_API_KEY": "chat-key",
        "LLM_BASE_URL": "https://chat.example.com/v1",
        "LLM_MODEL": "cx/gpt-5.4",
        "LLM_EMBEDDING_API_KEY": "embedding-key",
        "LLM_EMBEDDING_BASE_URL": "https://openrouter.ai/api/v1",
        "LLM_EMBEDDING_MODEL": "qwen/qwen3-embedding-8b",
        "LLM_TIMEOUT_SECONDS": "30",
    }
    mock_getenv.side_effect = lambda key, default=None: values.get(key, default)

    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {"index": 1, "embedding": [0.4, 0.5]},
            {"index": 0, "embedding": [0.1, 0.2]},
        ]
    }
    mock_response.raise_for_status.return_value = None
    mock_client.post.return_value = mock_response
    mock_client.__enter__.return_value = mock_client
    mock_client_cls.return_value = mock_client

    embeddings = generate_embeddings(["first", "second"])

    assert embeddings == [[0.1, 0.2], [0.4, 0.5]]
    call = mock_client.post.call_args
    assert call.args[0] == "https://openrouter.ai/api/v1/embeddings"
    assert call.kwargs["headers"]["Authorization"] == "Bearer embedding-key"
    assert call.kwargs["json"]["model"] == "qwen/qwen3-embedding-8b"
    assert call.kwargs["json"]["input"] == ["first", "second"]
