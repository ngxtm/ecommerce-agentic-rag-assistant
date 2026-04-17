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


class ChatResponse(BaseModel):
    answer: str
    intent: Intent
    sources: list[SourceItem] = Field(default_factory=list)
    verification_state: VerificationState = Field(default_factory=VerificationState)
    next_action: NextAction
