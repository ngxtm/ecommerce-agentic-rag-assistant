from pathlib import Path
from unittest.mock import Mock, patch

from scripts.index_sample_docs import (
    AMAZON_10K_DOC_ID,
    LEGACY_MARKDOWN_DOC_IDS,
    PRIMARY_TABLE_SECTION,
    _build_pdf_documents,
    _clean_pdf_line,
    _delete_existing_doc_chunks,
    _remove_toc_pages,
)


@patch("scripts.index_sample_docs._extract_pdf_metadata")
@patch("scripts.index_sample_docs._split_pdf_into_sections")
@patch("scripts.index_sample_docs._remove_toc_pages")
@patch("scripts.index_sample_docs._extract_pdf_pages")
def test_build_pdf_documents_creates_narrative_and_table_chunks(
    mock_extract_pdf_pages: Mock,
    mock_remove_toc_pages: Mock,
    mock_split_pdf_into_sections: Mock,
    mock_extract_pdf_metadata: Mock,
) -> None:
    path = Path("docs/company/Company-10k-18pages.pdf")
    mock_extract_pdf_pages.return_value = [(8, ["mock page text"])]
    mock_remove_toc_pages.return_value = [(8, ["mock page text"])]
    mock_extract_pdf_metadata.return_value = ("Amazon.com, Inc.", "FORM 10-K", "December 31, 2019")
    mock_split_pdf_into_sections.return_value = [
        Mock(
            part="PART II",
            item=PRIMARY_TABLE_SECTION,
            subsection=None,
            section_label=PRIMARY_TABLE_SECTION,
            lines=[
                "Selected Consolidated Financial Data",
                "(in millions, except per share data)",
                "2019 2018 2017 2016 2015",
                "Net sales 280,522 232,887 177,866 135,987 107,006",
                "Operating income 14,541 12,421 4,106 4,186 2,233",
                "Diluted earnings per share 23.01 20.14 6.15 4.90 1.25",
            ],
            page_start=8,
            page_end=8,
        )
    ]

    documents = _build_pdf_documents(path, "2026-04-18T00:00:00+00:00")

    assert any(document.doc_id == AMAZON_10K_DOC_ID for document in documents)
    assert any(document.content_type == "table_block" for document in documents)
    row_chunks = [document for document in documents if document.content_type == "table_row"]
    assert row_chunks
    net_sales_2019 = next(document for document in row_chunks if document.metric == "Net sales" and document.year == "2019")
    assert net_sales_2019.value_raw == "280,522"
    assert net_sales_2019.value_normalized == 280522.0
    assert net_sales_2019.unit == "million USD"
    per_share_2019 = next(document for document in row_chunks if document.metric == "Diluted earnings per share" and document.year == "2019")
    assert per_share_2019.unit == "USD/share"


@patch("scripts.index_sample_docs._extract_pdf_pages")
def test_build_pdf_documents_returns_empty_when_pdf_missing(mock_extract_pdf_pages: Mock) -> None:
    documents = _build_pdf_documents(Path("docs/company/missing.pdf"), "2026-04-18T00:00:00+00:00")

    assert documents == []
    mock_extract_pdf_pages.assert_not_called()


def test_delete_existing_doc_chunks_targets_fixed_doc_id() -> None:
    client = Mock()

    _delete_existing_doc_chunks(client, "policy-faq-chunks", AMAZON_10K_DOC_ID)

    client.delete_by_query.assert_called_once()
    args = client.delete_by_query.call_args.kwargs
    assert args["index"] == "policy-faq-chunks"
    assert args["body"]["query"]["term"]["doc_id.keyword"] == AMAZON_10K_DOC_ID


def test_clean_pdf_line_removes_table_of_contents_prefix() -> None:
    assert _clean_pdf_line("Table of Contents PART I") == "PART I"
    assert _clean_pdf_line("Table of Contents") is None



def test_remove_toc_pages_keeps_first_real_item_page() -> None:
    pages = [
        (2, ["TABLE OF CONTENTS", "PART I", "Item 1. Business ........ 3", "Item 1A. Risk Factors ........ 8"]),
        (3, ["PART I", "Item 1. Business", "We serve customers through our online and physical stores."]),
    ]

    filtered = _remove_toc_pages(pages)

    assert filtered == [
        (3, ["PART I", "Item 1. Business", "We serve customers through our online and physical stores."])
    ]



def test_legacy_markdown_doc_ids_are_locked_for_scoped_cleanup() -> None:
    assert LEGACY_MARKDOWN_DOC_IDS == (
        "shipping_policy",
        "returns_policy",
        "refund_policy",
        "order_tracking_faq",
    )
