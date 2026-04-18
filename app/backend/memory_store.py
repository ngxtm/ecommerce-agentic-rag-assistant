from __future__ import annotations

import os
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from app.backend.aws_auth import get_boto3_session
from app.backend.config import get_aws_region
from app.backend.models import ConversationMessage, SessionState


logger = logging.getLogger(__name__)


DEFAULT_RECENT_MESSAGE_LIMIT = 10
DEFAULT_MEMORY_TTL_DAYS = 7
SESSION_SORT_KEY = "SESSION"
SESSION_ITEM_TYPE = "SESSION"
MESSAGE_ITEM_TYPE = "MESSAGE"


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now_utc().isoformat()


def _compute_ttl_epoch(days: int) -> int:
    expires_at = _now_utc() + timedelta(days=days)
    return int(expires_at.timestamp())


def _get_ttl_days() -> int:
    return int(os.getenv("MEMORY_TTL_DAYS", str(DEFAULT_MEMORY_TTL_DAYS)))


def _build_message_sort_key(message_ts: str, message_id: str) -> str:
    return f"MESSAGE#{message_ts}#{message_id}"


def _trim_recent_messages(messages: list[ConversationMessage]) -> list[ConversationMessage]:
    return messages[-DEFAULT_RECENT_MESSAGE_LIMIT:]


def _message_to_dict(message: ConversationMessage) -> dict[str, Any]:
    return message.model_dump(mode="json")


def _message_from_dict(payload: dict[str, Any]) -> ConversationMessage:
    return ConversationMessage.model_validate(payload)


class InMemorySessionStore:
    def __init__(self) -> None:
        self._sessions: dict[str, SessionState] = {}

    def load(self, session_id: str) -> SessionState:
        existing = self._sessions.get(session_id)
        if existing is None:
            existing = SessionState(session_id=session_id)
            self._sessions[session_id] = existing
        elif existing.session_id is None:
            existing.session_id = session_id
        return existing.model_copy(deep=True)

    def save(self, session_id: str, state: SessionState) -> None:
        snapshot = state.model_copy(deep=True)
        snapshot.session_id = session_id
        now = _now_iso()
        snapshot.created_at = snapshot.created_at or now
        snapshot.updated_at = now
        snapshot.ttl = _compute_ttl_epoch(_get_ttl_days())
        snapshot.recent_messages = _trim_recent_messages(snapshot.recent_messages)
        self._sessions[session_id] = snapshot

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        contains_pii: bool = False,
        retrieval_refs: list[str] | None = None,
        tool_name: str | None = None,
        tool_result_summary: str | None = None,
    ) -> SessionState:
        state = self.load(session_id)
        message = ConversationMessage(
            message_ts=_now_iso(),
            role=role,
            content=content,
            tool_name=tool_name,
            tool_result_summary=tool_result_summary,
            retrieval_refs=retrieval_refs or [],
            contains_pii=contains_pii,
            ttl=_compute_ttl_epoch(_get_ttl_days()),
        )
        state.recent_messages.append(message)
        state.recent_messages = _trim_recent_messages(state.recent_messages)
        self.save(session_id, state)
        return self.load(session_id)


class DynamoDBSessionStore:
    def __init__(self, table_name: str, region_name: str | None = None) -> None:
        self._table_name = table_name
        self._region_name = region_name or get_aws_region()
        session = get_boto3_session(region_name=self._region_name)
        resource = session.resource("dynamodb", region_name=self._region_name)
        self._table = resource.Table(table_name)

    def _session_item_from_state(self, state: SessionState) -> dict[str, Any]:
        if state.session_id is None:
            raise ValueError("session_id is required to persist session state.")
        return {
            "pk": state.session_id,
            "sk": SESSION_SORT_KEY,
            "item_type": SESSION_ITEM_TYPE,
            "session_id": state.session_id,
            "created_at": state.created_at,
            "updated_at": state.updated_at,
            "current_intent": state.current_intent.value if state.current_intent else None,
            "workflow_state": state.workflow_state.value,
            "verification_state": state.verification_state.model_dump(mode="json"),
            "collected_fields": state.collected_fields.model_dump(mode="json"),
            "verified_customer_ref": state.verified_customer_ref,
            "recent_messages": [_message_to_dict(message) for message in state.recent_messages],
            "ttl": state.ttl,
        }

    def _state_from_session_item(self, session_id: str, item: dict[str, Any] | None) -> SessionState:
        if item is None:
            return SessionState(session_id=session_id)

        payload = {
            "session_id": item.get("session_id", session_id),
            "created_at": item.get("created_at"),
            "updated_at": item.get("updated_at"),
            "current_intent": item.get("current_intent"),
            "workflow_state": item.get("workflow_state"),
            "verification_state": item.get("verification_state", {}),
            "collected_fields": item.get("collected_fields", {}),
            "verified_customer_ref": item.get("verified_customer_ref"),
            "ttl": item.get("ttl"),
            "recent_messages": [_message_from_dict(message) for message in item.get("recent_messages", [])],
        }
        return SessionState.model_validate(payload)

    def _message_item_from_model(self, session_id: str, message: ConversationMessage) -> dict[str, Any]:
        return {
            "pk": session_id,
            "sk": _build_message_sort_key(message.message_ts or _now_iso(), message.message_id),
            "item_type": MESSAGE_ITEM_TYPE,
            "session_id": session_id,
            **_message_to_dict(message),
        }

    def load(self, session_id: str) -> SessionState:
        response = self._table.get_item(Key={"pk": session_id, "sk": SESSION_SORT_KEY})
        state = self._state_from_session_item(session_id, response.get("Item"))
        state.recent_messages = _trim_recent_messages(state.recent_messages)
        return state

    def save(self, session_id: str, state: SessionState) -> None:
        snapshot = state.model_copy(deep=True)
        snapshot.session_id = session_id
        now = _now_iso()
        snapshot.created_at = snapshot.created_at or now
        snapshot.updated_at = now
        snapshot.ttl = _compute_ttl_epoch(_get_ttl_days())
        snapshot.recent_messages = _trim_recent_messages(snapshot.recent_messages)
        self._table.put_item(Item=self._session_item_from_state(snapshot))

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        contains_pii: bool = False,
        retrieval_refs: list[str] | None = None,
        tool_name: str | None = None,
        tool_result_summary: str | None = None,
    ) -> SessionState:
        state = self.load(session_id)
        message = ConversationMessage(
            message_ts=_now_iso(),
            role=role,
            content=content,
            tool_name=tool_name,
            tool_result_summary=tool_result_summary,
            retrieval_refs=retrieval_refs or [],
            contains_pii=contains_pii,
            ttl=_compute_ttl_epoch(_get_ttl_days()),
        )
        state.recent_messages.append(message)
        state.recent_messages = _trim_recent_messages(state.recent_messages)
        self.save(session_id, state)
        self._table.put_item(Item=self._message_item_from_model(session_id, message))
        return self.load(session_id)


def _build_session_store() -> InMemorySessionStore | DynamoDBSessionStore:
    backend = os.getenv("MEMORY_BACKEND", "inmemory").casefold()
    if backend == "dynamodb":
        table_name = os.getenv("DYNAMODB_CONVERSATION_TABLE")
        if not table_name:
            raise ValueError("DYNAMODB_CONVERSATION_TABLE must be set when MEMORY_BACKEND=dynamodb.")
        logger.info("Initializing DynamoDB session store for table '%s'", table_name)
        return DynamoDBSessionStore(table_name=table_name)
    logger.info("Initializing in-memory session store")
    return InMemorySessionStore()


session_store = _build_session_store()
