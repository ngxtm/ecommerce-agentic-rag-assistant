import logging
import json
import os
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from dotenv import load_dotenv

from app.backend.config import get_aws_region
from app.backend.observability import build_log_event
from app.backend.models import ChatRequest, ChatResponse


ROOT_DIR = Path(__file__).resolve().parents[2]
load_dotenv(ROOT_DIR / ".env")

from app.backend.orchestrator import StreamingIntentError, ensure_streaming_allowed, handle_chat, stream_chat


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Agentic Commerce Assistant API", version="0.1.0")

logger.info(
    json.dumps(
        build_log_event(
            "app_config_loaded",
            app_env=os.getenv("APP_ENV", "unknown"),
            memory_backend=os.getenv("MEMORY_BACKEND", "inmemory"),
            dynamodb_conversation_table=os.getenv("DYNAMODB_CONVERSATION_TABLE"),
            aws_region=get_aws_region(),
        )
    )
)


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
        json.dumps(
            build_log_event(
                "chat_request_completed",
                request_id=request_id,
                session_id=request.session_id,
                intent=response.intent.value,
                next_action=response.next_action.value,
                latency_ms=latency_ms,
            )
        )
    )
    return response


@app.post("/chat/stream")
def chat_stream(request: ChatRequest) -> StreamingResponse:
    try:
        ensure_streaming_allowed(request)
    except StreamingIntentError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return StreamingResponse(stream_chat(request), media_type="text/event-stream")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
