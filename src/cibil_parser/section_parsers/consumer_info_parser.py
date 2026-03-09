"""
Parser for the Consumer Information section.

This is the first major section after the header. In CIBIL reports,
it's delivered as a large table box that contains:
  - Consumer name, DOB, gender
  - CIBIL TransUnion score(s)
  - Identification documents (PAN, UID)
  - Telephone numbers

We parse each sub-section by detecting known row patterns in the table extract.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from ..models import (
    CibilScore,
    ConsumerInformation,
    Identification,
    Telephone,
)
from .utils import (
    clean_value,
    extract_spans_text,
    get_table_extract,
    safe_int,
    split_label_value,
)

logger = logging.getLogger(__name__)


def _parse_from_text_boxes(
    boxes: list[dict[str, Any]],
) -> ConsumerInformation:
    """
    Parse consumer info from text boxes that appear before the table.

    These boxes contain label:value spans on the same line:
        NAME: MALLIXXXXXX X
        DATE OF BIRTH: 1988-07-30
    """
    info = ConsumerInformation()

    for box in boxes:
        if box.get("boxclass") not in ("text",):
            continue

        spans = extract_spans_text(box)
        i = 0
        while i < len(spans):
            text = spans[i]["text"]

            if text.upper().startswith("NAME:"):
                _, val = split_label_value(text)
                if val:
                    info.name = clean_value(val)
                elif i + 1 < len(spans):
                    info.name = clean_value(spans[i + 1]["text"])
                    i += 1

            elif text.upper().startswith("DATE OF BIRTH:"):
                _, val = split_label_value(text)
                if val:
                    info.date_of_birth = clean_value(val)
                elif i + 1 < len(spans):
                    info.date_of_birth = clean_value(spans[i + 1]["text"])
                    i += 1

            elif text.upper().startswith("GENDER:"):
                _, val = split_label_value(text)
                if val:
                    info.gender = clean_value(val)
                elif i + 1 < len(spans):
                    info.gender = clean_value(spans[i + 1]["text"])
                    i += 1

            i += 1

    return info


def _parse_from_table(
    table_extract: list[list[Optional[str]]],
) -> tuple[ConsumerInformation, CibilScore, list[Identification], list[Telephone]]:
    """
    Parse the main consumer information table.

    This table contains several sub-sections identified by row content:
    - NAME / DOB / GENDER
    - CIBIL TRANSUNION SCORE(S)
    - IDENTIFICATION(S)
    - TELEPHONE(S)
    """
    consumer = ConsumerInformation()
    score = CibilScore()
    identifications: list[Identification] = []
    telephones: list[Telephone] = []

    # State machine for tracking which sub-section we're in
    current_subsection = "consumer"

    for row_idx, row in enumerate(table_extract):
        if not row:
            continue

        # Get the first non-null cell for pattern matching
        first_cell = ""
        for cell in row:
            if cell and cell.strip():
                first_cell = cell.strip()
                break

        first_upper = first_cell.upper()

        # ---- Sub-section detection ----
        if "CIBIL TRANSUNION SCORE" in first_upper:
            current_subsection = "score"
            continue
        elif first_upper.startswith("IDENTIFICATION"):
            current_subsection = "identification"
            continue
        elif first_upper.startswith("TELEPHONE"):
            current_subsection = "telephone"
            continue
        elif first_upper.startswith("POSSIBLE RANGE"):
            current_subsection = "score_range"
            continue
        elif first_upper.startswith("SCORE NAME"):
            # This is the score table header row
            continue
        elif first_upper.startswith("IDENTIFICATION TYPE"):
            # This is the identification table header row
            continue
        elif first_upper.startswith("TELEPHONE TYPE"):
            # This is the telephone table header row
            continue
        elif first_upper.startswith("*"):
            # Footnote row — skip
            continue
        elif first_upper.startswith("CONSUMER"):
            # Skip if this is just a sub-section label like "Consumer with..."
            if "CONSUMER WITH" in first_upper or "CONSUMER NOT" in first_upper:
                continue

        # ---- Parse based on current sub-section ----
        if current_subsection == "consumer":
            _parse_consumer_row(row, consumer)

        elif current_subsection == "score":
            _parse_score_row(row, score)

        elif current_subsection == "identification":
            _parse_identification_row(row, identifications)

        elif current_subsection == "telephone":
            _parse_telephone_row(row, telephones)

    return consumer, score, identifications, telephones


def _parse_consumer_row(row: list[Optional[str]], consumer: ConsumerInformation) -> None:
    """Parse a row belonging to the consumer info sub-section."""
    combined = " ".join((c or "") for c in row).strip()

    # NAME row: "NAME:\nMALLIXXXXXX X" or "NAME: MALLIXXXXXX X"
    if "NAME:" in combined.upper() and not consumer.name:
        for cell in row:
            if cell and "NAME:" in cell.upper():
                parts = cell.split("\n")
                for part in parts:
                    if "NAME:" in part.upper():
                        _, val = split_label_value(part)
                        if val:
                            consumer.name = clean_value(val)
                    elif part.strip() and not consumer.name:
                        consumer.name = clean_value(part)

    # DATE OF BIRTH / GENDER row
    if "DATE OF BIRTH" in combined.upper():
        for cell in row:
            if not cell:
                continue
            if "DATE OF BIRTH" in cell.upper():
                _, val = split_label_value(cell)
                if val:
                    consumer.date_of_birth = clean_value(val)
            if "GENDER" in cell.upper():
                _, val = split_label_value(cell)
                if val:
                    consumer.gender = clean_value(val)


def _parse_score_row(row: list[Optional[str]], score: CibilScore) -> None:
    """Parse a row belonging to the CIBIL score sub-section."""
    cells = [c.strip() if c else "" for c in row]

    # Check if first cell looks like a score name
    first = cells[0] if cells else ""
    if not first or first.upper().startswith("POSSIBLE") or first.upper().startswith("CONSUMER"):
        return

    # Score row: [SCORE_NAME, SCORE_VALUE, ..., SCORING_FACTORS]
    if first.upper().startswith("CIBIL") or first.upper().startswith("TRANSUNION"):
        score.score_name = clean_value(first)

        # Score value is typically in column 1
        if len(cells) > 1:
            score_val = safe_int(cells[1])
            if score_val:
                score.score = score_val

        # Scoring factors can be in column 3 or 4
        for cell in cells[2:]:
            if cell and not cell.isdigit():
                factors = cell.split("\n")
                for f in factors:
                    f_clean = re.sub(r"^\d+\.\s*", "", f.strip())
                    if f_clean:
                        score.scoring_factors.append(f_clean)


def _parse_identification_row(
    row: list[Optional[str]], identifications: list[Identification]
) -> None:
    """Parse a row belonging to the identification sub-section."""
    cells = [c.strip() if c else "" for c in row]
    first = cells[0] if cells else ""

    if not first:
        return

    # Skip header rows and sub-section labels
    if first.upper() in ("IDENTIFICATION TYPE", "IDENTIFICATION(S):"):
        return

    ident = Identification()
    ident.identification_type = clean_value(first)

    if len(cells) > 1:
        ident.identification_number = clean_value(cells[1])
    if len(cells) > 3:
        ident.issue_date = clean_value(cells[3])
    if len(cells) > 4:
        ident.expiration_date = clean_value(cells[4])

    if ident.identification_type:
        identifications.append(ident)


def _parse_telephone_row(
    row: list[Optional[str]], telephones: list[Telephone]
) -> None:
    """Parse a row belonging to the telephone sub-section."""
    cells = [c.strip() if c else "" for c in row]
    first = cells[0] if cells else ""

    if not first:
        return

    # Skip header rows
    if first.upper() in ("TELEPHONE TYPE", "TELEPHONE(S):"):
        return

    phone = Telephone()
    phone.telephone_type = clean_value(first)

    # Telephone number may be in column 2 (index varies based on table structure)
    if len(cells) > 2:
        phone.telephone_number = clean_value(cells[2])
    elif len(cells) > 1:
        phone.telephone_number = clean_value(cells[1])

    if len(cells) > 4:
        phone.telephone_extension = clean_value(cells[4])

    if phone.telephone_type or phone.telephone_number:
        telephones.append(phone)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------
def parse_consumer_information(
    boxes: list[dict[str, Any]],
) -> tuple[ConsumerInformation, CibilScore, list[Identification], list[Telephone]]:
    """
    Parse the Consumer Information section.

    Returns a tuple of:
    - ConsumerInformation (name, DOB, gender)
    - CibilScore (score name, value, factors)
    - list of Identification (PAN, UID, etc.)
    - list of Telephone entries
    """
    consumer = ConsumerInformation()
    score = CibilScore()
    identifications: list[Identification] = []
    telephones: list[Telephone] = []

    # First, try to extract from text boxes (NAME, DOB appear as text before table)
    text_consumer = _parse_from_text_boxes(boxes)

    # Then parse the main table
    for box in boxes:
        table_extract = get_table_extract(box)
        if table_extract:
            t_consumer, t_score, t_ids, t_phones = _parse_from_table(table_extract)

            # Merge: prefer text-extracted values, fill in from table
            consumer.name = text_consumer.name or t_consumer.name
            consumer.date_of_birth = text_consumer.date_of_birth or t_consumer.date_of_birth
            consumer.gender = text_consumer.gender or t_consumer.gender

            if t_score.score_name:
                score = t_score
            identifications.extend(t_ids)
            telephones.extend(t_phones)

    # Fallback to text-only consumer info if no table found
    if not consumer.name and text_consumer.name:
        consumer = text_consumer

    return consumer, score, identifications, telephones
