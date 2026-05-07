from __future__ import annotations

from botocore.exceptions import ClientError

from app.backend.ingestion_handler import (
    COMPLETED_STATUS,
    FAILED_STATUS,
    PROCESSING_STATUS,
    S3DocumentEvent,
    _is_processing_stale,
    _mark_processing,
    _process_record,
    handler,
)


class FakeTable:
    def __init__(self, item: dict | None = None, conditional_failure: bool = False) -> None:
        self.item = item
        self.conditional_failure = conditional_failure
        self.updated = None

    def get_item(self, Key: dict) -> dict:
        return {"Item": self.item} if self.item is not None else {}

    def put_item(self, **kwargs) -> None:
        if self.conditional_failure:
            raise ClientError({"Error": {"Code": "ConditionalCheckFailedException", "Message": "exists"}}, "PutItem")
        self.item = kwargs["Item"]

    def update_item(self, **kwargs) -> None:
        self.updated = kwargs


def test_is_processing_stale_returns_true_for_missing_started_at(monkeypatch) -> None:
    monkeypatch.setenv("INGESTION_PROCESSING_TIMEOUT_SECONDS", "60")
    assert _is_processing_stale({}) is True


def test_mark_processing_skips_when_already_processing_and_not_stale(monkeypatch) -> None:
    monkeypatch.setenv("INGESTION_STATE_TTL_DAYS", "30")
    event = S3DocumentEvent(bucket="bucket", key="phase1-kb/doc.pdf", version_id="v1", etag="etag")
    table = FakeTable(item={"status": PROCESSING_STATUS, "started_at": "2999-01-01T00:00:00+00:00"}, conditional_failure=True)

    try:
        _mark_processing(table, event)
        assert False, "Expected processing conflict"
    except RuntimeError as exc:
        assert str(exc) == "ingestion_already_processing"


def test_mark_processing_reclaims_stale_processing_record(monkeypatch) -> None:
    monkeypatch.setenv("INGESTION_STATE_TTL_DAYS", "30")
    monkeypatch.setenv("INGESTION_PROCESSING_TIMEOUT_SECONDS", "60")
    event = S3DocumentEvent(bucket="bucket", key="phase1-kb/doc.pdf", version_id="v1", etag="etag")
    table = FakeTable(item={"status": PROCESSING_STATUS, "started_at": "2000-01-01T00:00:00+00:00"}, conditional_failure=True)

    _mark_processing(table, event)

    assert table.updated is not None
    assert table.updated["ExpressionAttributeValues"][":status"] == PROCESSING_STATUS


def test_process_record_skips_completed(monkeypatch) -> None:
    event = S3DocumentEvent(bucket="bucket", key="phase1-kb/doc.pdf", version_id="v1", etag="etag")
    table = FakeTable(item={"status": COMPLETED_STATUS})
    monkeypatch.setattr("app.backend.ingestion_handler._build_state_table", lambda region_name=None: table)

    result = _process_record(event)

    assert result["status"] == "skipped_completed"


def test_process_record_skips_active_processing(monkeypatch) -> None:
    event = S3DocumentEvent(bucket="bucket", key="phase1-kb/doc.pdf", version_id="v1", etag="etag")
    table = FakeTable(item={"status": PROCESSING_STATUS, "started_at": "2999-01-01T00:00:00+00:00"}, conditional_failure=True)
    monkeypatch.setattr("app.backend.ingestion_handler._build_state_table", lambda region_name=None: table)

    result = _process_record(event)

    assert result["status"] == "skipped_processing"


def test_process_record_marks_failed_when_download_errors(monkeypatch) -> None:
    event = S3DocumentEvent(bucket="bucket", key="phase1-kb/doc.pdf", version_id="v1", etag="etag")
    table = FakeTable()
    monkeypatch.setattr("app.backend.ingestion_handler._build_state_table", lambda region_name=None: table)
    monkeypatch.setattr(
        "app.backend.ingestion_handler._download_s3_object",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("download boom")),
    )

    try:
        _process_record(event)
        assert False, "Expected download error"
    except RuntimeError as exc:
        assert str(exc) == "download boom"

    assert table.updated is not None
    assert table.updated["ExpressionAttributeValues"][":status"] == FAILED_STATUS
    assert table.updated["ExpressionAttributeValues"][":error_message"] == "download boom"


def test_handler_marks_unsupported_type_without_failing(monkeypatch) -> None:
    event = {
        "Records": [
            {
                "s3": {
                    "bucket": {"name": "bucket"},
                    "object": {"key": "phase1-kb/readme.csv", "versionId": "v1", "eTag": "etag"},
                }
            }
        ]
    }

    monkeypatch.setattr("app.backend.ingestion_handler._build_state_table", lambda region_name=None: FakeTable())
    monkeypatch.setattr("app.backend.ingestion_handler._download_s3_object", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        "app.backend.ingestion_handler.index_documents_for_paths",
        lambda paths: (_ for _ in ()).throw(ValueError("Unsupported document type for ingestion: .csv")),
    )

    result = handler(event, None)

    assert result["processed"][0]["status"] == "unsupported_type"
