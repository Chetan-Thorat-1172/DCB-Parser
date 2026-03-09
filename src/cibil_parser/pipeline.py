"""
Main Parsing Pipeline — Stage 3 & 4 Orchestrator.

Wires together:
  Stage 1: Layout extraction (extract.py)
  Stage 2: Section detection (section_detector.py)
  Stage 3: Section parsing (section_parsers/*)
  Stage 4: Output assembly (models.py)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from .extract import extract_layout_from_pdf, load_layout_from_json, merge_layout_jsons
from .models import CreditReport
from .section_detector import DetectedSection, SectionType, detect_sections
from .section_parsers.account_parser import parse_accounts
from .section_parsers.address_parser import parse_addresses
from .section_parsers.consumer_info_parser import parse_consumer_information
from .section_parsers.email_parser import parse_email_contacts
from .section_parsers.employment_parser import parse_employment_information
from .section_parsers.enquiry_parser import parse_enquiries
from .section_parsers.header_parser import parse_report_header
from .section_parsers.summary_parser import parse_summary
from .template_registry import detect_template

logger = logging.getLogger(__name__)


def _get_sections_by_type(
    sections: list[DetectedSection], section_type: str
) -> list[DetectedSection]:
    """Get all sections matching the given type."""
    return [s for s in sections if s.section_type == section_type]


def _merge_boxes(sections: list[DetectedSection]) -> list[dict[str, Any]]:
    """Merge boxes from multiple sections of the same type."""
    boxes: list[dict[str, Any]] = []
    for section in sections:
        boxes.extend(section.boxes)
    return boxes


def parse_layout(layout_doc: dict[str, Any]) -> CreditReport:
    """
    Parse a PyMuPDF layout JSON document into a structured CreditReport.

    This is the main entry point for the parsing pipeline (stages 2-4).

    Parameters
    ----------
    layout_doc : dict
        The PyMuPDF layout JSON (output of Stage 1).

    Returns
    -------
    CreditReport
        Fully structured credit report object.
    """
    # --- Template detection ---
    template = detect_template(layout_doc)
    if template:
        logger.info("Using template: %s (v%s)", template.name, template.version)
    else:
        logger.warning("No template detected, using default CIBIL parsing rules")

    # --- Stage 2: Section detection ---
    sections = detect_sections(layout_doc)
    logger.info(
        "Detected %d sections: %s",
        len(sections),
        [(s.section_type, len(s.boxes)) for s in sections],
    )

    # --- Stage 3: Section-specific parsing ---
    report = CreditReport()

    # Report header
    header_sections = _get_sections_by_type(sections, SectionType.REPORT_HEADER)
    if header_sections:
        report.report_metadata = parse_report_header(
            _merge_boxes(header_sections)
        )

    # Consumer information (includes score, identifications, telephones)
    consumer_sections = _get_sections_by_type(
        sections, SectionType.CONSUMER_INFORMATION
    )
    if consumer_sections:
        consumer, score, identifications, telephones = parse_consumer_information(
            _merge_boxes(consumer_sections)
        )
        report.consumer_information = consumer
        report.cibil_score = score
        report.identifications = identifications
        report.telephones = telephones

    # Email contacts
    email_sections = _get_sections_by_type(sections, SectionType.EMAIL_CONTACTS)
    if email_sections:
        report.email_contacts = parse_email_contacts(
            _merge_boxes(email_sections)
        )

    # Addresses
    address_sections = _get_sections_by_type(sections, SectionType.ADDRESSES)
    if address_sections:
        report.addresses = parse_addresses(_merge_boxes(address_sections))

    # Employment information
    employment_sections = _get_sections_by_type(
        sections, SectionType.EMPLOYMENT_INFORMATION
    )
    if employment_sections:
        report.employment_information = parse_employment_information(
            _merge_boxes(employment_sections)
        )

    # Summary
    summary_sections = _get_sections_by_type(sections, SectionType.SUMMARY)
    if summary_sections:
        report.summary = parse_summary(_merge_boxes(summary_sections))

    # Accounts
    account_sections = _get_sections_by_type(sections, SectionType.ACCOUNTS)
    if account_sections:
        report.accounts = parse_accounts(_merge_boxes(account_sections))

    # Enquiries
    enquiry_sections = _get_sections_by_type(sections, SectionType.ENQUIRIES)
    if enquiry_sections:
        report.enquiries = parse_enquiries(_merge_boxes(enquiry_sections))

    # --- Stage 4: Validation & assembly (the model itself handles this) ---
    logger.info(
        "Parsing complete: %d identifications, %d addresses, "
        "%d accounts, %d enquiries",
        len(report.identifications),
        len(report.addresses),
        len(report.accounts),
        len(report.enquiries),
    )

    return report


# ---------------------------------------------------------------------------
# High-level convenience functions
# ---------------------------------------------------------------------------
def parse_pdf(pdf_path: str | Path) -> CreditReport:
    """
    Full pipeline: PDF → Layout JSON → Structured CreditReport.

    Parameters
    ----------
    pdf_path : str | Path
        Path to the CIBIL credit report PDF.

    Returns
    -------
    CreditReport
        Parsed and structured credit report.
    """
    layout_doc = extract_layout_from_pdf(pdf_path)
    return parse_layout(layout_doc)


# Parse from a pre-extracted layout JSON file.
def parse_layout_json(json_path: str | Path) -> CreditReport:
    layout_doc = load_layout_from_json(json_path)
    return parse_layout(layout_doc)


# Parse from multiple per-page layout JSON files.
def parse_layout_jsons(*json_paths: str | Path) -> CreditReport:

    layout_doc = merge_layout_jsons(*json_paths)
    return parse_layout(layout_doc)


def report_to_json(report: CreditReport, indent: int = 2) -> str:
    """Serialize a CreditReport to a JSON string."""
    return report.model_dump_json(indent=indent, exclude_none=True)


def report_to_dict(report: CreditReport) -> dict[str, Any]:
    """Convert a CreditReport to a plain dict (for BigQuery / Parquet)."""
    return report.model_dump(exclude_none=True)
