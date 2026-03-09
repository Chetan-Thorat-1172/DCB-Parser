"""
Configuration for the Cloud Run CIBIL Parser Service.

All values can be overridden via environment variables.
"""

from __future__ import annotations

import os
import re


# ── GCS Buckets ──────────────────────────────────────────────────────────
RAW_PDF_BUCKET = os.environ.get("RAW_PDF_BUCKET", "dcb-credit-raw-pdf")
PROCESSED_JSON_BUCKET = os.environ.get("PROCESSED_JSON_BUCKET", "dcb-credit-processed-json")

# ── Pub/Sub ──────────────────────────────────────────────────────────────
PUBSUB_TOPIC = os.environ.get("PUBSUB_TOPIC", "cibil-pdf-parsed")
GCP_PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "")

# ── Temp directory for downloaded PDFs ───────────────────────────────────
TEMP_DIR = os.environ.get("TEMP_DIR", "/tmp/cibil-parser")

# ── Logging ──────────────────────────────────────────────────────────────
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO")


def extract_report_id(file_name: str) -> str:
    """
    Extract report_id from a CIBIL PDF file name.

    Expected format:
        CIBIL_CN987654_20250627T111900.pdf
    Result:
        CN987654_20250627T111900

    Falls back to stripping the extension if the pattern doesn't match.
    """
    # Try the expected pattern: CIBIL_<report_id>.pdf
    match = re.match(r"^CIBIL_(.+)\.pdf$", file_name, re.IGNORECASE)
    if match:
        return match.group(1)

    # Fallback: just strip the extension
    stem = os.path.splitext(file_name)[0]
    return stem
