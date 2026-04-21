import json
import os
import uuid

import httpx
import streamlit as st
from dotenv import load_dotenv


EVENT_VERSION = 1
STREAMING_ORDER_FALLBACK_MESSAGE = "Streaming is only available for knowledge questions."


load_dotenv()
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8000").rstrip("/")
BACKEND_REQUEST_TIMEOUT_SECONDS = float(os.getenv("BACKEND_REQUEST_TIMEOUT_SECONDS", "60"))
BACKEND_STREAM_READ_TIMEOUT_SECONDS = float(os.getenv("BACKEND_STREAM_READ_TIMEOUT_SECONDS", "90"))


def _backend_request_timeout() -> httpx.Timeout:
    return httpx.Timeout(BACKEND_REQUEST_TIMEOUT_SECONDS)


def _backend_stream_timeout() -> httpx.Timeout:
    return httpx.Timeout(connect=10.0, read=BACKEND_STREAM_READ_TIMEOUT_SECONDS, write=30.0, pool=10.0)


def _render_backend_fallback(payload: dict[str, str]) -> str:
    fallback_response = httpx.post(
        f"{BACKEND_BASE_URL}/chat",
        json=payload,
        timeout=_backend_request_timeout(),
    )
    fallback_response.raise_for_status()
    return _render_blocking_response(fallback_response.json())


def _get_session_id() -> str:
    if "chat_session_id" not in st.session_state:
        st.session_state.chat_session_id = str(uuid.uuid4())
    return st.session_state.chat_session_id


def _get_messages() -> list[dict[str, str]]:
    if "messages" not in st.session_state:
        st.session_state.messages = []
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


def _render_blocking_response(data: dict[str, object]) -> str:
    lines = [str(data["answer"])]
    verification_state = data.get("verification_state", {})
    missing_fields = verification_state.get("missing_fields") or []
    if missing_fields:
        lines.append(f"Missing fields: {', '.join(missing_fields)}")
    lines.extend(_format_sources(data.get("sources") or []))
    return "\n\n".join(lines)


def _stream_knowledge_chunks(payload: dict[str, str]):
    final_payload: dict[str, object] | None = None
    try:
        with httpx.stream("POST", f"{BACKEND_BASE_URL}/chat/stream", json=payload, timeout=_backend_stream_timeout()) as response:
            if response.status_code == 400:
                detail = response.json().get("detail", "")
                if detail == STREAMING_ORDER_FALLBACK_MESSAGE:
                    raise RuntimeError(_render_backend_fallback(payload))
            if response.status_code >= 500:
                raise RuntimeError(_render_backend_fallback(payload))
            response.raise_for_status()
            current_event: str | None = None
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
                if current_event == "delta":
                    delta = str(payload_json.get("delta", ""))
                    if delta:
                        yield delta
                elif current_event == "final":
                    final_payload = payload_json
                elif current_event == "error":
                    raise RuntimeError(str(payload_json.get("message", "Knowledge answer streaming failed before completion.")))
    except (httpx.TimeoutException, httpx.HTTPError):
        raise RuntimeError(_render_backend_fallback(payload))
    if final_payload is None:
        raise RuntimeError("Knowledge answer streaming ended without a final event.")
    st.session_state["last_stream_sources"] = _format_sources(final_payload.get("sources") or [])


st.set_page_config(page_title="Agentic Commerce Assistant", page_icon=":speech_balloon:")
st.title("Agentic Commerce Assistant")

session_id = st.text_input("Session ID", value=_get_session_id())
messages = _get_messages()

for message in messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Ask about company documents or check an order status")

if prompt:
    messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    payload = {
        "session_id": session_id,
        "message": prompt,
    }

    try:
        with st.chat_message("assistant"):
            st.session_state["last_stream_sources"] = []
            streamed_answer = st.write_stream(_stream_knowledge_chunks(payload))
            source_lines = st.session_state.pop("last_stream_sources", [])
            if source_lines:
                st.markdown("\n\n".join(source_lines))
                assistant_message = "\n\n".join([streamed_answer, *source_lines])
            else:
                assistant_message = str(streamed_answer)
    except (httpx.HTTPError, RuntimeError) as exc:
        error_text = str(exc)
        if error_text and not error_text.startswith("Backend request failed:") and not error_text.startswith("Knowledge"):
            assistant_message = error_text
        else:
            assistant_message = f"Backend request failed: {exc}"
        with st.chat_message("assistant"):
            st.markdown(assistant_message)

    messages.append({"role": "assistant", "content": assistant_message})
