from __future__ import annotations

import os
from typing import Any

import httpx


class LLMClientError(RuntimeError):
    pass


def _normalize_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


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


def generate_chat_completion(messages: list[dict[str, str]]) -> str:
    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL")
    timeout_seconds = float(os.getenv("LLM_TIMEOUT_SECONDS", "30"))

    if not api_key or not base_url or not model:
        raise ValueError("OpenAI-compatible LLM configuration is incomplete.")

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": 350,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    url = f"{_normalize_base_url(base_url)}/chat/completions"

    try:
        with httpx.Client(timeout=timeout_seconds) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
    except httpx.HTTPError as exc:
        raise LLMClientError("OpenAI-compatible chat completion request failed.") from exc

    try:
        response_json = response.json()
    except ValueError as exc:
        raise LLMClientError("OpenAI-compatible chat completion response was not valid JSON.") from exc

    content = _extract_content(response_json)
    if not content:
        raise LLMClientError("OpenAI-compatible chat completion response did not contain usable content.")
    return content
