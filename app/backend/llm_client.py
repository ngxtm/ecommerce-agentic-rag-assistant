from __future__ import annotations

import json
import os
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import httpx

from app.backend.config import get_llm_api_key_secret_name, get_llm_embedding_api_key_secret_name
from app.backend.secrets import get_secret_string

class LLMClientError(RuntimeError):
    pass

@dataclass(frozen=True)
class ProviderConfig:
    api_key: str
    base_url: str
    model: str
    timeout_seconds: float

def _get_chat_api_key() -> str:
    api_key = os.getenv("LLM_API_KEY")
    if api_key:
        return api_key

    secret_name = get_llm_api_key_secret_name()
    if secret_name:
        return get_secret_string(secret_name)

    raise ValueError("OpenAI-compatible LLM configuration is incomplete.")

def _get_embedding_api_key() -> str:
    api_key = os.getenv("LLM_EMBEDDING_API_KEY")
    if api_key:
        return api_key

    secret_name = get_llm_embedding_api_key_secret_name()
    if secret_name:
        return get_secret_string(secret_name)

    api_key = os.getenv("LLM_API_KEY")
    if api_key:
        return api_key

    raise ValueError("OpenAI-compatible embedding configuration is incomplete.")

def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")

def _get_timeout_seconds() -> float:
    return float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

def _get_required_env(primary_key: str, fallback_key: str | None = None, error_message: str | None = None) -> str:
    value = os.getenv(primary_key)
    if value:
        return value
    if fallback_key:
        fallback_value = os.getenv(fallback_key)
        if fallback_value:
            return fallback_value
    raise ValueError(error_message or "OpenAI-compatible LLM configuration is incomplete.")

def _get_chat_provider_config() -> ProviderConfig:
    return ProviderConfig(
        api_key=_get_chat_api_key(),
        base_url=_get_required_env("LLM_BASE_URL"),
        model=_get_required_env("LLM_MODEL"),
        timeout_seconds=_get_timeout_seconds(),
    )

def _get_embedding_provider_config() -> ProviderConfig:
    return ProviderConfig(
        api_key=_get_embedding_api_key(),
        base_url=_get_required_env(
            "LLM_EMBEDDING_BASE_URL",
            "LLM_BASE_URL",
            "OpenAI-compatible embedding configuration is incomplete.",
        ),
        model=_get_required_env(
            "LLM_EMBEDDING_MODEL",
            "LLM_MODEL",
            "OpenAI-compatible embedding configuration is incomplete.",
        ),
        timeout_seconds=_get_timeout_seconds(),
    )

def _extract_content(response_json: dict[str, Any]) -> str:
    choices = response_json.get("choices", [])
    if not choices:
        return ""

    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                texts.append(str(item["text"]).strip())
            elif isinstance(item, str):
                texts.append(item.strip())
        return "\n".join(text for text in texts if text)
    return ""

def _request_openai_compatible(path: str, payload: dict[str, Any], config: ProviderConfig) -> dict[str, Any]:
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    url = f"{_normalize_base_url(config.base_url)}/{path}"

    try:
        with httpx.Client(timeout=config.timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise LLMClientError(f"OpenAI-compatible request to {path} failed.") from exc

    try:
        response_json = response.json()
    except ValueError as exc:
        raise LLMClientError(f"OpenAI-compatible response from {path} was not valid JSON.") from exc

    if not isinstance(response_json, dict):
        raise LLMClientError(f"OpenAI-compatible response from {path} was not a JSON object.")
    return response_json

def generate_chat_completion(messages: list[dict[str, str]]) -> str:
    config = _get_chat_provider_config()

    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 350,
    }
    response_json = _request_openai_compatible("chat/completions", payload, config)
    content = _extract_content(response_json)
    if not content:
        raise LLMClientError("OpenAI-compatible chat completion response did not contain usable content.")
    return content

def _extract_stream_delta(payload: dict[str, Any]) -> str:
    choices = payload.get("choices", [])
    if not choices:
        return ""

    delta = choices[0].get("delta", {})
    if isinstance(delta, dict):
        content = delta.get("content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            texts: list[str] = []
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text" and item.get("text"):
                    texts.append(str(item["text"]))
                elif isinstance(item, str):
                    texts.append(item)
            return "".join(texts)
    return ""

def generate_chat_completion_stream(messages: list[dict[str, str]]) -> Iterator[str]:
    config = _get_chat_provider_config()

    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 350,
        "stream": True,
    }
    headers = {
        "Authorization": f"Bearer {config.api_key}",
        "Content-Type": "application/json",
    }
    url = f"{_normalize_base_url(config.base_url)}/chat/completions"

    try:
        with httpx.Client(timeout=config.timeout_seconds) as client:
            with client.stream("POST", url, headers=headers, json=payload) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line:
                        continue
                    if isinstance(line, bytes):
                        line = line.decode("utf-8")
                    if not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if not data or data == "[DONE]":
                        continue
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError as exc:
                        raise LLMClientError("OpenAI-compatible chat completion stream returned invalid JSON.") from exc
                    if not isinstance(chunk, dict):
                        continue
                    delta = _extract_stream_delta(chunk)
                    if delta:
                        yield delta
    except httpx.HTTPError as exc:
        raise LLMClientError("OpenAI-compatible streaming chat completion request failed.") from exc

def generate_embedding(text: str) -> list[float]:
    config = _get_embedding_provider_config()

    payload = {
        "model": config.model,
        "input": text,
    }
    response_json = _request_openai_compatible("embeddings", payload, config)
    data = response_json.get("data")
    if not isinstance(data, list) or not data:
        raise LLMClientError("OpenAI-compatible embedding response did not contain data.")
    embedding = data[0].get("embedding") if isinstance(data[0], dict) else None
    if not isinstance(embedding, list) or not embedding:
        raise LLMClientError("OpenAI-compatible embedding response did not contain a usable vector.")
    return [float(value) for value in embedding]

def generate_embeddings(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    config = _get_embedding_provider_config()

    payload = {
        "model": config.model,
        "input": texts,
    }
    response_json = _request_openai_compatible("embeddings", payload, config)
    data = response_json.get("data")
    if not isinstance(data, list) or not data:
        raise LLMClientError("OpenAI-compatible embedding response did not contain data.")

    ordered_vectors: list[list[float]] = []
    for item in sorted((entry for entry in data if isinstance(entry, dict)), key=lambda entry: int(entry.get("index", 0))):
        embedding = item.get("embedding")
        if not isinstance(embedding, list) or not embedding:
            raise LLMClientError("OpenAI-compatible embedding response did not contain a usable vector.")
        ordered_vectors.append([float(value) for value in embedding])
    return ordered_vectors
