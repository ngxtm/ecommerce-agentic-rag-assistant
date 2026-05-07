from __future__ import annotations

import json
import os
import uuid
from typing import NotRequired, TypedDict

import httpx
import streamlit as st
from dotenv import load_dotenv

try:
    from app.frontend.chat_state import append_history_message, commit_assistant_message, consume_post_commit_rerender
except ModuleNotFoundError:
    from chat_state import append_history_message, commit_assistant_message, consume_post_commit_rerender

EVENT_VERSION = 1
STREAMING_ORDER_FALLBACK_MESSAGE = "Streaming is only available for knowledge questions."

load_dotenv()
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8000").rstrip("/")
BACKEND_REQUEST_TIMEOUT_SECONDS = float(os.getenv("BACKEND_REQUEST_TIMEOUT_SECONDS", "60"))
BACKEND_STREAM_READ_TIMEOUT_SECONDS = float(os.getenv("BACKEND_STREAM_READ_TIMEOUT_SECONDS", "90"))


class ChatMessage(TypedDict):
    role: str
    content: str
    sources: list[str]
    stream_mode: NotRequired[str]


def _backend_request_timeout() -> httpx.Timeout:
    return httpx.Timeout(BACKEND_REQUEST_TIMEOUT_SECONDS)


def _backend_stream_timeout() -> httpx.Timeout:
    return httpx.Timeout(connect=10.0, read=BACKEND_STREAM_READ_TIMEOUT_SECONDS, write=30.0, pool=10.0)


def _assistant_message(content: str, sources: list[str] | None = None, stream_mode: str | None = None) -> ChatMessage:
    message: ChatMessage = {
        "role": "assistant",
        "content": content,
        "sources": list(sources or []),
    }
    if stream_mode:
        message["stream_mode"] = stream_mode
    return message


def _user_message(content: str) -> ChatMessage:
    return {
        "role": "user",
        "content": content,
        "sources": [],
    }


def _normalize_message(message: object) -> ChatMessage | None:
    if not isinstance(message, dict):
        return None
    normalized_message: ChatMessage = {
        "role": str(message.get("role", "assistant")),
        "content": str(message.get("content", "")),
        "sources": [str(source) for source in message.get("sources", [])] if isinstance(message.get("sources"), list) else [],
    }
    stream_mode = message.get("stream_mode")
    if isinstance(stream_mode, str) and stream_mode:
        normalized_message["stream_mode"] = stream_mode
    return normalized_message


def _fetch_backend_fallback_message(payload: dict[str, str]) -> ChatMessage:
    fallback_response = httpx.post(
        f"{BACKEND_BASE_URL}/chat",
        json=payload,
        timeout=_backend_request_timeout(),
    )
    fallback_response.raise_for_status()
    return _build_blocking_message(fallback_response.json(), stream_mode="blocking_fallback")


def _read_stream_error_detail(response: httpx.Response) -> str:
    try:
        payload = json.loads(response.read().decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return ""
    if isinstance(payload, dict):
        return str(payload.get("detail", ""))
    return ""


def _get_session_id() -> str:
    if "chat_session_id" not in st.session_state:
        st.session_state.chat_session_id = str(uuid.uuid4())
    return st.session_state.chat_session_id


def _get_messages() -> list[ChatMessage]:
    raw_messages = st.session_state.get("messages", [])
    normalized_messages: list[ChatMessage] = []
    if isinstance(raw_messages, list):
        for raw_message in raw_messages:
            normalized_message = _normalize_message(raw_message)
            if normalized_message is not None:
                normalized_messages.append(normalized_message)
    st.session_state.messages = normalized_messages
    return st.session_state.messages


def _format_sources(sources: list[dict[str, object]]) -> list[str]:
    lines: list[str] = []
    if not sources:
        return lines
    lines.append("Sources:")
    for source in sources:
        detail_parts: list[str] = []
        if source.get("item"):
            detail_parts.append(str(source["item"]))
        if source.get("subsection"):
            detail_parts.append(str(source["subsection"]))
        page_start = source.get("page_start")
        page_end = source.get("page_end")
        if page_start and page_end:
            page_label = f"pp. {page_start}-{page_end}" if page_start != page_end else f"p. {page_start}"
            detail_parts.append(page_label)
        metric = source.get("metric")
        year = source.get("year")
        if metric and year:
            detail_parts.append(f"{metric} ({year})")
        elif metric:
            detail_parts.append(str(metric))
        elif year:
            detail_parts.append(str(year))
        detail_suffix = f" [{' | '.join(detail_parts)}]" if detail_parts else ""
        lines.append(f"- {source['title']}{detail_suffix}: {source['snippet']}")
    return lines


def _build_blocking_message(data: dict[str, object], *, stream_mode: str | None = None) -> ChatMessage:
    lines = [str(data["answer"])]
    verification_state = data.get("verification_state")
    if isinstance(verification_state, dict):
        missing_fields = verification_state.get("missing_fields") or []
        if missing_fields:
            lines.append(f"Missing fields: {', '.join(missing_fields)}")
    return _assistant_message("\n\n".join(lines), _format_sources(data.get("sources") or []), stream_mode=stream_mode)


def _render_sources(source_lines: list[str], placeholder: st.delta_generator.DeltaGenerator | None = None) -> None:
    if not source_lines:
        if placeholder is not None:
            placeholder.empty()
        return
    target = placeholder if placeholder is not None else st
    target.markdown("\n\n".join(source_lines))


def _render_message(message: ChatMessage) -> None:
    st.markdown(message["content"])
    _render_sources(message["sources"])


def _stream_knowledge_message(
    payload: dict[str, str],
    *,
    status_placeholder: st.delta_generator.DeltaGenerator,
    answer_placeholder: st.delta_generator.DeltaGenerator,
    sources_placeholder: st.delta_generator.DeltaGenerator,
) -> ChatMessage:
    answer_parts: list[str] = []
    final_payload: dict[str, object] | None = None
    current_event: str | None = None

    try:
        with httpx.stream("POST", f"{BACKEND_BASE_URL}/chat/stream", json=payload, timeout=_backend_stream_timeout()) as response:
            if response.status_code == 400:
                detail = _read_stream_error_detail(response)
                if detail == STREAMING_ORDER_FALLBACK_MESSAGE:
                    fallback_message = _fetch_backend_fallback_message(payload)
                    status_placeholder.empty()
                    answer_placeholder.markdown(fallback_message["content"])
                    _render_sources(fallback_message["sources"], sources_placeholder)
                    return fallback_message
                raise RuntimeError(detail or "Backend rejected the streaming request.")
            if response.status_code >= 500:
                fallback_message = _fetch_backend_fallback_message(payload)
                status_placeholder.empty()
                answer_placeholder.markdown(fallback_message["content"])
                _render_sources(fallback_message["sources"], sources_placeholder)
                return fallback_message
            response.raise_for_status()

            for raw_line in response.iter_lines():
                if raw_line is None:
                    continue
                line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
                if line.startswith("event:"):
                    current_event = line.split(":", 1)[1].strip()
                    continue
                if not line.startswith("data:"):
                    continue
                payload_json = json.loads(line.split(":", 1)[1].strip())
                if payload_json.get("event_version") != EVENT_VERSION:
                    raise RuntimeError("Unsupported stream event version.")
                if current_event == "status":
                    status_message = str(payload_json.get("message", "")).strip() or "Working..."
                    status_placeholder.markdown(f"_{status_message}_")
                elif current_event == "delta":
                    delta = str(payload_json.get("delta", ""))
                    if delta:
                        answer_parts.append(delta)
                        answer_placeholder.markdown("".join(answer_parts))
                elif current_event == "final":
                    final_payload = payload_json
                elif current_event == "error":
                    raise RuntimeError(str(payload_json.get("message", "Knowledge answer streaming failed before completion.")))
    except (httpx.TimeoutException, httpx.HTTPError):
        fallback_message = _fetch_backend_fallback_message(payload)
        status_placeholder.empty()
        answer_placeholder.markdown(fallback_message["content"])
        _render_sources(fallback_message["sources"], sources_placeholder)
        return fallback_message

    if final_payload is None:
        raise RuntimeError("Knowledge answer streaming ended without a final event.")

    final_answer = str(final_payload.get("full_answer", "")).strip() or "".join(answer_parts)
    answer_placeholder.markdown(final_answer)
    status_placeholder.empty()
    source_lines = _format_sources(final_payload.get("sources") or [])
    _render_sources(source_lines, sources_placeholder)
    final_mode = final_payload.get("mode")
    return _assistant_message(final_answer, source_lines, stream_mode=final_mode if isinstance(final_mode, str) else None)


st.set_page_config(page_title="Agentic Commerce Assistant", page_icon=":speech_balloon:")
st.title("Agentic Commerce Assistant")

session_id = st.text_input("Session ID", value=_get_session_id())
consume_post_commit_rerender(st.session_state)
messages = _get_messages()

for message in messages:
    with st.chat_message(message["role"]):
        _render_message(message)

prompt = st.chat_input("Ask about company documents or check an order status")

if prompt:
    append_history_message(st.session_state, _user_message(prompt))
    with st.chat_message("user"):
        st.markdown(prompt)

    payload = {
        "session_id": session_id,
        "message": prompt,
    }

    with st.chat_message("assistant"):
        status_placeholder = st.empty()
        answer_placeholder = st.empty()
        sources_placeholder = st.empty()
        try:
            assistant_message = _stream_knowledge_message(
                payload,
                status_placeholder=status_placeholder,
                answer_placeholder=answer_placeholder,
                sources_placeholder=sources_placeholder,
            )
        except (httpx.HTTPError, RuntimeError) as exc:
            status_placeholder.empty()
            sources_placeholder.empty()
            error_text = str(exc)
            if error_text and not error_text.startswith("Backend request failed:") and not error_text.startswith("Knowledge"):
                assistant_content = error_text
            else:
                assistant_content = f"Backend request failed: {exc}"
            answer_placeholder.markdown(assistant_content)
            assistant_message = _assistant_message(assistant_content)

    commit_assistant_message(st.session_state, assistant_message)
    st.rerun()
