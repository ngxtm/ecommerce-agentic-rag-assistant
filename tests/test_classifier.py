from app.backend.classifier import classify_intent
from app.backend.models import Intent


def test_classify_order_status_intent() -> None:
    assert classify_intent("Where is my order?") is Intent.ORDER_STATUS


def test_classify_knowledge_intent_by_default() -> None:
    assert classify_intent("What is the return policy?") is Intent.KNOWLEDGE_QA
