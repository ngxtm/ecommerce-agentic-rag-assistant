import os
import uuid

import httpx
import streamlit as st
from dotenv import load_dotenv


load_dotenv()
BACKEND_BASE_URL = os.getenv("BACKEND_BASE_URL", "http://localhost:8000")


def _get_session_id() -> str:
    if "chat_session_id" not in st.session_state:
        st.session_state.chat_session_id = str(uuid.uuid4())
    return st.session_state.chat_session_id


def _get_messages() -> list[dict[str, str]]:
    if "messages" not in st.session_state:
        st.session_state.messages = []
    return st.session_state.messages


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
        response = httpx.post(f"{BACKEND_BASE_URL}/chat", json=payload, timeout=30.0)
        response.raise_for_status()
        data = response.json()

        lines = [data["answer"]]
        verification_state = data.get("verification_state", {})
        missing_fields = verification_state.get("missing_fields") or []
        if missing_fields:
            lines.append(f"Missing fields: {', '.join(missing_fields)}")

        sources = data.get("sources") or []
        if sources:
            lines.append("Sources:")
            for source in sources:
                detail_parts: list[str] = []
                if source.get("item"):
                    detail_parts.append(source["item"])
                if source.get("subsection"):
                    detail_parts.append(source["subsection"])
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
                    detail_parts.append(metric)
                elif year:
                    detail_parts.append(str(year))

                detail_suffix = f" [{' | '.join(detail_parts)}]" if detail_parts else ""
                lines.append(f"- {source['title']}{detail_suffix}: {source['snippet']}")

        assistant_message = "\n\n".join(lines)
    except httpx.HTTPError as exc:
        assistant_message = f"Backend request failed: {exc}"

    messages.append({"role": "assistant", "content": assistant_message})
    with st.chat_message("assistant"):
        st.markdown(assistant_message)
