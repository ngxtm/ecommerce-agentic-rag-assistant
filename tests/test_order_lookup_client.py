import io
import json
from unittest.mock import MagicMock, patch

from app.backend.order_lookup_client import OrderLookupError, build_verified_customer_ref, lookup_verified_order


def test_build_verified_customer_ref_normalizes_name() -> None:
    assert build_verified_customer_ref(" John   Doe ", "1990-06-15", "1234") == "CUSTOMER#john doe#1990-06-15#1234"


@patch("app.backend.order_lookup_client.get_boto3_session")
@patch("app.backend.order_lookup_client.get_order_tool_function_name")
def test_lookup_verified_order_returns_order_payload(mock_function_name, mock_get_boto3_session) -> None:
    mock_function_name.return_value = "order-tool-dev"
    mock_client = MagicMock()
    mock_client.invoke.return_value = {
        "StatusCode": 200,
        "Payload": io.BytesIO(
            json.dumps(
                {
                    "found": True,
                    "order": {
                        "order_id": "ORD-1001",
                        "shipment_status": "In Transit",
                        "carrier": "UPS",
                        "estimated_delivery": "2026-04-20",
                    },
                }
            ).encode("utf-8")
        ),
    }
    mock_session = MagicMock()
    mock_session.client.return_value = mock_client
    mock_get_boto3_session.return_value = mock_session

    order = lookup_verified_order("John Doe", "1990-06-15", "1234")

    assert order == {
        "order_id": "ORD-1001",
        "shipment_status": "In Transit",
        "carrier": "UPS",
        "estimated_delivery": "2026-04-20",
    }


@patch("app.backend.order_lookup_client.get_boto3_session")
@patch("app.backend.order_lookup_client.get_order_tool_function_name")
def test_lookup_verified_order_returns_none_when_not_found(mock_function_name, mock_get_boto3_session) -> None:
    mock_function_name.return_value = "order-tool-dev"
    mock_client = MagicMock()
    mock_client.invoke.return_value = {
        "StatusCode": 200,
        "Payload": io.BytesIO(json.dumps({"found": False}).encode("utf-8")),
    }
    mock_session = MagicMock()
    mock_session.client.return_value = mock_client
    mock_get_boto3_session.return_value = mock_session

    assert lookup_verified_order("John Doe", "1990-06-15", "1234") is None


@patch("app.backend.order_lookup_client.get_order_tool_function_name")
def test_lookup_verified_order_raises_when_tool_name_missing(mock_function_name) -> None:
    mock_function_name.return_value = None

    try:
        lookup_verified_order("John Doe", "1990-06-15", "1234")
    except OrderLookupError as exc:
        assert "ORDER_TOOL_FUNCTION_NAME" in str(exc)
    else:
        raise AssertionError("Expected OrderLookupError when tool function name is missing.")
