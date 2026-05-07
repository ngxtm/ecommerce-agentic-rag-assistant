from __future__ import annotations

from collections.abc import MutableMapping

MESSAGES_STATE_KEY = "messages"
POST_COMMIT_RERENDER_STATE_KEY = "post_commit_rerender"


def append_history_message(session_state: MutableMapping[str, object], message: object) -> None:
    messages = session_state.get(MESSAGES_STATE_KEY)
    if not isinstance(messages, list):
        messages = []
        session_state[MESSAGES_STATE_KEY] = messages
    messages.append(message)


def mark_post_commit_rerender(session_state: MutableMapping[str, object]) -> None:
    session_state[POST_COMMIT_RERENDER_STATE_KEY] = True


def consume_post_commit_rerender(session_state: MutableMapping[str, object]) -> bool:
    should_rerender = bool(session_state.get(POST_COMMIT_RERENDER_STATE_KEY))
    if should_rerender:
        session_state.pop(POST_COMMIT_RERENDER_STATE_KEY, None)
    return should_rerender


def commit_assistant_message(session_state: MutableMapping[str, object], message: object) -> None:
    append_history_message(session_state, message)
    mark_post_commit_rerender(session_state)
