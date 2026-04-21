from __future__ import annotations

import json
import logging
import time
from typing import Any

from app.backend.aws_auth import get_boto3_session
from app.backend.config import get_aws_region, get_orders_table_name
from app.backend.observability import build_log_event
from app.backend.order_lookup_client import build_order_tool_response, build_verified_customer_ref


logger = logging.getLogger(__name__)


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    started_at = time.perf_counter()
    full_name = str(event.get("full_name", "")).strip()
    date_of_birth = str(event.get("date_of_birth", "")).strip()
    ssn_last4 = str(event.get("ssn_last4", "")).strip()
    if not full_name or not date_of_birth or not ssn_last4:
        raise ValueError("full_name, date_of_birth, and ssn_last4 are required.")

    table_name = get_orders_table_name()
    if not table_name:
        raise ValueError("ORDERS_TABLE_NAME is not configured.")

    customer_ref = build_verified_customer_ref(full_name, date_of_birth, ssn_last4)
    region_name = get_aws_region()
    session = get_boto3_session(region_name=region_name)
    table = session.resource("dynamodb", region_name=region_name).Table(table_name)
    response = table.get_item(Key={"pk": customer_ref, "sk": "PROFILE"})
    order_item = response.get("Item")
    logger.info(
        json.dumps(
            build_log_event(
                "order_tool_lookup_completed",
                customer_ref=customer_ref,
                found=order_item is not None,
                latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )
        )
    )
    return build_order_tool_response(order_item)
