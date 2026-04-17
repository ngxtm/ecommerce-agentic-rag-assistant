import logging
import time
import uuid

from fastapi import FastAPI

from app.backend.models import ChatRequest, ChatResponse
from app.backend.orchestrator import handle_chat


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agentic Commerce Assistant API", version="0.1.0")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    request_id = str(uuid.uuid4())
    started_at = time.perf_counter()

    response = handle_chat(request)

    latency_ms = round((time.perf_counter() - started_at) * 1000, 2)
    logger.info(
        "chat_request request_id=%s session_id=%s intent=%s next_action=%s latency_ms=%s",
        request_id,
        request.session_id,
        response.intent.value,
        response.next_action.value,
        latency_ms,
    )
    return response
