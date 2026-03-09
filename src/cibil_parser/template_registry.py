"""
Template Detection and Registry.

Supports extensibility by allowing multiple PDF report formats.
Each template defines:
  - A detection function (does this layout match this template?)
  - Section header patterns
  - Section parsers
  - Field mappings

Currently supports: CIBIL
Future: Experian, Equifax, bank-specific templates
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


@dataclass
class ReportTemplate:
    """Definition of a credit report template."""

    name: str
    description: str
    detect: Callable[[dict[str, Any]], bool]
    section_header_patterns: list[tuple[str, str]] = field(default_factory=list)
    version: str = "1.0"


# ---------------------------------------------------------------------------
# Template registry
# ---------------------------------------------------------------------------
_registry: dict[str, ReportTemplate] = {}


def register_template(template: ReportTemplate) -> None:
    """Register a report template in the global registry."""
    _registry[template.name] = template
    logger.info("Registered template: %s (v%s)", template.name, template.version)


def get_template(name: str) -> Optional[ReportTemplate]:
    """Get a template by name."""
    return _registry.get(name)


def detect_template(layout_doc: dict[str, Any]) -> Optional[ReportTemplate]:
    """
    Auto-detect which template matches the given layout document.

    Runs each registered template's detect function and returns the first match.
    """
    for name, template in _registry.items():
        try:
            if template.detect(layout_doc):
                logger.info("Detected template: %s", name)
                return template
        except Exception as e:
            logger.warning("Error detecting template %s: %s", name, e)

    logger.warning("No template matched the document")
    return None


def list_templates() -> list[str]:
    """List all registered template names."""
    return list(_registry.keys())


# ---------------------------------------------------------------------------
# CIBIL Template Detection
# ---------------------------------------------------------------------------
def _detect_cibil(layout_doc: dict[str, Any]) -> bool:
    """
    Detect if a layout document is a CIBIL credit report.

    Detection heuristics:
    1. Document title contains "CIBIL"
    2. Page content contains "CIBIL TRANSUNION" or "CONSUMER CIR"
    3. Section headers match CIBIL patterns
    """
    # Check metadata title
    metadata = layout_doc.get("metadata", {})
    title = (metadata.get("title") or "").upper()
    if "CIBIL" in title:
        return True

    # Check page content
    pages = layout_doc.get("pages", [])
    for page in pages:
        boxes = page.get("boxes", [])
        for box in boxes:
            # Check section headers
            if box.get("boxclass") == "section-header":
                textlines = box.get("textlines", [])
                for tl in textlines:
                    for span in tl.get("spans", []):
                        text = span.get("text", "").upper()
                        if "CONSUMER CIR" in text:
                            return True

            # Check table content for CIBIL-specific markers
            table = box.get("table", {})
            if table:
                extract = table.get("extract", [])
                for row in extract:
                    for cell in (row or []):
                        if cell and "CIBIL TRANSUNION" in cell.upper():
                            return True

    return False


# ---------------------------------------------------------------------------
# Register built-in templates
# ---------------------------------------------------------------------------
CIBIL_TEMPLATE = ReportTemplate(
    name="cibil",
    description="CIBIL TransUnion Consumer Information Report",
    detect=_detect_cibil,
    version="1.0",
)

register_template(CIBIL_TEMPLATE)
