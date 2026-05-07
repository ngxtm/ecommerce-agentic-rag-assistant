from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.backend.knowledge_base import (  # noqa: E402
    _build_messages,
    _build_sources,
    _classify_question_intent,
    _format_context,
    answer_question,
    generate_grounded_answer,
    retrieve_relevant_chunks,
)


def main() -> None:
    load_dotenv(ROOT_DIR / ".env")
    question = os.getenv("DEBUG_QUESTION", "What does Amazon's business focus on?")
    intent = _classify_question_intent(question)
    chunks = retrieve_relevant_chunks(question)
    production_answer, production_sources = answer_question(question)

    print("MODEL:", os.getenv("LLM_MODEL"))
    print("QUESTION:", question)
    print("INTENT:", intent)
    print("CHUNKS:", [(chunk.title, chunk.section, chunk.score) for chunk in chunks])
    print("SOURCES:", json.dumps([source.model_dump() for source in _build_sources(chunks, active_question=question)], indent=2))
    print("MESSAGES:", json.dumps(_build_messages(question, _format_context(chunks)), indent=2))
    answer = generate_grounded_answer(question, chunks)
    print("ANSWER_FROM_CHUNKS:", answer)
    print(
        "PRODUCTION_OUTPUT:",
        json.dumps(
            {
                "answer": production_answer,
                "sources": [source.model_dump() for source in production_sources],
            },
            indent=2,
        ),
    )


if __name__ == "__main__":
    main()
