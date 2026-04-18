from app.backend.memory_store import InMemorySessionStore


def test_inmemory_store_initializes_session_state() -> None:
    store = InMemorySessionStore()

    state = store.load("session-1")

    assert state.session_id == "session-1"
    assert state.recent_messages == []


def test_inmemory_store_appends_message_metadata() -> None:
    store = InMemorySessionStore()

    state = store.append_message(
        "session-2",
        "assistant",
        "Grounded answer",
        retrieval_refs=["chunk-1", "chunk-2"],
        tool_name="mock_order_lookup",
        tool_result_summary="order_found",
        contains_pii=False,
    )

    assert len(state.recent_messages) == 1
    message = state.recent_messages[0]
    assert message.message_id
    assert message.message_ts
    assert message.retrieval_refs == ["chunk-1", "chunk-2"]
    assert message.tool_name == "mock_order_lookup"
    assert message.tool_result_summary == "order_found"
    assert message.ttl is not None


def test_inmemory_store_keeps_recent_messages_window() -> None:
    store = InMemorySessionStore()

    for index in range(12):
        store.append_message("session-3", "user", f"message-{index}")

    state = store.load("session-3")

    assert len(state.recent_messages) == 10
    assert state.recent_messages[0].content == "message-2"
    assert state.recent_messages[-1].content == "message-11"
