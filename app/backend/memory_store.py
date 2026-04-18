from app.backend.models import ConversationMessage, SessionState


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def load(self, session_id: str) -> SessionState:
        existing = self._sessions.get(session_id)
        if existing is None:
            existing = SessionState()
            self._sessions[session_id] = existing
        return existing.model_copy(deep=True)

    def save(self, session_id: str, state: SessionState) -> None:
        self._sessions[session_id] = state.model_copy(deep=True)

    def append_message(self, session_id: str, role: str, content: str) -> SessionState:
        state = self.load(session_id)
        state.recent_messages.append(ConversationMessage(role=role, content=content))
        state.recent_messages = state.recent_messages[-10:]
        self.save(session_id, state)
        return state


session_store = InMemorySessionStore()
