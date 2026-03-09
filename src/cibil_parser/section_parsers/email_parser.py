"""
Parser for the Email Contacts section.

Simple section with just email addresses listed as text.
"""

from __future__ import annotations

import logging
from typing import Any

from ..models import EmailContact
from .utils import clean_value, extract_spans_text

logger = logging.getLogger(__name__)


def parse_email_contacts(boxes: list[dict[str, Any]]) -> list[EmailContact]:
    """
    Parse the EMAIL CONTACT(S) section.

    The section typically has:
    - A section-header box: "EMAIL CONTACT(S):"
    - One or more text boxes with "EMAIL ADDRESS" header and actual email values.
    """
    emails: list[EmailContact] = []
    skip_labels = {"EMAIL ADDRESS", "EMAIL CONTACT(S):"}

    for box in boxes:
        boxclass = box.get("boxclass", "")
        if boxclass == "section-header":
            continue

        spans = extract_spans_text(box)
        for span in spans:
            text = span["text"].strip()
            if text.upper() in skip_labels:
                continue
            val = clean_value(text)
            if val and "@" in val:
                emails.append(EmailContact(email_address=val))
            elif val and val not in skip_labels:
                # Some reports may not have emails but list empty rows
                emails.append(EmailContact(email_address=val))

    return emails
