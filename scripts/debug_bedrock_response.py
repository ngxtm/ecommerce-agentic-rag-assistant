from __future__ import annotations

import json
import os
import sys
import traceback
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.backend.knowledge_base import (  # noqa: E402
    _build_messages,
    _format_context,
    _get_bedrock_runtime_client,
    retrieve_relevant_chunks,
)


def main() -> None:
    load_dotenv(ROOT_DIR / ".env")
    question = "What is the return window for most items?"
    chunks = retrieve_relevant_chunks(question)
    print("MODEL:", os.getenv("BEDROCK_INFERENCE_PROFILE_ID") or os.getenv("BEDROCK_MODEL_ID"))
    print("CHUNKS:", [(chunk.title, chunk.section, chunk.score) for chunk in chunks])

    client = _get_bedrock_runtime_client()
    try:
        response = client.converse(
            modelId=os.getenv("BEDROCK_INFERENCE_PROFILE_ID") or os.getenv("BEDROCK_MODEL_ID"),
            system=[
                {
                    "text": (
                        "You are a customer support knowledge assistant. Only answer using the supplied context. "
                        "If the context is insufficient, explicitly say you do not have enough grounded context."
                    )
                }
            ],
            messages=_build_messages(question, _format_context(chunks)),
            inferenceConfig={"maxTokens": 350, "temperature": 0},
        )
        print(json.dumps(response, default=str, indent=2))
    except Exception as exc:  # pragma: no cover - diagnostics only
        print(type(exc).__name__)
        print(exc)
        traceback.print_exc()


if __name__ == "__main__":
    main()
