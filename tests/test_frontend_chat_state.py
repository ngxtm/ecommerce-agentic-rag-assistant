from app.frontend.chat_state import (
    MESSAGES_STATE_KEY,
    POST_COMMIT_RERENDER_STATE_KEY,
    append_history_message,
    commit_assistant_message,
    consume_post_commit_rerender,
)


def test_append_history_message_initializes_messages_list() -> None:
    session_state: dict[str, object] = {}

    append_history_message(session_state, {"role": "user", "content": "hello", "sources": []})

    assert session_state[MESSAGES_STATE_KEY] == [{"role": "user", "content": "hello", "sources": []}]


def test_commit_assistant_message_appends_once_and_marks_rerender() -> None:
    session_state: dict[str, object] = {
        MESSAGES_STATE_KEY: [{"role": "user", "content": "hello", "sources": []}],
    }
    assistant_message = {
        "role": "assistant",
        "content": "answer",
        "sources": ["Sources:\n- Item 1A"],
        "stream_mode": "llm_stream",
    }

    commit_assistant_message(session_state, assistant_message)

    assert session_state[MESSAGES_STATE_KEY] == [
        {"role": "user", "content": "hello", "sources": []},
        assistant_message,
    ]
    assert session_state[POST_COMMIT_RERENDER_STATE_KEY] is True


def test_consume_post_commit_rerender_clears_flag_after_first_read() -> None:
    session_state: dict[str, object] = {POST_COMMIT_RERENDER_STATE_KEY: True}

    assert consume_post_commit_rerender(session_state) is True
    assert POST_COMMIT_RERENDER_STATE_KEY not in session_state
    assert consume_post_commit_rerender(session_state) is False


def test_commit_assistant_message_preserves_existing_history_for_fallback_path() -> None:
    session_state: dict[str, object] = {
        MESSAGES_STATE_KEY: [
            {"role": "user", "content": "kb question", "sources": []},
            {"role": "assistant", "content": "first answer", "sources": ["Sources:\n- Item 1"]},
            {"role": "user", "content": "follow-up", "sources": []},
        ],
    }
    fallback_message = {
        "role": "assistant",
        "content": "blocking fallback answer",
        "sources": ["Sources:\n- Item 2"],
        "stream_mode": "blocking_fallback",
    }

    commit_assistant_message(session_state, fallback_message)

    assert len(session_state[MESSAGES_STATE_KEY]) == 4
    assert session_state[MESSAGES_STATE_KEY][-1] == fallback_message
