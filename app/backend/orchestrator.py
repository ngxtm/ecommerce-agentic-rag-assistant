import json
import logging
import time

from app.backend.classifier import classify_intent
from app.backend.knowledge_base import CONSERVATIVE_FALLBACK, answer_question
from app.backend.memory_store import session_store
from app.backend.observability import build_log_event, contains_possible_pii
from app.backend.models import ChatRequest, ChatResponse, Intent, NextAction, WorkflowState
from app.backend.order_workflow import handle_order_workflow


logger = logging.getLogger(__name__)


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


def handle_chat(request: ChatRequest) -> ChatResponse:
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
        response, updated_state = handle_order_workflow(request.message, session_state)
        logger.info(
            json.dumps(
                build_log_event(
                    "order_workflow_collecting",
                    session_id=request.session_id,
                    workflow_state=updated_state.workflow_state.value,
                    verification_status=updated_state.verification_state.status.value,
                    missing_fields=updated_state.verification_state.missing_fields,
                )
            )
        )
    else:
        intent = classify_intent(request.message)
        logger.info(json.dumps(build_log_event("intent_classified", session_id=request.session_id, intent=intent.value)))

        if intent is Intent.ORDER_STATUS:
            response, updated_state = handle_order_workflow(request.message, session_state)
            logger.info(
                json.dumps(
                    build_log_event(
                        "order_workflow_collecting",
                        session_id=request.session_id,
                        workflow_state=updated_state.workflow_state.value,
                        verification_status=updated_state.verification_state.status.value,
                        missing_fields=updated_state.verification_state.missing_fields,
                    )
                )
            )
        else:
            answer, sources = answer_question(request.message)
            updated_state = session_state.model_copy(deep=True)
            updated_state.session_id = request.session_id
            updated_state.current_intent = Intent.KNOWLEDGE_QA
            updated_state.workflow_state = WorkflowState.IDLE
            retrieval_refs = _extract_source_ids(sources)
            fallback_used = answer == CONSERVATIVE_FALLBACK or not sources
            response = ChatResponse(
                answer=answer,
                intent=Intent.KNOWLEDGE_QA,
                sources=sources,
                verification_state=updated_state.verification_state,
                next_action=NextAction.RESPOND,
            )
            logger.info(
                json.dumps(
                    build_log_event(
                        "knowledge_query_completed",
                        session_id=request.session_id,
                        success=not fallback_used,
                        fallback_used=fallback_used,
                        retrieval_ref_count=len(retrieval_refs),
                    )
                )
            )

    session_store.save(request.session_id, updated_state)
    assistant_tool_name = None
    assistant_tool_result_summary = None
    assistant_retrieval_refs: list[str] = []

    if response.intent is Intent.KNOWLEDGE_QA:
        assistant_retrieval_refs = _extract_source_ids(response.sources)
    elif _is_order_response_with_tool_summary(response):
        assistant_tool_name = "mock_order_lookup"
        if "could not find a matching order" in response.answer:
            assistant_tool_result_summary = "order_not_found"
            logger.info(json.dumps(build_log_event("order_workflow_not_found", session_id=request.session_id)))
        elif "Your order " in response.answer:
            assistant_tool_result_summary = "order_found"
            logger.info(json.dumps(build_log_event("order_workflow_succeeded", session_id=request.session_id)))

    if response.intent is Intent.ORDER_STATUS and response.next_action is NextAction.ASK_USER:
        logger.info(
            json.dumps(
                build_log_event(
                    "verification_failed",
                    session_id=request.session_id,
                    missing_fields=response.verification_state.missing_fields,
                    verification_status=response.verification_state.status.value,
                )
            )
        )

    session_store.append_message(
        request.session_id,
        "assistant",
        response.answer,
        contains_pii=False,
        retrieval_refs=assistant_retrieval_refs,
        tool_name=assistant_tool_name,
        tool_result_summary=assistant_tool_result_summary,
    )
    logger.info(
        json.dumps(
            build_log_event(
                "chat_orchestration_completed",
                session_id=request.session_id,
                intent=response.intent.value,
                next_action=response.next_action.value,
                latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )
        )
    )
    return response
