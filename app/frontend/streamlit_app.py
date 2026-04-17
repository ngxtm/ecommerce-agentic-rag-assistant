import os
import uuid

import httpx
import streamlit as st


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
st.caption("Phase 0 local UI stub for the Cloud Kinetics assignment")

session_id = st.text_input("Session ID", value=_get_session_id())
messages = _get_messages()

for message in messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

prompt = st.chat_input("Ask a question about company documents or your order")

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
                lines.append(f"- {source['title']}: {source['snippet']}")

        assistant_message = "\n\n".join(lines)
    except httpx.HTTPError as exc:
        assistant_message = f"Backend request failed: {exc}"

    messages.append({"role": "assistant", "content": assistant_message})
    with st.chat_message("assistant"):
        st.markdown(assistant_message)
