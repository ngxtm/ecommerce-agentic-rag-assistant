from __future__ import annotations

import os


def get_aws_region() -> str | None:
    return os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or os.getenv("AMAZON_REGION")


def get_order_tool_function_name() -> str | None:
    return os.getenv("ORDER_TOOL_FUNCTION_NAME")


def get_orders_table_name() -> str | None:
    return os.getenv("ORDERS_TABLE_NAME")


def get_llm_api_key_secret_name() -> str | None:
    return os.getenv("LLM_API_KEY_SECRET_NAME")

def get_llm_embedding_api_key_secret_name() -> str | None:
    return os.getenv("LLM_EMBEDDING_API_KEY_SECRET_NAME") or os.getenv("LLM_API_KEY_SECRET_NAME")
