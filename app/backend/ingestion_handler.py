from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import unquote_plus

from botocore.exceptions import ClientError

from app.backend.aws_auth import get_boto3_session
from app.backend.config import get_aws_region
from app.backend.observability import build_log_event
from scripts.index_sample_docs import index_documents_for_paths


logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

PROCESSING_STATUS = "processing"
COMPLETED_STATUS = "completed"
FAILED_STATUS = "failed"
DEFAULT_STATE_TTL_DAYS = 30
DEFAULT_PROCESSING_TIMEOUT_SECONDS = 900


@dataclass(frozen=True)
class S3DocumentEvent:
    bucket: str
    key: str
    version_id: str
    etag: str | None

    @property
    def pk(self) -> str:
        return f"OBJECT#{self.bucket}#{self.key}"

    @property
    def sk(self) -> str:
        return f"VERSION#{self.version_id}"

    @property
    def source_uri(self) -> str:
        return f"s3://{self.bucket}/{self.key}"


def _get_required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise ValueError(f"{name} is not configured.")
    return value


def _ttl_epoch(days: int) -> int:
    return int((datetime.now(UTC) + timedelta(days=days)).timestamp())


def _build_s3_client(region_name: str | None = None):
    session = get_boto3_session(region_name=region_name)
    return session.client("s3", region_name=region_name)


def _build_state_table(region_name: str | None = None):
    session = get_boto3_session(region_name=region_name)
    table_name = _get_required_env("INGESTION_STATE_TABLE_NAME")
    return session.resource("dynamodb", region_name=region_name).Table(table_name)


def _parse_s3_events(event: dict[str, Any]) -> list[S3DocumentEvent]:
    parsed: list[S3DocumentEvent] = []
    for record in event.get("Records", []):
        s3_record = record.get("s3", {})
        bucket = str(s3_record.get("bucket", {}).get("name", "")).strip()
        key = unquote_plus(str(s3_record.get("object", {}).get("key", "")).strip())
        version_id = str(s3_record.get("object", {}).get("versionId") or s3_record.get("object", {}).get("sequencer") or "null")
        etag = s3_record.get("object", {}).get("eTag")
        if not bucket or not key:
            continue
        parsed.append(S3DocumentEvent(bucket=bucket, key=key, version_id=version_id, etag=str(etag) if etag else None))
    return parsed


def _is_completed(table, document_event: S3DocumentEvent) -> bool:
    response = table.get_item(Key={"pk": document_event.pk, "sk": document_event.sk})
    item = response.get("Item") or {}
    return item.get("status") == COMPLETED_STATUS


def _parse_iso8601(timestamp: str | None) -> datetime | None:
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def _is_processing_stale(item: dict[str, Any]) -> bool:
    started_at = _parse_iso8601(str(item.get("started_at") or ""))
    if started_at is None:
        return True
    timeout_seconds = int(os.getenv("INGESTION_PROCESSING_TIMEOUT_SECONDS", str(DEFAULT_PROCESSING_TIMEOUT_SECONDS)))
    return datetime.now(UTC) - started_at > timedelta(seconds=timeout_seconds)


def _mark_processing(table, document_event: S3DocumentEvent) -> None:
    now = datetime.now(UTC).isoformat()
    item = {
        "pk": document_event.pk,
        "sk": document_event.sk,
        "bucket": document_event.bucket,
        "object_key": document_event.key,
        "version_id": document_event.version_id,
        "etag": document_event.etag,
        "source_uri": document_event.source_uri,
        "status": PROCESSING_STATUS,
        "started_at": now,
        "ttl": _ttl_epoch(int(os.getenv("INGESTION_STATE_TTL_DAYS", str(DEFAULT_STATE_TTL_DAYS)))),
    }
    try:
        table.put_item(
            Item=item,
            ConditionExpression="attribute_not_exists(pk) AND attribute_not_exists(sk)",
        )
        return
    except ClientError as exc:
        error_code = exc.response.get("Error", {}).get("Code")
        if error_code != "ConditionalCheckFailedException":
            raise

    existing = table.get_item(Key={"pk": document_event.pk, "sk": document_event.sk}).get("Item") or {}
    existing_status = existing.get("status")
    if existing_status == COMPLETED_STATUS:
        raise RuntimeError("ingestion_already_completed")
    if existing_status == PROCESSING_STATUS and not _is_processing_stale(existing):
        raise RuntimeError("ingestion_already_processing")

    logger.info(
        json.dumps(
            build_log_event(
                "ingestion_stale_reclaimed",
                source_uri=document_event.source_uri,
                previous_status=existing_status,
                previous_started_at=existing.get("started_at"),
            )
        )
    )

    table.update_item(
        Key={"pk": document_event.pk, "sk": document_event.sk},
        UpdateExpression="SET #status = :status, started_at = :started_at, #ttl = :ttl REMOVE error_message, completed_at, indexed_doc_count",
        ConditionExpression="#status = :failed_status OR #status = :processing_status",
        ExpressionAttributeNames={"#status": "status", "#ttl": "ttl"},
        ExpressionAttributeValues={
            ":status": PROCESSING_STATUS,
            ":started_at": now,
            ":ttl": item["ttl"],
            ":failed_status": FAILED_STATUS,
            ":processing_status": PROCESSING_STATUS,
        },
    )


def _update_status(table, document_event: S3DocumentEvent, status: str, *, indexed_doc_count: int | None = None, error_message: str | None = None) -> None:
    expression_values: dict[str, Any] = {
        ":status": status,
        ":updated_at": datetime.now(UTC).isoformat(),
    }
    update_parts = ["#status = :status", "updated_at = :updated_at"]

    if status == COMPLETED_STATUS:
        update_parts.append("completed_at = :updated_at")
    if indexed_doc_count is not None:
        expression_values[":indexed_doc_count"] = indexed_doc_count
        update_parts.append("indexed_doc_count = :indexed_doc_count")
    if error_message is not None:
        expression_values[":error_message"] = error_message[:1000]
        update_parts.append("error_message = :error_message")

    table.update_item(
        Key={"pk": document_event.pk, "sk": document_event.sk},
        UpdateExpression=f"SET {', '.join(update_parts)}",
        ExpressionAttributeNames={"#status": "status"},
        ExpressionAttributeValues=expression_values,
    )


def _download_s3_object(document_event: S3DocumentEvent, destination: Path, *, region_name: str | None = None) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    _build_s3_client(region_name=region_name).download_file(document_event.bucket, document_event.key, str(destination))


def _process_record(document_event: S3DocumentEvent, *, region_name: str | None = None) -> dict[str, Any]:
    table = _build_state_table(region_name=region_name)
    if _is_completed(table, document_event):
        return {"source_uri": document_event.source_uri, "status": "skipped_completed"}

    try:
        _mark_processing(table, document_event)
    except RuntimeError as exc:
        if str(exc) == "ingestion_already_completed":
            logger.info(json.dumps(build_log_event("ingestion_skipped_completed", source_uri=document_event.source_uri)))
            return {"source_uri": document_event.source_uri, "status": "skipped_completed"}
        if str(exc) == "ingestion_already_processing":
            logger.info(json.dumps(build_log_event("ingestion_skipped_processing", source_uri=document_event.source_uri)))
            return {"source_uri": document_event.source_uri, "status": "skipped_processing"}
        raise

    try:
        with tempfile.TemporaryDirectory(prefix="ingestion-") as temp_dir:
            local_path = Path(temp_dir) / Path(document_event.key).name
            _download_s3_object(document_event, local_path, region_name=region_name)
            indexed_doc_count = index_documents_for_paths([local_path])
    except Exception as exc:
        _update_status(table, document_event, FAILED_STATUS, error_message=str(exc))
        raise

    _update_status(table, document_event, COMPLETED_STATUS, indexed_doc_count=indexed_doc_count)
    return {"source_uri": document_event.source_uri, "status": COMPLETED_STATUS, "indexed_doc_count": indexed_doc_count}


def handler(event: dict[str, Any], _context: Any) -> dict[str, Any]:
    started_at = time.perf_counter()
    region_name = get_aws_region()
    records = _parse_s3_events(event)
    if not records:
        raise ValueError("No S3 records found in ingestion event.")

    processed: list[dict[str, Any]] = []
    for record in records:
        try:
            processed.append(_process_record(record, region_name=region_name))
        except ValueError as exc:
            if str(exc).startswith("Unsupported document type for ingestion"):
                logger.warning(json.dumps(build_log_event("ingestion_unsupported_type", source_uri=record.source_uri, error=str(exc))))
                processed.append({"source_uri": record.source_uri, "status": "unsupported_type", "error": str(exc)})
                continue
            raise

    logger.info(
        json.dumps(
            build_log_event(
                "ingestion_completed",
                record_count=len(processed),
                results=processed,
                latency_ms=round((time.perf_counter() - started_at) * 1000, 2),
            )
        )
    )
    return {"processed": processed}
