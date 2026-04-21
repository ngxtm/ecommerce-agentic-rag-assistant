from __future__ import annotations

import json
from typing import Any

from app.backend.aws_auth import get_boto3_session
from app.backend.config import get_aws_region, get_order_tool_function_name


class OrderLookupError(RuntimeError):
    pass


def lookup_verified_order(full_name: str, date_of_birth: str, ssn_last4: str) -> dict[str, str] | None:
    function_name = get_order_tool_function_name()
    if not function_name:
        raise OrderLookupError("ORDER_TOOL_FUNCTION_NAME is not configured.")

    region_name = get_aws_region()
    session = get_boto3_session(region_name=region_name)
    client = session.client("lambda", region_name=region_name)
    payload = {
        "full_name": full_name,
        "date_of_birth": date_of_birth,
        "ssn_last4": ssn_last4,
    }

    response = client.invoke(
        FunctionName=function_name,
        InvocationType="RequestResponse",
        Payload=json.dumps(payload).encode("utf-8"),
    )
    status_code = response.get("StatusCode")
    if status_code != 200:
        raise OrderLookupError(f"Order tool invocation failed with status code {status_code}.")

    payload_stream = response.get("Payload")
    if payload_stream is None:
        raise OrderLookupError("Order tool invocation returned no payload.")

    try:
        response_payload = json.loads(payload_stream.read())
    except json.JSONDecodeError as exc:
        raise OrderLookupError("Order tool invocation returned invalid JSON.") from exc

    if not isinstance(response_payload, dict):
        raise OrderLookupError("Order tool invocation returned an unexpected payload.")
    if response_payload.get("found") is True:
        order = response_payload.get("order")
        if not isinstance(order, dict):
            raise OrderLookupError("Order tool payload did not contain a usable order object.")
        normalized_order: dict[str, str] = {}
        for key in ("order_id", "shipment_status", "carrier", "estimated_delivery"):
            value = order.get(key)
            if not isinstance(value, str):
                raise OrderLookupError("Order tool payload contained an invalid order field.")
            normalized_order[key] = value
        return normalized_order
    if response_payload.get("found") is False:
        return None
    raise OrderLookupError("Order tool payload did not contain a valid found flag.")


def build_verified_customer_ref(full_name: str, date_of_birth: str, ssn_last4: str) -> str:
    normalized_full_name = " ".join(full_name.split()).casefold()
    return f"CUSTOMER#{normalized_full_name}#{date_of_birth}#{ssn_last4}"


def build_order_tool_response(order_item: dict[str, Any] | None) -> dict[str, Any]:
    if order_item is None:
        return {"found": False}
    return {
        "found": True,
        "order": {
            "order_id": order_item["order_id"],
            "shipment_status": order_item["shipment_status"],
            "carrier": order_item["carrier"],
            "estimated_delivery": order_item["estimated_delivery"],
        },
    }
