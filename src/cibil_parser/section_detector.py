"""
Stage 2 — Section Detection

Identifies semantic sections within the PyMuPDF layout JSON by scanning
for known section-header boxes and their associated content boxes.

Each detected section carries:
  - section_type  (e.g. "consumer_information", "accounts", "enquiries")
  - boxes         (list of layout boxes belonging to this section)
  - page_number   (originating page)
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Section type enum
# ---------------------------------------------------------------------------
class SectionType:
    """Constants for known CIBIL report section types."""

    REPORT_HEADER = "report_header"
    CONSUMER_INFORMATION = "consumer_information"
    EMAIL_CONTACTS = "email_contacts"
    ADDRESSES = "addresses"
    EMPLOYMENT_INFORMATION = "employment_information"
    SUMMARY = "summary"
    ACCOUNTS = "accounts"
    ENQUIRIES = "enquiries"
    END_OF_REPORT = "end_of_report"
    UNKNOWN = "unknown"


# Header patterns → section type mapping
# These are matched against the text of section-header boxes.
# Order matters — first match wins.
SECTION_HEADER_PATTERNS: list[tuple[str, str]] = [
    (r"CONSUMER\s+INFORMATION", SectionType.CONSUMER_INFORMATION),
    (r"EMAIL\s+CONTACT", SectionType.EMAIL_CONTACTS),
    (r"ADDRESS\(?E?S?\)?", SectionType.ADDRESSES),
    (r"EMPLOYMENT\s+INFORMATION", SectionType.EMPLOYMENT_INFORMATION),
    (r"SUMMARY", SectionType.SUMMARY),
    (r"ACCOUNT\(?S?\)?:", SectionType.ACCOUNTS),
    (r"ENQUIR(?:Y|IES)", SectionType.ENQUIRIES),
]


def _classify_section_header(text: str) -> str:
    """Return the SectionType for a header text, or UNKNOWN."""
    text_upper = text.strip().upper()
    for pattern, section_type in SECTION_HEADER_PATTERNS:
        if re.search(pattern, text_upper):
            return section_type
    return SectionType.UNKNOWN


# ---------------------------------------------------------------------------
# Detected section dataclass
# ---------------------------------------------------------------------------
@dataclass
class DetectedSection:
    """A section detected within the credit report."""

    section_type: str
    boxes: list[dict[str, Any]] = field(default_factory=list)
    page_numbers: list[int] = field(default_factory=list)

    def add_box(self, box: dict[str, Any], page_number: int) -> None:
        self.boxes.append(box)
        if page_number not in self.page_numbers:
            self.page_numbers.append(page_number)


# ---------------------------------------------------------------------------
# Helper: extract text from a box
# ---------------------------------------------------------------------------
def get_box_text(box: dict[str, Any]) -> str:
    """
    Extract plain text from a layout box.

    Works for both textline-based boxes and table-based boxes.
    """
    texts: list[str] = []

    # From textlines
    textlines = box.get("textlines")
    if textlines:
        for tl in textlines:
            spans = tl.get("spans", [])
            for span in spans:
                t = span.get("text", "").strip()
                if t:
                    texts.append(t)

    # From table extract
    table = box.get("table")
    if table and table.get("extract"):
        for row in table["extract"]:
            for cell in row:
                if cell:
                    texts.append(cell.strip())

    return " ".join(texts)


# ---------------------------------------------------------------------------
# Main section detection
# ---------------------------------------------------------------------------
def detect_sections(layout_doc: dict[str, Any]) -> list[DetectedSection]:
    """
    Scan all pages and boxes in the layout document to identify sections.

    Strategy:
    1. Walk boxes in reading order (page-by-page, top-to-bottom).
    2. When a section-header box is found, start a new section.
    3. Non-header boxes are assigned to the current active section.
    4. Special handling for the main table on page 1 that contains
       consumer info, score, identifications, and telephones in one table.

    Returns
    -------
    list[DetectedSection]
        Ordered list of detected sections with their associated boxes.
    """
    sections: list[DetectedSection] = []
    current_section: DetectedSection | None = None

    # Start with a report-header section for pre-section boxes
    header_section = DetectedSection(section_type=SectionType.REPORT_HEADER)
    current_section = header_section

    pages = layout_doc.get("pages", [])
    for page in pages:
        page_number = page.get("page_number", 0)
        boxes = page.get("boxes", [])

        for box in boxes:
            boxclass = box.get("boxclass", "")

            # Skip pictures and page footers
            if boxclass in ("picture", "page-footer"):
                continue

            # Check if this is a section header
            if boxclass == "section-header":
                header_text = get_box_text(box)
                section_type = _classify_section_header(header_text)

                if section_type != SectionType.UNKNOWN:
                    # Save previous section if it has content
                    if current_section and current_section.boxes:
                        sections.append(current_section)

                    # Start a new section
                    current_section = DetectedSection(section_type=section_type)
                    current_section.add_box(box, page_number)
                    logger.debug(
                        "Detected section: %s on page %d",
                        section_type,
                        page_number,
                    )
                else:
                    # Unknown header — still add to current section
                    if current_section:
                        current_section.add_box(box, page_number)
                continue

            # Page headers on page 2+ that carry continuation data for accounts
            if boxclass == "page-header":
                # These carry overflow data from accounts spanning pages
                if current_section and current_section.section_type == SectionType.ACCOUNTS:
                    current_section.add_box(box, page_number)
                elif current_section:
                    current_section.add_box(box, page_number)
                continue

            # Check text boxes for section content cues
            box_text = get_box_text(box).upper()

            # Check for "DAYS PAST DUE" — these belong to the accounts section
            if "DAYS PAST DUE" in box_text:
                if not current_section or current_section.section_type != SectionType.ACCOUNTS:
                    if current_section and current_section.boxes:
                        sections.append(current_section)
                    current_section = DetectedSection(section_type=SectionType.ACCOUNTS)
                if current_section:
                    current_section.add_box(box, page_number)
                continue

            # Detect enquiries section when table contains "ENQUIRIES:" row
            if boxclass == "table" and box.get("table", {}).get("extract"):
                extract = box["table"]["extract"]
                has_enquiry_header = False
                for row in extract:
                    for cell in row:
                        if cell and "ENQUIRIES:" in cell.upper():
                            has_enquiry_header = True
                            break
                    if has_enquiry_header:
                        break

                if has_enquiry_header:
                    # This table contains enquiry data — may also have DPD data
                    # We'll let the section parser handle splitting
                    if current_section and current_section.boxes:
                        sections.append(current_section)
                    enquiry_section = DetectedSection(section_type=SectionType.ENQUIRIES)
                    enquiry_section.add_box(box, page_number)
                    sections.append(enquiry_section)
                    current_section = DetectedSection(section_type=SectionType.END_OF_REPORT)
                    continue

            # Check for "END OF REPORT"
            if "END OF REPORT" in box_text:
                if current_section and current_section.boxes:
                    sections.append(current_section)
                current_section = DetectedSection(section_type=SectionType.END_OF_REPORT)
                current_section.add_box(box, page_number)
                continue

            # Default: add to current section
            if current_section:
                current_section.add_box(box, page_number)

    # Don't forget the last section
    if current_section and current_section.boxes:
        sections.append(current_section)

    logger.info(
        "Detected %d sections: %s",
        len(sections),
        [s.section_type for s in sections],
    )
    return sections
