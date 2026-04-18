from __future__ import annotations

import os


def get_aws_region() -> str | None:
    return os.getenv("AWS_REGION") or os.getenv("AWS_DEFAULT_REGION") or os.getenv("AMAZON_REGION")
