from __future__ import annotations

import logging

from botocore.exceptions import BotoCoreError, ClientError

from app.backend.aws_auth import get_boto3_session
from app.backend.config import get_aws_region


logger = logging.getLogger(__name__)
_SECRET_CACHE: dict[str, str] = {}


def get_secret_string(secret_name: str) -> str:
    cached = _SECRET_CACHE.get(secret_name)
    if cached is not None:
        return cached

    region_name = get_aws_region()
    session = get_boto3_session(region_name=region_name)
    client = session.client("secretsmanager", region_name=region_name)

    try:
        response = client.get_secret_value(SecretId=secret_name)
    except (BotoCoreError, ClientError) as exc:
        logger.exception("Failed to retrieve secret '%s' from Secrets Manager.", secret_name)
        raise RuntimeError(f"Failed to retrieve secret '{secret_name}' from Secrets Manager.") from exc

    secret_string = response.get("SecretString")
    if not secret_string:
        raise RuntimeError(f"Secret '{secret_name}' did not contain a usable SecretString value.")

    _SECRET_CACHE[secret_name] = secret_string
    return secret_string


def clear_secret_cache() -> None:
    _SECRET_CACHE.clear()
