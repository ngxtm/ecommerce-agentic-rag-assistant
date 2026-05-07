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
    _build_sources,
    _classify_question_intent,
    answer_question,
    retrieve_relevant_chunks,
)


BENCHMARK_QUESTIONS = [
    "What does Amazon's business focus on?",
    "What facilities did Amazon operate?",
    "Were there any legal proceedings?",
    "Who are the Executive Officers and Directors?",
    "Who is Andrew R. Jassy?",
    "Selected Consolidated Financial Data",
    "What were net sales in 2019?",
    "The Loss of Key Senior Management Personnel or the Inability to Hire and Retain Qualified Personnel Could Harm Our Business",
]


def _serialize_chunk(chunk: object) -> dict[str, object]:
    return {
        "chunk_id": getattr(chunk, "chunk_id", None),
        "score": round(float(getattr(chunk, "score", 0.0)), 4),
        "lexical_score": round(float(getattr(chunk, "lexical_score", 0.0)), 4),
        "vector_score": round(float(getattr(chunk, "vector_score", 0.0)), 4),
        "section": getattr(chunk, "section", None),
        "item": getattr(chunk, "item", None),
        "subsection": getattr(chunk, "subsection", None),
        "subsubsection": getattr(chunk, "subsubsection", None),
        "content_type": getattr(chunk, "content_type", None),
        "table_name": getattr(chunk, "table_name", None),
        "metric": getattr(chunk, "metric", None),
        "year": getattr(chunk, "year", None),
        "entity_name": getattr(chunk, "entity_name", None),
        "entity_role": getattr(chunk, "entity_role", None),
        "page_start": getattr(chunk, "page_start", None),
        "page_end": getattr(chunk, "page_end", None),
        "content_preview": getattr(chunk, "content", "")[:260],
    }


def _run_question(question: str) -> dict[str, object]:
    intent = _classify_question_intent(question)
    retrieval_k = 8 if intent == "entity_lookup" and question.casefold().startswith("who are ") else 4
    chunks = retrieve_relevant_chunks(question, top_k=retrieval_k)
    provisional_sources = [source.model_dump() for source in _build_sources(chunks, active_question=question)]
    answer, final_sources = answer_question(question)
    return {
        "question": question,
        "intent": intent,
        "retrieval_k": retrieval_k,
        "fallback": not bool(final_sources),
        "answer": answer,
        "retrieved_chunks": [_serialize_chunk(chunk) for chunk in chunks],
        "provisional_sources": provisional_sources,
        "final_sources": [source.model_dump() for source in final_sources],
    }


def main() -> None:
    load_dotenv(ROOT_DIR / ".env")
    output_path = ROOT_DIR / "artifacts" / "round3_benchmark.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    results = {
        "llm_model": os.getenv("LLM_MODEL"),
        "opensearch_index": os.getenv("OPENSEARCH_INDEX_NAME"),
        "questions": [],
    }
    for question in BENCHMARK_QUESTIONS:
        results["questions"].append(_run_question(question))

    output_path.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"Wrote benchmark results to {output_path}")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
