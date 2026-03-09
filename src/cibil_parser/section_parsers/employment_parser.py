"""
Parser for the Employment Information section.

Employment data comes in a simple 2-row table:
  Row 0 (header): ACCOUNT | TYPE | DATE REPORTED | OCCUPATION CODE | INCOME | ...
  Row 1+ (data):  values
"""

from __future__ import annotations

import logging
from typing import Any

from ..models import EmploymentInformation
from .utils import clean_value, get_table_extract

logger = logging.getLogger(__name__)

# Column header → field name mapping
EMPLOYMENT_COLUMN_MAP: dict[str, str] = {
    "ACCOUNT": "account",
    "TYPE": "account_type",
    "DATE REPORTED": "date_reported",
    "OCCUPATION CODE": "occupation_code",
    "INCOME": "income",
    "NET / GROSS INCOME INDICATOR": "net_gross_income_indicator",
    "NET / GROSS INCOME\nINDICATOR": "net_gross_income_indicator",
    "MONTHLY / ANNUAL INCOME INDICATOR": "monthly_annual_income_indicator",
    "MONTHLY / ANNUAL\nINCOME INDICATOR": "monthly_annual_income_indicator",
}


def _normalize_header(header: str) -> str:
    """Normalize a column header for matching."""
    return header.strip().upper().replace("\n", " ")


def parse_employment_information(
    boxes: list[dict[str, Any]],
) -> list[EmploymentInformation]:
    """
    Parse the EMPLOYMENT INFORMATION section.

    Returns a list of EmploymentInformation entries.
    """
    entries: list[EmploymentInformation] = []

    for box in boxes:
        table_extract = get_table_extract(box)
        if not table_extract or len(table_extract) < 2:
            continue

        # First row is headers
        headers = table_extract[0]
        col_map: dict[int, str] = {}

        for col_idx, header_cell in enumerate(headers):
            if not header_cell:
                continue
            norm = _normalize_header(header_cell)
            for pattern, field_name in EMPLOYMENT_COLUMN_MAP.items():
                if _normalize_header(pattern) == norm or norm.startswith(
                    _normalize_header(pattern).split("\n")[0]
                ):
                    col_map[col_idx] = field_name
                    break

        # Data rows
        for row in table_extract[1:]:
            fields: dict[str, str | None] = {}
            for col_idx, cell in enumerate(row):
                if col_idx in col_map:
                    fields[col_map[col_idx]] = clean_value(cell)

            if any(v for v in fields.values()):
                entries.append(EmploymentInformation(**fields))

    return entries
