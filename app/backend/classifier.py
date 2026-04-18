from app.backend.models import Intent


ORDER_KEYWORDS = (
    "order",
    "shipment",
    "shipping status",
    "track",
    "tracking",
    "package",
    "delivery status",
    "where is my package",
)


def classify_intent(message: str) -> Intent:
    normalized = message.lower()
    if any(keyword in normalized for keyword in ORDER_KEYWORDS):
        return Intent.ORDER_STATUS
    return Intent.KNOWLEDGE_QA
