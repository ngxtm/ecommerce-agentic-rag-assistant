from app.backend.classifier import classify_intent
from app.backend.knowledge_base import answer_question
from app.backend.memory_store import session_store
from app.backend.models import ChatRequest, ChatResponse, Intent, NextAction, WorkflowState
from app.backend.order_workflow import handle_order_workflow


def handle_chat(request: ChatRequest) -> ChatResponse:
    session_state = session_store.load(request.session_id)
    session_state = session_store.append_message(request.session_id, "user", request.message)

    if session_state.workflow_state is WorkflowState.COLLECTING_ORDER_VERIFICATION:
        response, updated_state = handle_order_workflow(request.message, session_state)
    else:
        intent = classify_intent(request.message)

        if intent is Intent.ORDER_STATUS:
            response, updated_state = handle_order_workflow(request.message, session_state)
        else:
            answer, sources = answer_question(request.message)
            updated_state = session_state.model_copy(deep=True)
            updated_state.current_intent = Intent.KNOWLEDGE_QA
            updated_state.workflow_state = WorkflowState.IDLE
            response = ChatResponse(
                answer=answer,
                intent=Intent.KNOWLEDGE_QA,
                sources=sources,
                verification_state=updated_state.verification_state,
                next_action=NextAction.RESPOND,
            )

    session_store.save(request.session_id, updated_state)
    session_store.append_message(request.session_id, "assistant", response.answer)
    return response
