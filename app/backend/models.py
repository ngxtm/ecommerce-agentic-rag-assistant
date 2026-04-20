from enum import Enum
from uuid import uuid4

from pydantic import BaseModel, Field


class Intent(str, Enum):
    KNOWLEDGE_QA = "KNOWLEDGE_QA"
    ORDER_STATUS = "ORDER_STATUS"
    FALLBACK = "FALLBACK"


class NextAction(str, Enum):
    ASK_USER = "ASK_USER"
    CALL_TOOL = "CALL_TOOL"
    RESPOND = "RESPOND"


class VerificationStatus(str, Enum):
    NOT_STARTED = "not_started"
    COLLECTING = "collecting"
    VERIFIED = "verified"


class WorkflowState(str, Enum):
    IDLE = "idle"
    COLLECTING_ORDER_VERIFICATION = "collecting_order_verification"
    ORDER_VERIFIED = "order_verified"
    ORDER_COMPLETED = "order_completed"


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    user_id: str | None = None


class SourceItem(BaseModel):
    source_id: str
    title: str
    snippet: str
    content_type: str | None = None
    item: str | None = None
    subsection: str | None = None
    page_start: int | None = None
    page_end: int | None = None
    entity_name: str | None = None
    entity_role: str | None = None
    metric: str | None = None
    year: str | None = None
    table_name: str | None = None


class VerificationState(BaseModel):
    status: VerificationStatus = VerificationStatus.NOT_STARTED
    missing_fields: list[str] = Field(default_factory=list)
    verified_fields: list[str] = Field(default_factory=list)


class CollectedFields(BaseModel):
    full_name: str | None = None
    date_of_birth: str | None = None
    ssn_last4: str | None = None


class ConversationMessage(BaseModel):
    message_id: str = Field(default_factory=lambda: str(uuid4()))
    message_ts: str | None = None
    role: str
    content: str
    tool_name: str | None = None
    tool_result_summary: str | None = None
    retrieval_refs: list[str] = Field(default_factory=list)
    contains_pii: bool = False
    ttl: int | None = None


class SessionState(BaseModel):
    session_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    current_intent: Intent | None = None
    workflow_state: WorkflowState = WorkflowState.IDLE
    verification_state: VerificationState = Field(default_factory=VerificationState)
    collected_fields: CollectedFields = Field(default_factory=CollectedFields)
    verified_customer_ref: str | None = None
    ttl: int | None = None
    recent_messages: list[ConversationMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    intent: Intent
    sources: list[SourceItem] = Field(default_factory=list)
    verification_state: VerificationState = Field(default_factory=VerificationState)
    next_action: NextAction
