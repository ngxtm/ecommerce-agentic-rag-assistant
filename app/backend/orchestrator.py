import json
import logging
import time
from collections.abc import Iterator

from app.backend.classifier import classify_intent
from app.backend.knowledge_base import CONSERVATIVE_FALLBACK, answer_question, stream_answer_question
from app.backend.memory_store import session_store
from app.backend.observability import build_log_event, contains_possible_pii
from app.backend.models import ChatRequest, ChatResponse, Intent, NextAction, WorkflowState
from app.backend.order_workflow import handle_order_workflow


logger = logging.getLogger(__name__)
EVENT_VERSION = 1
STREAMING_NOT_AVAILABLE_FOR_ORDER_STATUS = "Streaming is only available for knowledge questions."


class StreamingIntentError(RuntimeError):
    pass


def _is_order_response_with_tool_summary(response: ChatResponse) -> bool:
    return response.intent is Intent.ORDER_STATUS and response.next_action is NextAction.RESPOND


def _extract_source_ids(sources: list) -> list[str]:
    source_ids: list[str] = []
    for source in sources:
        if hasattr(source, "source_id"):
            source_ids.append(source.source_id)
        elif isinstance(source, dict) and source.get("source_id"):
            source_ids.append(str(source["source_id"]))
    return source_ids


def _sse_event(event_type: str, data: dict[str, object]) -> str:
    payload = {"event_version": EVENT_VERSION, **data}
    return f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"


def _persist_knowledge_response(session_id: str, answer: str, sources: list, session_state) -> None:
    updated_state = session_state.model_copy(deep=True)
    updated_state.session_id = session_id
    updated_state.current_intent = Intent.KNOWLEDGE_QA
    updated_state.workflow_state = WorkflowState.IDLE
    retrieval_refs = _extract_source_ids(sources)
    fallback_used = answer == CONSERVATIVE_FALLBACK or not sources
    logger.info(
        json.dumps(
            build_log_event(
                "knowledge_query_completed",
                session_id=session_id,
                success=not fallback_used,
                fallback_used=fallback_used,
                retrieval_ref_count=len(retrieval_refs),
            )
        )
    )
    session_store.save(session_id, updated_state)
    session_store.append_message(
        session_id,
        "assistant",
        answer,
        contains_pii=False,
        retrieval_refs=retrieval_refs,
    )


def _append_order_response_observability(request: ChatRequest, response: ChatResponse, request_id: str | None = None) -> None:
    if response.intent is Intent.ORDER_STATUS and response.next_action is NextAction.ASK_USER:
        logger.info(
            json.dumps(
                build_log_event(
                    "verification_failed",
                    request_id=request_id,
                    session_id=request.session_id,
                    missing_fields=response.verification_state.missing_fields,
                    verification_status=response.verification_state.status.value,
                )
            )
        )


def _append_assistant_message(request: ChatRequest, response: ChatResponse, request_id: str | None = None) -> None:
    assistant_tool_name = None
    assistant_tool_result_summary = None
    assistant_retrieval_refs: list[str] = []

    if response.intent is Intent.KNOWLEDGE_QA:
        assistant_retrieval_refs = _extract_source_ids(response.sources)
    elif _is_order_response_with_tool_summary(response):
        assistant_tool_name = "order_status_tool"
        if "could not find a matching order" in response.answer:
            assistant_tool_result_summary = "order_not_found"
            logger.info(
                json.dumps(
                    build_log_event(
                        "order_workflow_not_found",
                        request_id=request_id,
                        session_id=request.session_id,
                        tool_name=assistant_tool_name,
                        tool_result_summary=assistant_tool_result_summary,
                    )
                )
            )
        elif "I verified your details, but I could not complete the order lookup right now." in response.answer:
            assistant_tool_result_summary = "lookup_failed"
            logger.info(
                json.dumps(
                    build_log_event(
                        "order_workflow_lookup_failed",
                        request_id=request_id,
                        session_id=request.session_id,
                        tool_name=assistant_tool_name,
                        tool_result_summary=assistant_tool_result_summary,
                    )
                )
            )
        elif "Your order " in response.answer:
            assistant_tool_result_summary = "order_found"
            logger.info(
                json.dumps(
                    build_log_event(
                        "order_workflow_succeeded",
                        request_id=request_id,
                        session_id=request.session_id,
                        tool_name=assistant_tool_name,
                        tool_result_summary=assistant_tool_result_summary,
                    )
                )
            )

    _append_order_response_observability(request, response, request_id=request_id)
    session_store.append_message(
        request.session_id,
        "assistant",
        response.answer,
        contains_pii=False,
        retrieval_refs=assistant_retrieval_refs,
        tool_name=assistant_tool_name,
        tool_result_summary=assistant_tool_result_summary,
    )


def _log_order_collecting(request: ChatRequest, updated_state, request_id: str | None = None) -> None:
    logger.info(
        json.dumps(
            build_log_event(
                "order_workflow_collecting",
                request_id=request_id,
                session_id=request.session_id,
                workflow_state=updated_state.workflow_state.value,
                verification_status=updated_state.verification_state.status.value,
                missing_fields=updated_state.verification_state.missing_fields,
            )
        )
    )


def _handle_order_chat(request: ChatRequest, session_state, request_id: str | None = None) -> ChatResponse:
    response, updated_state = handle_order_workflow(request.message, session_state)
    _log_order_collecting(request, updated_state, request_id=request_id)
    session_store.save(request.session_id, updated_state)
    _append_assistant_message(request, response, request_id=request_id)
    return response


def _handle_knowledge_chat(request: ChatRequest, session_state) -> ChatResponse:
    answer, sources = answer_question(request.message)
    _persist_knowledge_response(request.session_id, answer, sources, session_state)
    return ChatResponse(
        answer=answer,
        intent=Intent.KNOWLEDGE_QA,
        sources=sources,
        verification_state=session_state.verification_state,
        next_action=NextAction.RESPOND,
    )


def handle_chat(request: ChatRequest, request_id: str | None = None) -> ChatResponse:
    started_at = time.perf_counter()
    session_state = session_store.load(request.session_id)
    session_state.session_id = request.session_id
    user_contains_pii = (
        session_state.workflow_state is WorkflowState.COLLECTING_ORDER_VERIFICATION
        or contains_possible_pii(request.message)
    )
    session_state = session_store.append_message(
        request.session_id,
        "user",
        request.message,
        contains_pii=user_contains_pii,
    )

    if session_state.workflow_state is WorkflowState.COLLECTING_ORDER_VERIFICATION:
        response = _handle_order_chat(request, session_state, request_id=request_id)
    else:
        intent = classify_intent(request.message)
        logger.info(
            json.dumps(
                build_log_event(
                    "intent_classified",
                    request_id=request_id,
                    session_id=request.session_id,
                    intent=intent.value,
                )
            )
        )
        if intent is Intent.ORDER_STATUS:
            response = _handle_order_chat(request, session_state, request_id=request_id)
        else:
            response = _handle_knowledge_chat(request, session_state)

    logger.info(
        json.dumps(
            build_log_event(
                "chat_orchestration_completed",
                request_id=request_id,
                session_id=request.session_id,
                intent=response.intent.value,
                next_action=response.next_action.value,
                latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )
        )
    )
    return response


def ensure_streaming_allowed(request: ChatRequest) -> None:
    session_state = session_store.load(request.session_id)
    if session_state.workflow_state is WorkflowState.COLLECTING_ORDER_VERIFICATION:
        raise StreamingIntentError(STREAMING_NOT_AVAILABLE_FOR_ORDER_STATUS)
    intent = classify_intent(request.message)
    if intent is Intent.ORDER_STATUS:
        raise StreamingIntentError(STREAMING_NOT_AVAILABLE_FOR_ORDER_STATUS)


def stream_chat(request: ChatRequest, request_id: str | None = None) -> Iterator[str]:
    session_state = session_store.load(request.session_id)
    session_state.session_id = request.session_id
    user_contains_pii = (
        session_state.workflow_state is WorkflowState.COLLECTING_ORDER_VERIFICATION
        or contains_possible_pii(request.message)
    )
    session_state = session_store.append_message(
        request.session_id,
        "user",
        request.message,
        contains_pii=user_contains_pii,
    )

    intent = classify_intent(request.message)
    logger.info(
        json.dumps(
            build_log_event(
                "intent_classified",
                request_id=request_id,
                session_id=request.session_id,
                intent=intent.value,
            )
        )
    )

    full_answer_parts: list[str] = []
    try:
        answer_stream, sources = stream_answer_question(request.message)
        for chunk in answer_stream:
            if not chunk:
                continue
            full_answer_parts.append(chunk)
            yield _sse_event("delta", {"delta": chunk})
        full_answer = "".join(full_answer_parts).strip() or CONSERVATIVE_FALLBACK
        _persist_knowledge_response(request.session_id, full_answer, sources, session_state)
        yield _sse_event(
            "final",
            {
                "full_answer": full_answer,
                "sources": [source.model_dump() if hasattr(source, "model_dump") else source for source in sources],
                "session_update_status": "committed",
            },
        )
    except Exception:
        logger.info(
            json.dumps(
                build_log_event(
                    "knowledge_stream_failed",
                    request_id=request_id,
                    session_id=request.session_id,
                    partial_chars=len("".join(full_answer_parts)),
                )
            )
        )
        yield _sse_event(
            "error",
            {
                "message": "Knowledge answer streaming failed before completion.",
                "session_update_status": "not_committed",
            },
        )
