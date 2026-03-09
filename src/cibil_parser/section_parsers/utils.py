"""
Shared utility functions used by all section parsers.
"""

from __future__ import annotations

import re
from typing import Any, Optional


def extract_spans_text(box: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Extract all spans from a box's textlines, preserving positional info.

    Returns a list of dicts: {"text": str, "x0": float, "y0": float, ...}
    """
    spans_out = []
    textlines = box.get("textlines") or []
    for tl in textlines:
        for span in tl.get("spans", []):
            bbox = span.get("bbox", [0, 0, 0, 0])
            spans_out.append(
                {
                    "text": span.get("text", "").strip(),
                    "font": span.get("font", ""),
                    "color": span.get("color", 0),
                    "size": span.get("size", 0),
                    "x0": bbox[0] if len(bbox) > 0 else 0,
                    "y0": bbox[1] if len(bbox) > 1 else 0,
                    "x1": bbox[2] if len(bbox) > 2 else 0,
                    "y1": bbox[3] if len(bbox) > 3 else 0,
                }
            )
    return spans_out


def get_table_extract(box: dict[str, Any]) -> list[list[Optional[str]]]:
    """Return the table extract grid from a box, or empty list."""
    table = box.get("table")
    if table and table.get("extract"):
        return table["extract"]
    return []


def split_label_value(text: str, separator: str = ":") -> tuple[str, str]:
    """
    Split a 'LABEL:VALUE' string into (label, value).

    Handles cases like:
        'MEMBER NAME:BAJAJ FIN LTD' → ('MEMBER NAME', 'BAJAJ FIN LTD')
        'OPENED:2025-04-23' → ('OPENED', '2025-04-23')
        'ACCOUNT CLOSED: NA' → ('ACCOUNT CLOSED', 'NA')
    """
    if separator not in text:
        return text.strip(), ""
    idx = text.index(separator)
    label = text[:idx].strip()
    value = text[idx + 1 :].strip()
    return label, value


def clean_value(value: str | None) -> str | None:
    """Strip whitespace and return None for empty/missing values."""
    if value is None:
        return None
    value = value.strip()
    if not value or value.upper() in ("", "NOT AVAILABLE", "NA", "N/A"):
        return None
    return value


def safe_int(value: str | None) -> int | None:
    """Parse an integer, returning None on failure."""
    if value is None:
        return None
    value = value.strip().replace(",", "")
    try:
        return int(float(value))
    except (ValueError, TypeError):
        return None


def normalize_label(label: str) -> str:
    """
    Normalize a label for matching:
    - Uppercase
    - Strip special chars
    - Collapse whitespace
    """
    label = label.upper().strip()
    label = re.sub(r"[^A-Z0-9\s/]", "", label)
    label = re.sub(r"\s+", " ", label)
    return label


def find_label_value_in_row(
    row: list[Optional[str]], label_pattern: str
) -> Optional[str]:
    """
    Search a table row for a cell matching label_pattern and return the value
    from the next non-empty cell, or extract value from 'LABEL: VALUE' format.
    """
    for i, cell in enumerate(row):
        if cell is None:
            continue
        cell_stripped = cell.strip()
        if re.search(label_pattern, cell_stripped, re.IGNORECASE):
            # Check if value is embedded: "LABEL: VALUE"
            if ":" in cell_stripped:
                _, val = split_label_value(cell_stripped)
                if val:
                    return val
            # Otherwise look at next non-empty cells
            for j in range(i + 1, len(row)):
                if row[j] and row[j].strip():
                    return row[j].strip()
    return None
