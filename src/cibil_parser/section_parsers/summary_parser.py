"""
Parser for the Summary section.

The summary section contains two sub-tables:
1. ACCOUNT(S) summary — totals, balances, dates
2. ENQUIRIES summary — counts by time period
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from ..models import AccountSummary, EnquirySummary, Summary
from .utils import clean_value, get_table_extract, safe_int, split_label_value

logger = logging.getLogger(__name__)


def parse_summary(boxes: list[dict[str, Any]]) -> Summary:
    """
    Parse the SUMMARY section.

    The summary appears as a table with two logical sub-tables:
    - Account summary rows (TOTAL, HIGH CR/SANC. AMT, CURRENT, OVERDUE, ZERO-BALANCE, dates)
    - Enquiry summary rows (TOTAL, PAST 30 DAYS, PAST 12 MONTHS, etc.)
    """
    acct_summary = AccountSummary()
    enq_summary = EnquirySummary()

    for box in boxes:
        table_extract = get_table_extract(box)
        if not table_extract:
            continue

        current_sub = "accounts"  # Start with accounts sub-section

        for row in table_extract:
            combined = " ".join((c or "") for c in row).strip()
            combined_upper = combined.upper()

            # Detect sub-section switch
            if "ENQUIR" in combined_upper and "PURPOSE" in combined_upper:
                current_sub = "enquiries"
                continue

            if current_sub == "accounts":
                _parse_account_summary_row(row, acct_summary)
            else:
                _parse_enquiry_summary_row(row, enq_summary)

    return Summary(account_summary=acct_summary, enquiry_summary=enq_summary)


def _extract_kv_from_cell(cell: str) -> dict[str, str]:
    """
    Extract key:value pairs from a cell that may contain multiple lines.

    Example cell: "TOTAL:4\nHIGH CR/SANC. AMT:696624"
    Returns: {"TOTAL": "4", "HIGH CR/SANC. AMT": "696624"}
    """
    result = {}
    lines = cell.split("\n")
    for line in lines:
        line = line.strip()
        if ":" in line:
            key, val = split_label_value(line)
            if key and val:
                result[key.upper()] = val
    return result


def _parse_account_summary_row(
    row: list[Optional[str]], summary: AccountSummary
) -> None:
    """Parse a single row from the accounts summary."""
    for cell in row:
        if not cell:
            continue

        cell_stripped = cell.strip()
        cell_upper = cell_stripped.upper()

        # Skip header rows
        if cell_upper in ("ACCOUNT(S)", "ACCOUNT TYPE", "ACCOUNTS", "BALANCES", "DATE OPENED"):
            continue

        if cell_upper == "ALL ACCOUNTS":
            summary.account_type = "All Accounts"
            continue

        # Parse key:value pairs in cell
        kvs = _extract_kv_from_cell(cell_stripped)

        for key, val in kvs.items():
            if key == "TOTAL":
                summary.total_accounts = safe_int(val)
            elif "HIGH CR" in key or "SANC" in key:
                summary.high_credit_sanctioned_amount = safe_int(val)
            elif key == "CURRENT":
                summary.current_balance = safe_int(val)
            elif key == "OVERDUE" and summary.overdue_accounts is None:
                summary.overdue_accounts = safe_int(val)
            elif key == "OVERDUE" and summary.overdue_accounts is not None:
                summary.overdue_balance = safe_int(val)
            elif "ZERO" in key:
                summary.zero_balance_accounts = safe_int(val)
            elif key == "RECENT":
                summary.recent_date_opened = clean_value(val)
            elif key == "OLDEST":
                summary.oldest_date_opened = clean_value(val)

        # Handle "OVERDUE:0" appearing in different columns
        if "OVERDUE:" in cell_upper:
            _, ov_val = split_label_value(cell_stripped)
            if summary.overdue_accounts is None:
                summary.overdue_accounts = safe_int(ov_val)
            elif summary.overdue_balance is None:
                summary.overdue_balance = safe_int(ov_val)


def _parse_enquiry_summary_row(
    row: list[Optional[str]], summary: EnquirySummary
) -> None:
    """Parse a single row from the enquiries summary."""
    cells = [(c.strip() if c else "") for c in row]

    first = cells[0] if cells else ""

    if first.upper().startswith("ALL ENQUIR"):
        summary.enquiry_purpose = "All Enquiries"
        if len(cells) > 1 and cells[1]:
            summary.total = safe_int(cells[1])
        if len(cells) > 2 and cells[2]:
            summary.past_12_months = safe_int(cells[2])
        if len(cells) > 3 and cells[3]:
            summary.past_24_months = safe_int(cells[3])
