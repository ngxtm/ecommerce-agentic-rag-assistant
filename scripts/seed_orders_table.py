from __future__ import annotations

import json
from pathlib import Path

from app.backend.aws_auth import get_boto3_session
from app.backend.config import get_aws_region
from app.backend.order_lookup_client import build_verified_customer_ref


ROOT_DIR = Path(__file__).resolve().parents[1]
ORDERS_FILE = ROOT_DIR / "data" / "mock" / "orders.json"


def _load_orders() -> list[dict[str, str]]:
    with ORDERS_FILE.open("r", encoding="utf-8") as file:
        payload = json.load(file)
    if not isinstance(payload, list):
        raise ValueError("orders.json must contain a list of order records.")
    return payload


def seed_orders_table(table_name: str) -> int:
    region_name = get_aws_region()
    session = get_boto3_session(region_name=region_name)
    table = session.resource("dynamodb", region_name=region_name).Table(table_name)
    count = 0

    for order in _load_orders():
        customer_ref = build_verified_customer_ref(order["full_name"], order["dob"], order["ssn_last4"])
        table.put_item(
            Item={
                "pk": customer_ref,
                "sk": "PROFILE",
                "customer_id": order["customer_id"],
                "full_name": order["full_name"],
                "dob": order["dob"],
                "ssn_last4": order["ssn_last4"],
                "order_id": order["order_id"],
                "shipment_status": order["shipment_status"],
                "carrier": order["carrier"],
                "estimated_delivery": order["estimated_delivery"],
            }
        )
        count += 1
    return count


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Seed the Orders DynamoDB table from data/mock/orders.json")
    parser.add_argument("table_name", help="Target DynamoDB orders table name")
    args = parser.parse_args()

    inserted = seed_orders_table(args.table_name)
    print(f"Seeded {inserted} verified order record(s) into {args.table_name}.")
