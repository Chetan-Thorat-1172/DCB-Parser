"""
Parser for the Account(s) section.

This is the most complex parser because:
1. Account data spans multiple pages
2. Each account is a sub-table with a repeating 4-column structure:
   ACCOUNT | DATES | AMOUNTS | STATUS
3. The first account on page 1 may be missing some fields that overflow to page 2
4. DPD (Days Past Due) history appears between account blocks
5. A single large table box may contain multiple account blocks

Account block detection strategy:
- Look for rows containing "MEMBER NAME:" — this signals a new account
- Each account has 5-8 rows of key:value data
- DPD rows contain month-year codes and "000" values
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from ..models import Account, DaysPaymentHistory
from .utils import clean_value, extract_spans_text, get_table_extract, safe_int, split_label_value

logger = logging.getLogger(__name__)

# Field mapping: LABEL → Account attribute name
# These labels appear in table cells as "LABEL:VALUE"
ACCOUNT_FIELD_MAP: dict[str, str] = {
    "MEMBER NAME": "member_name",
    "ACCOUNT NUMBER": "account_number",
    "TYPE": "account_type",
    "OWNERSHIP": "ownership",
    "OPENED": "opened_date",
    "REPORTED AND CERTIFIED": "reported_and_certified",
    "PMT HIST START": "pmt_hist_start",
    "PMT HIST END": "pmt_hist_end",
    "LAST PAYMENT": "last_payment_date",
    "HIGH CREDIT AMOUNT": "high_credit_amount",
    "CURRENT BALANCE": "current_balance",
    "EMI": "emi",
    "PAYMENT FREQUENCY": "payment_frequency",
    "REPAYMENT TENURE": "repayment_tenure",
    "AMOUNT OVERDUE": "amount_overdue",
    "ACCOUNT CLOSED": "account_closed_date",
}

# Fields that should be parsed as integers
INT_FIELDS = {
    "high_credit_amount",
    "current_balance",
    "emi",
    "repayment_tenure",
    "amount_overdue",
}

# Pattern to detect DPD date headers like "06-25", "05-25\n04-25"
DPD_DATE_PATTERN = re.compile(r"^\d{2}-\d{2}(?:\n\d{2}-\d{2})*$")

# Pattern to detect DPD values like "000", "000\n000"
DPD_VALUE_PATTERN = re.compile(r"^(?:(?:000|XXX|\d{1,3})\n?)+$")


def _is_dpd_row(row: list[Optional[str]]) -> bool:
    """Check if a row contains DPD date headers or DPD values."""
    non_empty = [c for c in row if c and c.strip()]
    if not non_empty:
        return False
    return all(
        DPD_DATE_PATTERN.match(c.strip()) or DPD_VALUE_PATTERN.match(c.strip())
        for c in non_empty
    )


def _is_account_header_row(row: list[Optional[str]]) -> bool:
    """Check if a row is the ACCOUNT | DATES | AMOUNTS | STATUS header."""
    cells = [(c or "").strip().upper() for c in row]
    return "ACCOUNT" in cells and ("DATES" in cells or "AMOUNTS" in cells)


def _is_days_past_due_label(row: list[Optional[str]]) -> bool:
    """Check if a row contains 'DAYS PAST DUE' label."""
    combined = " ".join((c or "") for c in row).upper()
    return "DAYS PAST DUE" in combined


def _extract_field_from_cell(cell: str, account: Account) -> None:
    """
    Extract a field from a cell containing 'LABEL:VALUE'.

    Handles variations like:
    - "MEMBER NAME:BAJAJ FIN LTD"
    - "ACCOUNT CLOSED: NA"
    - "PAYMENT FREQUENCY: 03"
    - "Amount Overdue:0"  (mixed case)
    """
    if not cell or ":" not in cell:
        return

    label, value = split_label_value(cell)
    label_upper = label.upper().strip()

    # Try direct match first
    field_name = ACCOUNT_FIELD_MAP.get(label_upper)

    # Try partial match
    if not field_name:
        for map_label, fname in ACCOUNT_FIELD_MAP.items():
            if map_label in label_upper or label_upper in map_label:
                field_name = fname
                break

    if not field_name:
        return

    # Clean and set the value
    if field_name in INT_FIELDS:
        int_val = safe_int(value)
        setattr(account, field_name, int_val)
    else:
        cleaned = clean_value(value)
        # For account_closed_date, normalize "NA" to None
        if field_name == "account_closed_date" and cleaned and cleaned.upper() == "NA":
            cleaned = None
        setattr(account, field_name, cleaned)


def _parse_dpd_rows(
    date_row: list[Optional[str]], value_row: list[Optional[str]]
) -> list[DaysPaymentHistory]:
    """
    Parse paired DPD rows (date headers + values).

    Date row: ["06-25\n05-25", "04-25", ...]
    Value row: ["000\n000", "000", ...]
    """
    dpd_entries: list[DaysPaymentHistory] = []

    for col_idx in range(min(len(date_row), len(value_row))):
        date_cell = (date_row[col_idx] or "").strip()
        value_cell = (value_row[col_idx] or "").strip()

        if not date_cell:
            continue

        dates = date_cell.split("\n")
        values = value_cell.split("\n") if value_cell else []

        for i, d in enumerate(dates):
            d = d.strip()
            if not d:
                continue
            v = values[i].strip() if i < len(values) else None
            dpd_entries.append(DaysPaymentHistory(month_year=d, dpd_value=v))

    return dpd_entries


def _parse_account_block(
    rows: list[list[Optional[str]]],
) -> Account:
    """
    Parse a block of rows belonging to a single account.

    A block consists of:
    - (optional) ACCOUNT|DATES|AMOUNTS|STATUS header row
    - 4-8 data rows with LABEL:VALUE cells
    """
    account = Account()

    for row in rows:
        for cell in row:
            if not cell:
                continue
            cell_stripped = cell.strip()
            if ":" in cell_stripped:
                _extract_field_from_cell(cell_stripped, account)

    # Handle split "PAYMENT" + "FREQUENCY: 03" across cells
    # This happens when columns shift
    return account


def _merge_page_header_into_account(
    account: Account, boxes: list[dict[str, Any]]
) -> None:
    """
    Handle page-header boxes that carry continuation fields from the previous page.

    On page 2, the top of the page may have:
    - "Amount Overdue: 0"
    - "LAST PAYMENT: 2025-06-02"
    - "REPAYMENT TENURE: 48"
    """
    for box in boxes:
        if box.get("boxclass") != "page-header":
            continue
        spans = extract_spans_text(box)
        combined_text = " ".join(s["text"] for s in spans)
        if ":" in combined_text:
            _extract_field_from_cell(combined_text, account)


def parse_accounts(boxes: list[dict[str, Any]]) -> list[Account]:
    """
    Parse the ACCOUNT(S) section into a list of Account objects.

    Handles:
    - Multi-page account data
    - Multiple accounts in a single table box
    - DPD history rows
    - Page-header continuation fields
    """
    accounts: list[Account] = []
    pending_dpd_dates: list[list[Optional[str]]] = []
    pending_dpd_values: list[list[Optional[str]]] = []

    # Separate page-header boxes (for first account continuation)
    page_header_boxes = [b for b in boxes if b.get("boxclass") == "page-header"]
    content_boxes = [b for b in boxes if b.get("boxclass") != "page-header"]

    for box in content_boxes:
        boxclass = box.get("boxclass", "")

        # Skip section headers and text labels
        if boxclass == "section-header":
            continue

        # Handle "DAYS PAST DUE" text labels (not in table)
        if boxclass == "text":
            text = ""
            spans = extract_spans_text(box)
            for s in spans:
                text += s["text"] + " "
            # Skip — just a label before the DPD table
            continue

        table_extract = get_table_extract(box)
        if not table_extract:
            continue

        # Process this table — may contain multiple account blocks
        current_block_rows: list[list[Optional[str]]] = []
        in_dpd_section = False
        dpd_date_rows: list[list[Optional[str]]] = []
        dpd_value_rows: list[list[Optional[str]]] = []

        for row_idx, row in enumerate(table_extract):
            # Skip completely empty rows
            non_empty_cells = [c for c in row if c and c.strip()]
            if not non_empty_cells:
                continue

            combined = " ".join((c or "") for c in row).strip().upper()

            # Check for DPD section label
            if _is_days_past_due_label(row):
                in_dpd_section = False  # will be set by subsequent DPD rows
                continue

            # Check if this is a DPD row (date headers or values)
            if _is_dpd_row(row):
                # Determine if dates or values
                first_non_empty = ""
                for c in row:
                    if c and c.strip():
                        first_non_empty = c.strip()
                        break

                if DPD_DATE_PATTERN.match(first_non_empty):
                    dpd_date_rows.append(row)
                else:
                    dpd_value_rows.append(row)
                continue

            # Check for account header row
            if _is_account_header_row(row):
                # If we have a pending block, finalize it
                if current_block_rows:
                    account = _parse_account_block(current_block_rows)
                    # Attach any pending DPD data
                    if dpd_value_rows and dpd_date_rows:
                        for dr, vr in zip(dpd_date_rows, dpd_value_rows):
                            account.days_past_due.extend(_parse_dpd_rows(dr, vr))
                    if account.member_name or account.account_number:
                        accounts.append(account)
                    current_block_rows = []
                    dpd_date_rows = []
                    dpd_value_rows = []
                continue

            # Check if this row starts a new account block (MEMBER NAME:)
            if "MEMBER NAME:" in combined:
                # Save previous block
                if current_block_rows:
                    account = _parse_account_block(current_block_rows)
                    if dpd_value_rows and dpd_date_rows:
                        for dr, vr in zip(dpd_date_rows, dpd_value_rows):
                            account.days_past_due.extend(_parse_dpd_rows(dr, vr))
                    if account.member_name or account.account_number:
                        accounts.append(account)
                    dpd_date_rows = []
                    dpd_value_rows = []
                current_block_rows = [row]
                continue

            # Add to current block
            current_block_rows.append(row)

        # Finalize last block in this table
        if current_block_rows:
            account = _parse_account_block(current_block_rows)
            if dpd_value_rows and dpd_date_rows:
                for dr, vr in zip(dpd_date_rows, dpd_value_rows):
                    account.days_past_due.extend(_parse_dpd_rows(dr, vr))
            if account.member_name or account.account_number:
                accounts.append(account)

    # Merge page-header continuation data into the first account
    if accounts and page_header_boxes:
        _merge_page_header_into_account(accounts[0], page_header_boxes)

    # Post-processing: handle split PAYMENT FREQUENCY across cells
    for acct in accounts:
        if acct.payment_frequency is None:
            # Check if it was split across cells — already handled by _extract_field_from_cell
            pass

    logger.info("Parsed %d accounts", len(accounts))
    return accounts
