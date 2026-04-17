from app.backend.models import ChatRequest, ChatResponse, Intent, NextAction, VerificationState, VerificationStatus


ORDER_KEYWORDS = {
    "order",
    "shipment",
    "shipping status",
    "track",
    "tracking",
    "package",
    "delivery status",
}


def _classify_intent(message: str) -> Intent:
    normalized = message.lower()
    if any(keyword in normalized for keyword in ORDER_KEYWORDS):
        return Intent.ORDER_STATUS
    return Intent.KNOWLEDGE_QA


def handle_chat(request: ChatRequest) -> ChatResponse:
    intent = _classify_intent(request.message)

    if intent is Intent.ORDER_STATUS:
        return ChatResponse(
            answer=(
                "I can help check your order status. Please share your full name, "
                "date of birth in YYYY-MM-DD format, and the last 4 digits of your SSN."
            ),
            intent=intent,
            verification_state=VerificationState(
                status=VerificationStatus.COLLECTING,
                missing_fields=["full_name", "date_of_birth", "ssn_last4"],
                verified_fields=[],
            ),
            next_action=NextAction.ASK_USER,
        )

    return ChatResponse(
        answer=(
            "Phase 0 mock response: knowledge-base routing is wired. "
            "RAG integration will be added in the next phase."
        ),
        intent=intent,
        verification_state=VerificationState(),
        next_action=NextAction.RESPOND,
    )
