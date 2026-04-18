from enum import Enum

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


class VerificationState(BaseModel):
    status: VerificationStatus = VerificationStatus.NOT_STARTED
    missing_fields: list[str] = Field(default_factory=list)
    verified_fields: list[str] = Field(default_factory=list)


class CollectedFields(BaseModel):
    full_name: str | None = None
    date_of_birth: str | None = None
    ssn_last4: str | None = None


class ConversationMessage(BaseModel):
    role: str
    content: str


class SessionState(BaseModel):
    current_intent: Intent | None = None
    workflow_state: WorkflowState = WorkflowState.IDLE
    verification_state: VerificationState = Field(default_factory=VerificationState)
    collected_fields: CollectedFields = Field(default_factory=CollectedFields)
    recent_messages: list[ConversationMessage] = Field(default_factory=list)


class ChatResponse(BaseModel):
    answer: str
    intent: Intent
    sources: list[SourceItem] = Field(default_factory=list)
    verification_state: VerificationState = Field(default_factory=VerificationState)
    next_action: NextAction
