from unittest.mock import MagicMock, patch

from app.backend.order_tool_handler import handler


@patch("app.backend.order_tool_handler.get_boto3_session")
@patch("app.backend.order_tool_handler.get_orders_table_name")
def test_order_tool_handler_returns_found_order(mock_table_name, mock_get_boto3_session) -> None:
    mock_table_name.return_value = "orders-dev"
    mock_table = MagicMock()
    mock_table.get_item.return_value = {
        "Item": {
            "order_id": "ORD-1001",
            "shipment_status": "In Transit",
            "carrier": "UPS",
            "estimated_delivery": "2026-04-20",
        }
    }
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table
    mock_session = MagicMock()
    mock_session.resource.return_value = mock_resource
    mock_get_boto3_session.return_value = mock_session

    payload = handler(
        {"full_name": "John Doe", "date_of_birth": "1990-06-15", "ssn_last4": "1234"},
        None,
    )

    assert payload == {
        "found": True,
        "order": {
            "order_id": "ORD-1001",
            "shipment_status": "In Transit",
            "carrier": "UPS",
            "estimated_delivery": "2026-04-20",
        },
    }


@patch("app.backend.order_tool_handler.get_boto3_session")
@patch("app.backend.order_tool_handler.get_orders_table_name")
def test_order_tool_handler_returns_not_found(mock_table_name, mock_get_boto3_session) -> None:
    mock_table_name.return_value = "orders-dev"
    mock_table = MagicMock()
    mock_table.get_item.return_value = {}
    mock_resource = MagicMock()
    mock_resource.Table.return_value = mock_table
    mock_session = MagicMock()
    mock_session.resource.return_value = mock_resource
    mock_get_boto3_session.return_value = mock_session

    payload = handler(
        {"full_name": "John Doe", "date_of_birth": "1990-06-15", "ssn_last4": "1234"},
        None,
    )

    assert payload == {"found": False}
