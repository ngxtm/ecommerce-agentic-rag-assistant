from __future__ import annotations

import re

from app.backend.order_lookup_client import OrderLookupError, build_verified_customer_ref, lookup_verified_order
from app.backend.models import (
    ChatResponse,
    CollectedFields,
    Intent,
    NextAction,
    SessionState,
    VerificationState,
    VerificationStatus,
    WorkflowState,
)
from app.backend.validators import validate_date_of_birth, validate_full_name, validate_ssn_last4


FIELD_ORDER = ("full_name", "date_of_birth", "ssn_last4")
FIELD_PROMPTS = {
    "full_name": "Please share your full name.",
    "date_of_birth": "Please share your date of birth in DD-MM-YYYY format.",
    "ssn_last4": "Please share the last 4 digits of your SSN.",
}


def _extract_full_name(message: str) -> str | None:
    patterns = (
        r"(?:my name is|i am|this is)\s+([A-Za-z]+(?:\s+[A-Za-z]+)+)",
        r"^([A-Za-z]+(?:\s+[A-Za-z]+)+)$",
    )
    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return None


def _extract_date_of_birth(message: str) -> str | None:
    match = re.search(r"\b(\d{2}-\d{2}-\d{4})\b", message)
    return match.group(1) if match else None


def _extract_invalid_date_of_birth(message: str) -> str | None:
    match = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", message)
    return match.group(1) if match else None


def _extract_ssn_last4(message: str) -> str | None:
    if re.fullmatch(r"\s*\d{4}\s*", message):
        return message.strip()

    match = re.search(r"(?:ssn|last\s*4|last\s*four)[^\d]*(\d{4})", message, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _update_verification_state(collected_fields: CollectedFields) -> VerificationState:
    missing_fields = [field for field in FIELD_ORDER if getattr(collected_fields, field) is None]
    verified_fields = [field for field in FIELD_ORDER if getattr(collected_fields, field) is not None]
    status = VerificationStatus.VERIFIED if not missing_fields else VerificationStatus.COLLECTING
    return VerificationState(
        status=status,
        missing_fields=missing_fields,
        verified_fields=verified_fields,
    )


def _build_missing_field_prompt(verification_state: VerificationState) -> str:
    first_missing = verification_state.missing_fields[0]
    intro = "I can help check your order status, but I need to verify your identity first."
    return f"{intro} {FIELD_PROMPTS[first_missing]}"


def _apply_extracted_fields(message: str, collected_fields: CollectedFields) -> tuple[CollectedFields, list[str]]:
    updated = collected_fields.model_copy(deep=True)
    validation_errors: list[str] = []

    full_name = _extract_full_name(message)
    if full_name and updated.full_name is None:
        result = validate_full_name(full_name)
        if result.is_valid:
            updated.full_name = result.normalized_value
        else:
            validation_errors.append(result.error_message or FIELD_PROMPTS["full_name"])

    date_of_birth = _extract_date_of_birth(message)
    if date_of_birth and updated.date_of_birth is None:
        result = validate_date_of_birth(date_of_birth)
        if result.is_valid:
            updated.date_of_birth = result.normalized_value
        else:
            validation_errors.append(result.error_message or FIELD_PROMPTS["date_of_birth"])
    elif updated.date_of_birth is None:
        invalid_date_of_birth = _extract_invalid_date_of_birth(message)
        if invalid_date_of_birth:
            validation_errors.append("Please provide your date of birth in DD-MM-YYYY format.")

    ssn_last4 = _extract_ssn_last4(message)
    if ssn_last4 and updated.ssn_last4 is None:
        result = validate_ssn_last4(ssn_last4)
        if result.is_valid:
            updated.ssn_last4 = result.normalized_value
        else:
            validation_errors.append(result.error_message or FIELD_PROMPTS["ssn_last4"])

    return updated, validation_errors


def handle_order_workflow(message: str, session_state: SessionState) -> tuple[ChatResponse, SessionState]:
    updated_state = session_state.model_copy(deep=True)
    updated_state.current_intent = Intent.ORDER_STATUS
    updated_state.workflow_state = WorkflowState.COLLECTING_ORDER_VERIFICATION

    collected_fields, validation_errors = _apply_extracted_fields(message, updated_state.collected_fields)
    updated_state.collected_fields = collected_fields
    updated_state.verification_state = _update_verification_state(collected_fields)

    if validation_errors:
        answer = f"{validation_errors[0]} {FIELD_PROMPTS[updated_state.verification_state.missing_fields[0]]}"
        return (
            ChatResponse(
                answer=answer,
                intent=Intent.ORDER_STATUS,
                verification_state=updated_state.verification_state,
                next_action=NextAction.ASK_USER,
            ),
            updated_state,
        )

    if updated_state.verification_state.missing_fields:
        return (
            ChatResponse(
                answer=_build_missing_field_prompt(updated_state.verification_state),
                intent=Intent.ORDER_STATUS,
                verification_state=updated_state.verification_state,
                next_action=NextAction.ASK_USER,
            ),
            updated_state,
        )

    updated_state.workflow_state = WorkflowState.ORDER_VERIFIED
    updated_state.verified_customer_ref = build_verified_customer_ref(
        updated_state.collected_fields.full_name,
        updated_state.collected_fields.date_of_birth,
        updated_state.collected_fields.ssn_last4,
    )
    try:
        order = lookup_verified_order(
            updated_state.collected_fields.full_name,
            updated_state.collected_fields.date_of_birth,
            updated_state.collected_fields.ssn_last4,
        )
    except OrderLookupError:
        updated_state.workflow_state = WorkflowState.ORDER_COMPLETED
        answer = (
            "I verified your details, but I could not complete the order lookup right now. "
            "Please try again shortly."
        )
        return (
            ChatResponse(
                answer=answer,
                intent=Intent.ORDER_STATUS,
                verification_state=updated_state.verification_state,
                next_action=NextAction.RESPOND,
            ),
            updated_state,
        )
    updated_state.workflow_state = WorkflowState.ORDER_COMPLETED

    if order is None:
        answer = (
            "I could not find a matching order with the verified details provided. "
            "Please confirm your full name, date of birth, and last 4 digits of your SSN."
        )
        return (
            ChatResponse(
                answer=answer,
                intent=Intent.ORDER_STATUS,
                verification_state=updated_state.verification_state,
                next_action=NextAction.RESPOND,
            ),
            updated_state,
        )

    answer = (
        f"Your order {order['order_id']} is currently {order['shipment_status']} via {order['carrier']}. "
        f"Estimated delivery is {order['estimated_delivery']}."
    )
    return (
        ChatResponse(
            answer=answer,
            intent=Intent.ORDER_STATUS,
            verification_state=updated_state.verification_state,
            next_action=NextAction.RESPOND,
        ),
        updated_state,
    )
