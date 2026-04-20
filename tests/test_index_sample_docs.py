from pathlib import Path
from unittest.mock import Mock, patch

from opensearchpy.exceptions import NotFoundError, RequestError

from scripts.index_sample_docs import (
    AMAZON_10K_DOC_ID,
    EXECUTIVE_OFFICERS_SECTION,
    ITEM_1A_SECTION,
    ITEM_7_SECTION,
    LEGACY_MARKDOWN_DOC_IDS,
    PRIMARY_TABLE_SECTION,
    DocumentBlock,
    NormalizedLine,
    _build_chunk_id,
    _build_document_skeleton,
    _build_pdf_documents,
    _business_refiner,
    _clean_pdf_line,
    _count_documents_by_doc_id,
    _delete_existing_doc_chunks,
    _doc_id_exists,
    _ensure_index,
    _executive_refiner,
    _item8_refiner,
    _legal_proceedings_refiner,
    _mapping_supports_doc_id_keyword,
    _market_risk_refiner,
    _mda_refiner,
    _normalize_pdf_lines,
    _overview_refiner,
    _properties_refiner,
    _remove_toc_pages,
    _extract_risk_sections_from_text,
    _risk_factor_refiner,
    _validate_documents,
    _verify_doc_id_cleanup,
)


def test_build_chunk_id_is_stable_for_same_inputs() -> None:
    assert _build_chunk_id("amazon_10k_2019", "table_row", "Item 6", "Net sales", "2019") == _build_chunk_id(
        "amazon_10k_2019", "table_row", "Item 6", "Net sales", "2019"
    )


def test_build_chunk_id_changes_when_semantic_key_changes() -> None:
    assert _build_chunk_id("amazon_10k_2019", "table_row", "Item 6", "Net sales", "2019") != _build_chunk_id(
        "amazon_10k_2019", "table_row", "Item 6", "Operating income", "2019"
    )


def test_normalize_pdf_lines_preserves_page_numbers() -> None:
    lines = _normalize_pdf_lines([(3, ["Item 1. Business", "We serve customers."])])

    assert lines[0].page_number == 3
    assert lines[0].text == "Item 1. Business"
    assert lines[1].text == "We serve customers."


def test_build_document_skeleton_splits_overview_and_items() -> None:
    lines = [
        NormalizedLine(page_number=1, text="Available Information", raw_text="Available Information", source_index=0),
        NormalizedLine(page_number=2, text="PART I", raw_text="PART I", source_index=0),
        NormalizedLine(page_number=3, text="Item 1. Business", raw_text="Item 1. Business", source_index=0),
        NormalizedLine(page_number=3, text="We serve customers.", raw_text="We serve customers.", source_index=1),
    ]

    blocks = _build_document_skeleton(lines)

    assert blocks[0].label == "Overview"
    assert blocks[1].item == "Item 1. Business"


def test_overview_refiner_keeps_factual_front_matter() -> None:
    block = DocumentBlock(
        part=None,
        item=None,
        label="Overview",
        lines=[
            NormalizedLine(1, "Available Information", "Available Information", 0),
            NormalizedLine(1, "Our investor relations website includes SEC filings.", "Our investor relations website includes SEC filings.", 1),
        ],
        page_start=1,
        page_end=1,
    )

    refined = _overview_refiner(block)

    assert len(refined) == 1
    assert refined[0].block_type == "fact"


def test_executive_refiner_creates_profile_rows_and_bios() -> None:
    block = DocumentBlock(
        part=None,
        item=None,
        label="Overview",
        lines=[
            NormalizedLine(5, "Executive Officers and Directors", "Executive Officers and Directors", 0),
            NormalizedLine(5, "Information About Our Executive Officers", "Information About Our Executive Officers", 1),
            NormalizedLine(5, "Jeffrey P. Bezos 56 President, Chief Executive Officer, and Chairman of the Board", "", 2),
            NormalizedLine(5, "Andrew R. Jassy 52 CEO Amazon Web Services", "", 3),
            NormalizedLine(5, "Jeffrey P. Bezos. Mr. Bezos has been Chairman of the Board of Amazon.com since founding it in 1994.", "", 4),
            NormalizedLine(5, "Andrew R. Jassy. Mr. Jassy has served as CEO Amazon Web Services since April 2016.", "", 5),
        ],
        page_start=5,
        page_end=5,
    )

    refined = _executive_refiner(block)

    assert any(entry.block_type == "profile_row" and entry.entity_name == "Andrew R. Jassy" for entry in refined)
    assert any(entry.block_type == "profile_bio" and entry.entity_name == "Jeffrey P. Bezos" for entry in refined)
    assert any(entry.block_type == "narrative" for entry in refined)


def test_risk_factor_refiner_splits_sentence_headings() -> None:
    block = DocumentBlock(
        part="PART I",
        item=ITEM_1A_SECTION,
        label=ITEM_1A_SECTION,
        lines=[
            NormalizedLine(8, "The Loss of Key Senior Management Personnel or the Inability to Hire and Retain Qualified Personnel Could Harm Our Business", "", 0),
            NormalizedLine(8, "Our future success depends on our senior management.", "", 1),
            NormalizedLine(8, "We compete for qualified personnel.", "", 2),
        ],
        page_start=8,
        page_end=8,
    )

    refined = _risk_factor_refiner(block)

    assert len(refined) == 1
    assert refined[0].subsection == "The Loss of Key Senior Management Personnel or the Inability to Hire and Retain Qualified Personnel Could Harm Our Business"


def test_mda_refiner_materializes_subsections() -> None:
    block = DocumentBlock(
        part="PART II",
        item=ITEM_7_SECTION,
        label=ITEM_7_SECTION,
        lines=[
            NormalizedLine(9, "Results of Operations", "", 0),
            NormalizedLine(9, "Net sales increased primarily due to unit growth.", "", 1),
            NormalizedLine(9, "Liquidity and Capital Resources", "", 2),
            NormalizedLine(9, "Cash flows remained strong.", "", 3),
        ],
        page_start=9,
        page_end=9,
    )

    refined = _mda_refiner(block)

    assert any(entry.subsection == "Results of Operations" for entry in refined)
    assert any(entry.subsection == "Liquidity and Capital Resources" for entry in refined)


def test_business_refiner_materializes_subsections_and_facts() -> None:
    block = DocumentBlock(
        part="PART I",
        item="Item 1. Business",
        label="Item 1. Business",
        lines=[
            NormalizedLine(3, "Overview", "", 0),
            NormalizedLine(3, "We serve consumers through our online and physical stores.", "", 1),
            NormalizedLine(3, "We focus on low prices, selection, and convenience.", "", 2),
            NormalizedLine(4, "Amazon Web Services", "", 3),
            NormalizedLine(4, "We serve developers and enterprises with on-demand technology services.", "", 4),
        ],
        page_start=3,
        page_end=4,
    )

    refined = _business_refiner(block)

    assert any(entry.subsection == "Overview" and entry.block_type == "narrative" for entry in refined)
    assert any(entry.subsection == "Overview" and entry.block_type == "fact" for entry in refined)
    assert any(entry.subsection == "Amazon Web Services" for entry in refined)


def test_properties_refiner_extracts_facilities_facts() -> None:
    block = DocumentBlock(
        part="PART I",
        item="Item 2. Properties",
        label="Item 2. Properties",
        lines=[
            NormalizedLine(6, "Properties", "", 0),
            NormalizedLine(6, "We operate offices, fulfillment centers, sortation centers, and data centers worldwide.", "", 1),
        ],
        page_start=6,
        page_end=6,
    )

    refined = _properties_refiner(block)

    assert any(entry.block_type == "fact" for entry in refined)
    assert any(entry.subsection == "Properties" for entry in refined)


def test_legal_proceedings_refiner_keeps_legal_narrative_grounded() -> None:
    block = DocumentBlock(
        part="PART I",
        item="Item 3. Legal Proceedings",
        label="Item 3. Legal Proceedings",
        lines=[
            NormalizedLine(7, "Legal Proceedings", "", 0),
            NormalizedLine(7, "From time to time, we are involved in legal proceedings and claims arising in the ordinary course of business.", "", 1),
        ],
        page_start=7,
        page_end=7,
    )

    refined = _legal_proceedings_refiner(block)

    assert any(entry.block_type == "fact" for entry in refined)
    assert any(entry.subsection == "Legal Proceedings" for entry in refined)


def test_market_risk_refiner_materializes_market_risk_subsections() -> None:
    block = DocumentBlock(
        part="PART II",
        item="Item 7A. Quantitative and Qualitative Disclosures About Market Risk",
        label="Item 7A. Quantitative and Qualitative Disclosures About Market Risk",
        lines=[
            NormalizedLine(12, "Interest Rate Risk", "", 0),
            NormalizedLine(12, "We are exposed to fluctuations in interest rates.", "", 1),
            NormalizedLine(12, "Foreign Exchange Risk", "", 2),
            NormalizedLine(12, "We are exposed to foreign currency exchange risk.", "", 3),
        ],
        page_start=12,
        page_end=12,
    )

    refined = _market_risk_refiner(block)

    assert any(entry.subsection == "Interest Rate Risk" for entry in refined)
    assert any(entry.subsection == "Foreign Exchange Risk" for entry in refined)


def test_item8_refiner_extracts_statement_table_blocks() -> None:
    block = DocumentBlock(
        part="PART II",
        item="Item 8. Financial Statements and Supplementary Data",
        label="Item 8. Financial Statements and Supplementary Data",
        lines=[
            NormalizedLine(13, "Consolidated Statements of Operations", "", 0),
            NormalizedLine(13, "2019 2018 2017", "", 1),
            NormalizedLine(13, "Net sales 280,522 232,887 177,866", "", 2),
        ],
        page_start=13,
        page_end=13,
    )

    refined = _item8_refiner(block)

    assert any(entry.block_type == "table_block" and entry.subsection == "Consolidated Statements of Operations" for entry in refined)
    assert any(entry.block_type == "table_row" and entry.metric == "Net sales" and entry.year == "2019" for entry in refined)


def test_extract_risk_sections_from_text_handles_embedded_key_personnel_heading() -> None:
    text = (
        "The Loss of Key Senior Management Personnel or the Failure to Hire and Retain Highly Skilled and Other Key Personnel Could Negatively Affect Our "
        "BusinessWe depend on our senior management and other key personnel, particularly Jeffrey P. Bezos, our President, CEO, and Chairman. "
        "We do not have key person life insurance policies. We Could Be Harmed by Data Loss or Other Security Breaches"
    )

    sections = _extract_risk_sections_from_text(text)

    assert sections
    assert sections[0][0].startswith("The Loss of Key Senior Management Personnel")
    assert "We depend on our senior management" in sections[0][1]


@patch("scripts.index_sample_docs._extract_pdf_metadata")
@patch("scripts.index_sample_docs._extract_pdf_pages")
@patch("pathlib.Path.exists")
def test_build_pdf_documents_creates_semantic_chunks(mock_exists: Mock, mock_extract_pdf_pages: Mock, mock_extract_pdf_metadata: Mock) -> None:
    path = Path("docs/company/Company-10k-18pages.pdf")
    mock_exists.return_value = True
    mock_extract_pdf_pages.return_value = [
        (5, [
            "Executive Officers and Directors",
            "Information About Our Executive Officers",
            "Andrew R. Jassy 52 CEO Amazon Web Services",
            "Andrew R. Jassy. Mr. Jassy has served as CEO Amazon Web Services since April 2016.",
        ]),
        (8, [
            "PART II",
            "Item 6. Selected Consolidated Financial Data",
            "Selected Consolidated Financial Data",
            "(in millions, except per share data)",
            "2019 2018 2017 2016 2015",
            "Net sales 280,522 232,887 177,866 135,987 107,006",
        ]),
        (9, [
            "Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations",
            "Results of Operations",
            "Net sales increased due to demand.",
        ]),
        (10, [
            "Item 1A. Risk Factors",
            "The Loss of Key Senior Management Personnel or the Inability to Hire and Retain Qualified Personnel Could Harm Our Business",
            "Our future success depends on our senior management.",
        ]),
        (11, [
            "Item 1. Business",
            "Overview",
            "We focus on low prices, selection, and convenience.",
        ]),
        (12, [
            "Item 2. Properties",
            "Properties",
            "We operate offices and fulfillment centers worldwide.",
        ]),
        (13, [
            "Item 3. Legal Proceedings",
            "Legal Proceedings",
            "From time to time, we are involved in legal proceedings in the ordinary course of business.",
        ]),
        (14, [
            "Item 7A. Quantitative and Qualitative Disclosures About Market Risk",
            "Interest Rate Risk",
            "We are exposed to fluctuations in interest rates.",
        ]),
        (15, [
            "Item 8. Financial Statements and Supplementary Data",
            "Consolidated Statements of Operations",
            "2019 2018 2017",
            "Net sales 280,522 232,887 177,866",
        ]),
    ]
    mock_extract_pdf_metadata.return_value = ("Amazon.com, Inc.", "FORM 10-K", "December 31, 2019")

    documents_first = _build_pdf_documents(path, "2026-04-20T00:00:00+00:00")
    documents_second = _build_pdf_documents(path, "2026-04-21T00:00:00+00:00")

    assert {document.chunk_id for document in documents_first} == {document.chunk_id for document in documents_second}
    assert any(document.content_type == "profile_row" for document in documents_first)
    assert any(document.content_type == "profile_bio" for document in documents_first)
    assert len([document for document in documents_first if document.section == PRIMARY_TABLE_SECTION and document.content_type == "table_block"]) == 1
    assert any(document.section == ITEM_7_SECTION and document.subsection == "Results of Operations" for document in documents_first)
    assert any(document.section == ITEM_1A_SECTION and document.subsection for document in documents_first)
    assert any(document.section == "Item 1. Business" and document.content_type == "fact" for document in documents_first)
    assert any(document.section == "Item 2. Properties" and document.content_type == "fact" for document in documents_first)
    assert any(document.section == "Item 3. Legal Proceedings" and document.content_type == "fact" for document in documents_first)
    assert any(document.section == "Item 7A. Quantitative and Qualitative Disclosures About Market Risk" and document.subsection == "Interest Rate Risk" for document in documents_first)
    assert any(document.section == "Item 8. Financial Statements and Supplementary Data" and document.content_type == "table_block" for document in documents_first)


def test_validate_documents_rejects_duplicate_metric_year_rows() -> None:
    document = Mock(chunk_id="1", section=PRIMARY_TABLE_SECTION, content_type="table_row", metric="Net sales", year="2019", entity_name=None, content="a")
    duplicate = Mock(chunk_id="2", section=PRIMARY_TABLE_SECTION, content_type="table_row", metric="Net sales", year="2019", entity_name=None, content="b")

    try:
        _validate_documents([document, duplicate])
        assert False, "Expected duplicate metric/year validation failure"
    except RuntimeError as exc:
        assert "duplicate metric/year rows" in str(exc)


def test_delete_existing_doc_chunks_targets_fixed_doc_id() -> None:
    client = Mock()

    _delete_existing_doc_chunks(client, "policy-faq-chunks", AMAZON_10K_DOC_ID)

    client.delete_by_query.assert_called_once()
    args = client.delete_by_query.call_args.kwargs
    assert args["index"] == "policy-faq-chunks"
    assert args["body"]["query"]["term"]["doc_id.keyword"] == AMAZON_10K_DOC_ID


def test_ensure_index_creates_index_with_expected_mapping() -> None:
    client = Mock()
    client.indices.get_mapping.side_effect = NotFoundError(404, "index_not_found_exception", {})

    _ensure_index(client, "policy-faq-chunks")

    client.indices.create.assert_called_once()
    args = client.indices.create.call_args.kwargs
    assert args["body"]["mappings"]["properties"]["entity_name"]["type"] == "text"


def test_ensure_index_ignores_existing_index_error() -> None:
    client = Mock()
    client.indices.get_mapping.side_effect = NotFoundError(404, "index_not_found_exception", {})
    client.indices.create.side_effect = RequestError(
        400,
        "resource_already_exists_exception",
        {"error": {"type": "resource_already_exists_exception"}},
    )

    _ensure_index(client, "policy-faq-chunks")


def test_mapping_supports_doc_id_keyword_returns_true_for_expected_mapping() -> None:
    client = Mock()
    client.indices.get_mapping.return_value = {
        "policy-faq-chunks": {
            "mappings": {
                "properties": {
                    "doc_id": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
                    "entity_name": {"type": "text"},
                    "index_version": {"type": "keyword"},
                }
            }
        }
    }

    assert _mapping_supports_doc_id_keyword(client, "policy-faq-chunks") is True


def test_doc_id_exists_returns_false_when_index_missing() -> None:
    client = Mock()
    client.search.side_effect = NotFoundError(404, "index_not_found_exception", {})

    assert _doc_id_exists(client, "policy-faq-chunks", AMAZON_10K_DOC_ID) is False


def test_count_documents_by_doc_id_returns_zero_when_index_missing() -> None:
    client = Mock()
    client.search.side_effect = NotFoundError(404, "index_not_found_exception", {})

    assert _count_documents_by_doc_id(client, "policy-faq-chunks", AMAZON_10K_DOC_ID) == 0


@patch("scripts.index_sample_docs.time.sleep")
@patch("scripts.index_sample_docs._count_documents_by_doc_id")
def test_verify_doc_id_cleanup_retries_until_ten_k_visible(mock_count: Mock, mock_sleep: Mock) -> None:
    client = Mock()
    mock_count.side_effect = [0, 0, 0, 0, 0, 0, 0, 0, 0, 3]

    _verify_doc_id_cleanup(client, "policy-faq-chunks")

    mock_sleep.assert_called_once_with(1)


def test_clean_pdf_line_removes_table_of_contents_prefix() -> None:
    assert _clean_pdf_line("Table of Contents PART I") == "PART I"
    assert _clean_pdf_line("Table of Contents") is None


def test_remove_toc_pages_keeps_first_real_item_page() -> None:
    pages = [
        (2, ["TABLE OF CONTENTS", "PART I", "Item 1. Business ........ 3", "Item 1A. Risk Factors ........ 8"]),
        (3, ["PART I", "Item 1. Business", "We serve customers through our online and physical stores."]),
    ]

    filtered = _remove_toc_pages(pages)

    assert filtered == [(3, ["PART I", "Item 1. Business", "We serve customers through our online and physical stores."])]


def test_legacy_markdown_doc_ids_are_locked_for_scoped_cleanup() -> None:
    assert LEGACY_MARKDOWN_DOC_IDS == (
        "shipping_policy",
        "returns_policy",
        "refund_policy",
        "order_tracking_faq",
    )
