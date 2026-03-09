"""
Parser for the Enquiries section.

Enquiries appear in a table with the structure:
  MEMBER | ENQUIRY DATE | ENQUIRY PURPOSE | ENQUIRY AMOUNT

The table may also contain DPD history from a previous account,
followed by the "ENQUIRIES:" header row, then the enquiry data rows.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from ..models import Enquiry
from .utils import clean_value, get_table_extract, safe_int

logger = logging.getLogger(__name__)


def parse_enquiries(boxes: list[dict[str, Any]]) -> list[Enquiry]:
    """
    Parse the ENQUIRIES section.

    Strategy:
    1. Find the table box(es) in this section.
    2. Locate the "ENQUIRIES:" label row.
    3. Locate the column header row (MEMBER | ENQUIRY DATE | ...).
    4. Parse all subsequent rows as enquiry entries.
    """
    enquiries: list[Enquiry] = []

    for box in boxes:
        table_extract = get_table_extract(box)
        if not table_extract:
            continue

        # Find the start of enquiry data
        enquiry_started = False
        header_found = False
        # Column indices for enquiry fields
        col_member = 0
        col_date = 4
        col_purpose = 8
        col_amount = 10

        for row_idx, row in enumerate(table_extract):
            combined = " ".join((c or "") for c in row).strip().upper()

            # Detect "ENQUIRIES:" section start
            if "ENQUIRIES:" in combined:
                enquiry_started = True
                continue

            if not enquiry_started:
                continue

            # Detect header row
            if "MEMBER" in combined and "ENQUIRY" in combined:
                header_found = True
                # Determine column indices from the header
                for i, cell in enumerate(row):
                    if not cell:
                        continue
                    cell_upper = cell.strip().upper()
                    if cell_upper == "MEMBER":
                        col_member = i
                    elif "ENQUIRY DATE" in cell_upper or cell_upper == "ENQUIRY DATE":
                        col_date = i
                    elif cell_upper in ("ENQUIRY", "PURPOSE"):
                        if "ENQUIRY" == cell_upper:
                            col_purpose = i
                    elif cell_upper == "PURPOSE":
                        col_purpose = i
                    elif "ENQUIRY AMOUNT" in cell_upper:
                        col_amount = i
                    elif cell_upper == "AMOUNT" or "AMOUNT" in cell_upper:
                        col_amount = i
                continue

            if not header_found:
                continue

            # Parse enquiry data rows
            # Skip empty rows and DPD rows
            non_empty = [c for c in row if c and c.strip()]
            if not non_empty:
                continue

            # Get member name from first column
            member = _safe_get(row, col_member)
            if not member or not member.strip():
                continue

            # Skip if this looks like a DPD row
            if re.match(r"^\d{2}-\d{2}$", member.strip()):
                continue
            if re.match(r"^0{3}$", member.strip()):
                continue

            enquiry = Enquiry()
            enquiry.member = clean_value(member)

            # Date
            date_val = _safe_get(row, col_date)
            if date_val:
                enquiry.enquiry_date = clean_value(date_val)

            # Purpose
            purpose_val = _safe_get(row, col_purpose)
            if purpose_val:
                enquiry.enquiry_purpose = clean_value(purpose_val)

            # Amount
            amount_val = _safe_get(row, col_amount)
            if amount_val:
                enquiry.enquiry_amount = safe_int(amount_val)

            if enquiry.member:
                enquiries.append(enquiry)

    logger.info("Parsed %d enquiries", len(enquiries))
    return enquiries


def _safe_get(lst: list, idx: int) -> Optional[str]:
    """Safely get an element from a list, returning None if out of bounds."""
    if 0 <= idx < len(lst):
        return lst[idx]
    return None
