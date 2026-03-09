"""
Stage 1 — PDF Layout Extraction

Converts a CIBIL Credit Report PDF into the PyMuPDF layout JSON representation.
This module wraps PyMuPDF Layout + PyMuPDF4LLM to produce structured layout data.

"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-but-ordered import helper
# ---------------------------------------------------------------------------
_LAYOUT_READY = False


def _ensure_layout_imports() -> None:
    """
    Import ``pymupdf.layout`` then ``pymupdf4llm`` in the correct order.

    Per the official PyMuPDF Layout documentation:
        pymupdf.layout MUST be imported BEFORE pymupdf4llm
        to activate PyMuPDF's layout feature.

    This function is idempotent — subsequent calls are no-ops.
    """
    global _LAYOUT_READY
    if _LAYOUT_READY:
        return

    try:
        import pymupdf.layout  # noqa: F401  — activates layout engine
        logger.debug("pymupdf.layout activated")
    except ImportError:
        logger.warning(
            "pymupdf-layout is not installed. "
            "Install it with: pip install pymupdf-layout"
        )

    try:
        import pymupdf4llm  # noqa: F401
        logger.debug("pymupdf4llm loaded")
    except ImportError:
        logger.warning(
            "pymupdf4llm is not installed. "
            "Install it with: pip install pymupdf4llm"
        )

    _LAYOUT_READY = True


# ---------------------------------------------------------------------------
# Stage 1 — Extract layout JSON from PDF
# ---------------------------------------------------------------------------
def extract_layout_from_pdf(pdf_path: str | Path) -> dict[str, Any]:
    """
    Extract layout-aware JSON from a PDF using PyMuPDF Layout + PyMuPDF4LLM.

    The function:
      1. Imports ``pymupdf.layout`` (layout engine) then ``pymupdf4llm``.
      2. Opens the PDF as a ``pymupdf`` Document object.
      3. Calls ``pymupdf4llm.to_json(doc)`` to get structured layout JSON.

    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF not found: {pdf_path}")

    # Ensure correct import order: pymupdf.layout → pymupdf4llm
    _ensure_layout_imports()

    try:
        import pymupdf          # core library
        import pymupdf4llm      # extraction API (layout-enhanced)

        logger.info("Extracting layout JSON from %s", pdf_path)

        # Open the PDF as a Document object — pymupdf4llm.to_json() expects this
        doc = pymupdf.open(str(pdf_path))

        # Extract structured layout JSON via PyMuPDF4LLM
        # With pymupdf.layout imported, this uses the layout engine automatically
        layout_json = pymupdf4llm.to_json(doc)

        doc.close()

        # pymupdf4llm.to_json returns a JSON *string* — parse it
        if isinstance(layout_json, str):
            return json.loads(layout_json)
        return layout_json

    except ImportError as exc:
        logger.warning(
            "pymupdf4llm / pymupdf not available (%s), "
            "falling back to raw pymupdf extraction",
            exc,
        )
        return _extract_with_raw_pymupdf(pdf_path)


def _extract_with_raw_pymupdf(pdf_path: Path) -> dict[str, Any]:
    """
    Fallback extraction using only raw pymupdf (no layout engine).

    This produces a minimal structure without box classification or table
    detection — sufficient for basic text but not for reliable section parsing.
    """
    import pymupdf

    doc = pymupdf.open(str(pdf_path))
    pages = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        text_dict = page.get_text("dict", sort=True)
        pages.append(
            {
                "page_number": page_num + 1,
                "width": page.rect.width,
                "height": page.rect.height,
                "boxes": [],  # raw fallback has no box classification
                "fulltext": text_dict.get("blocks", []),
            }
        )
    doc.close()
    return {
        "filename": str(pdf_path),
        "page_count": len(pages),
        "pages": pages,
        "metadata": {},
    }


# Load a pre-extracted layout JSON file.
def load_layout_from_json(json_path: str | Path) -> dict[str, Any]:

    json_path = Path(json_path)
    if not json_path.exists():
        raise FileNotFoundError(f"Layout JSON not found: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        return json.load(f)


# Merge multiple per-page layout JSONs into a single document.
def merge_layout_jsons(*json_paths: str | Path) -> dict[str, Any]:
    
    if not json_paths:
        raise ValueError("At least one JSON path is required")

    first = load_layout_from_json(json_paths[0])
    all_pages = list(first.get("pages", []))

    seen_page_numbers = {p["page_number"] for p in all_pages}

    for jp in json_paths[1:]:
        doc = load_layout_from_json(jp)
        for page in doc.get("pages", []):
            if page["page_number"] not in seen_page_numbers:
                all_pages.append(page)
                seen_page_numbers.add(page["page_number"])

    all_pages.sort(key=lambda p: p["page_number"])
    first["pages"] = all_pages
    first["page_count"] = len(all_pages)
    return first
