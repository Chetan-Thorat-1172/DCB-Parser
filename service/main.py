"""
Cloud Run CIBIL Parser Service

Receives CloudEvents from Eventarc (triggered by GCS uploads),
downloads the PDF, runs the existing parser pipeline, writes the
structured JSON to a processed bucket, and publishes a Pub/Sub message.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import tempfile
from pathlib import Path

from flask import Flask, request, make_response
from google.cloud import storage, pubsub_v1
from cloudevents.http import from_http

# ── Parser imports ───────────────────────────────────────────────────────
from cibil_parser.pipeline import parse_pdf, report_to_json

# ── Service config ───────────────────────────────────────────────────────
from config import (
    RAW_PDF_BUCKET,
    PROCESSED_JSON_BUCKET,
    PUBSUB_TOPIC,
    GCP_PROJECT_ID,
    TEMP_DIR,
    LOG_LEVEL,
    extract_report_id,
)

# ── Logging ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    stream=sys.stdout,
)
logger = logging.getLogger("cibil_parser.service")

# ── Flask App ────────────────────────────────────────────────────────────
app = Flask(__name__)

# ── GCP Clients (initialized once, reused across requests) ──────────────
storage_client = storage.Client()
publisher = pubsub_v1.PublisherClient()


# =====================================================================
# Health check
# =====================================================================
@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint for Cloud Run."""
    return {"status": "healthy", "service": "cibil-parser"}, 200


# =====================================================================
# Main endpoint — receives CloudEvent from Eventarc
# =====================================================================
@app.route("/", methods=["POST"])
def handle_event():
    """
    Process a CloudEvent triggered by a GCS object upload.

    Expected CloudEvent data payload:
        {
            "bucket": "dcb-credit-raw-pdf",
            "name": "CIBIL_CN987654_20250627T111900.pdf"
        }
    """
    try:
        # ── 1. Parse the CloudEvent ──────────────────────────────────
        event = from_http(request.headers, request.get_data())
        data = event.data

        bucket_name = data["bucket"]
        file_name = data["name"]

        logger.info(
            "Received event: bucket=%s, file=%s, event_type=%s",
            bucket_name, file_name, event["type"],
        )

        # Skip non-PDF files
        if not file_name.lower().endswith(".pdf"):
            logger.info("Skipping non-PDF file: %s", file_name)
            return {"message": f"Skipped non-PDF file: {file_name}"}, 200

        # ── 2. Extract report_id from file name ─────────────────────
        report_id = extract_report_id(file_name)
        logger.info("Report ID: %s", report_id)

        # ── 3. Download PDF from GCS ─────────────────────────────────
        local_pdf_path = _download_pdf(bucket_name, file_name)
        logger.info("Downloaded PDF to: %s", local_pdf_path)

        # ── 4. Run the parser pipeline ───────────────────────────────
        logger.info("Starting parser pipeline...")
        report = parse_pdf(local_pdf_path)
        json_output = report_to_json(report, indent=2)
        logger.info("Parsing complete. JSON size: %d bytes", len(json_output))

        # ── 5. Upload JSON to processed bucket ───────────────────────
        json_gcs_uri = _upload_json(report_id, json_output)
        logger.info("Uploaded JSON to: %s", json_gcs_uri)

        # ── 6. Publish Pub/Sub message ───────────────────────────────
        source_pdf_uri = f"gs://{bucket_name}/{file_name}"
        _publish_message(report_id, json_gcs_uri, source_pdf_uri)
        logger.info("Published Pub/Sub message for report: %s", report_id)

        # ── 7. Cleanup temp file ─────────────────────────────────────
        try:
            os.unlink(local_pdf_path)
        except OSError:
            pass

        # ── Done ─────────────────────────────────────────────────────
        return {
            "message": "success",
            "report_id": report_id,
            "json_gcs_uri": json_gcs_uri,
            "source_pdf": source_pdf_uri,
        }, 200

    except KeyError as e:
        logger.error("Missing field in event data: %s", e)
        return {"error": f"Missing field: {e}"}, 400

    except Exception as e:
        logger.error("Processing failed: %s", e, exc_info=True)
        return {"error": str(e)}, 500


# =====================================================================
# Helper functions
# =====================================================================

def _download_pdf(bucket_name: str, file_name: str) -> Path:
    """Download a PDF from GCS to a local temp directory."""
    os.makedirs(TEMP_DIR, exist_ok=True)

    # Use a safe local filename
    safe_name = file_name.replace("/", "_")
    local_path = Path(TEMP_DIR) / safe_name

    bucket = storage_client.bucket(bucket_name)
    blob = bucket.blob(file_name)
    blob.download_to_filename(str(local_path))

    return local_path


def _upload_json(report_id: str, json_content: str) -> str:
    """Upload the parsed JSON to the processed GCS bucket."""
    destination_blob_name = f"{report_id}.json"

    bucket = storage_client.bucket(PROCESSED_JSON_BUCKET)
    blob = bucket.blob(destination_blob_name)
    blob.upload_from_string(json_content, content_type="application/json")

    gcs_uri = f"gs://{PROCESSED_JSON_BUCKET}/{destination_blob_name}"
    return gcs_uri


def _publish_message(
    report_id: str, json_gcs_uri: str, source_pdf: str
) -> None:
    """Publish a message to the Pub/Sub topic."""
    project_id = GCP_PROJECT_ID
    if not project_id:
        # Auto-detect from metadata server when running on GCP
        import google.auth
        _, project_id = google.auth.default()

    topic_path = publisher.topic_path(project_id, PUBSUB_TOPIC)

    message_data = {
        "report_id": report_id,
        "json_gcs_uri": json_gcs_uri,
        "source_pdf": source_pdf,
    }

    future = publisher.publish(
        topic_path,
        data=json.dumps(message_data).encode("utf-8"),
        report_id=report_id,  # attribute for filtering
    )
    future.result()  # Block until published
    logger.info("Pub/Sub message ID: %s", future.result())


# =====================================================================
# Entry point
# =====================================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info("Starting CIBIL Parser Service on port %d", port)
    app.run(host="0.0.0.0", port=port, debug=False)
