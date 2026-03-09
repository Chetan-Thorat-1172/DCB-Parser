"""
Parser for the Report Header section.

Extracts metadata fields from the report header area:
  - Consumer name
  - Member ID
  - Member Reference Number
  - Report Date / Time
  - Control Number
"""

from __future__ import annotations

import logging
from typing import Any

from ..models import ReportMetadata
from .utils import clean_value, extract_spans_text

logger = logging.getLogger(__name__)

# Label-to-field mapping for header key-value pairs.
# The label color in the PDF is 42964 (a teal/green), values are 0 (black).
HEADER_LABEL_MAP: dict[str, str] = {
    "CONSUMER": "consumer_name",
    "MEMBER ID": "member_id",
    "MEMBER REFERENCE NUMBER": "member_reference_number",
    "DATE": "report_date",
    "TIME": "report_time",
    "CONTROL NUMBER": "control_number",
}


def parse_report_header(boxes: list[dict[str, Any]]) -> ReportMetadata:
    """
    Parse the report header boxes into ReportMetadata.

    The header uses label/value spans where:
    - Labels are in color=42964 (teal), font Arial-BoldMT
    - Values are in color=0 (black), font Arial-BoldMT
    - Labels end with ':'
    - Value span follows the label span on the same line
    """
    fields: dict[str, str | None] = {}

    for box in boxes:
        boxclass = box.get("boxclass", "")
        if boxclass in ("section-header", "picture"):
            continue

        spans = extract_spans_text(box)

        # Pair up label and value spans
        i = 0
        while i < len(spans):
            span = spans[i]
            text = span["text"]

            # Check if this is a label (ends with ':')
            if text.endswith(":"):
                label_key = text.rstrip(":").strip().upper()
                field_name = HEADER_LABEL_MAP.get(label_key)

                if field_name:
                    # Look for value in the next span (or same line)
                    value = None
                    if i + 1 < len(spans):
                        next_span = spans[i + 1]
                        # Value should be on approximately the same Y line
                        if abs(next_span["y0"] - span["y0"]) < 5:
                            value = next_span["text"]
                            i += 1

                    fields[field_name] = clean_value(value)

            # Check for consumer name as a standalone value box
            # (The consumer name appears in a separate text box next to "CONSUMER:" label)
            elif span.get("color") == 0 and not text.endswith(":"):
                # Could be the consumer name if it's near the CONSUMER label
                if "consumer_name" not in fields and span.get("x0", 0) > 100:
                    if span.get("y0", 0) < 130:  # In the header region
                        fields["consumer_name"] = clean_value(text)

            i += 1

    return ReportMetadata(**fields)
