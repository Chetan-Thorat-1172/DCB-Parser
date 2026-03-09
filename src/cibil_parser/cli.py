"""
CLI entry point for the CIBIL Credit Report Parser.

Usage:
    cibil-parser credit_report.pdf -o output.json
    cibil-parser --from-layout layout.json -o output.json
    cibil-parser --from-layouts page1.json page2.json -o output.json
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

from .pipeline import (
    parse_layout_json,
    parse_layout_jsons,
    parse_pdf,
    report_to_json,
)


def _setup_logging(verbose: bool = False) -> None:
    """Configure logging for the CLI."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def main(argv: list[str] | None = None) -> None:
    """CLI main entry point."""
    parser = argparse.ArgumentParser(
        prog="cibil-parser",
        description="Parse CIBIL Credit Report PDFs into structured JSON",
    )

    # Input source (mutually exclusive)
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        "pdf_path",
        nargs="?",
        type=str,
        help="Path to the CIBIL credit report PDF",
    )
    input_group.add_argument(
        "--from-layout",
        type=str,
        metavar="JSON_PATH",
        help="Path to a pre-extracted PyMuPDF layout JSON file",
    )
    input_group.add_argument(
        "--from-layouts",
        type=str,
        nargs="+",
        metavar="JSON_PATH",
        help="Paths to per-page layout JSON files (will be merged)",
    )

    # Output
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="Output file path for the structured JSON (default: stdout)",
    )

    # Options
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation level (default: 2)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose/debug logging",
    )

    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    logger = logging.getLogger("cibil_parser.cli")

    try:
        # Parse based on input type
        if args.from_layout:
            logger.info("Parsing from layout JSON: %s", args.from_layout)
            report = parse_layout_json(args.from_layout)
        elif args.from_layouts:
            logger.info(
                "Parsing from %d layout JSON files", len(args.from_layouts)
            )
            report = parse_layout_jsons(*args.from_layouts)
        else:
            logger.info("Parsing PDF: %s", args.pdf_path)
            report = parse_pdf(args.pdf_path)

        # Serialize
        json_output = report_to_json(report, indent=args.indent)

        # Write output
        if args.output:
            output_path = Path(args.output)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(json_output, encoding="utf-8")
            logger.info("Output written to: %s", output_path)
        else:
            print(json_output)

    except FileNotFoundError as e:
        logger.error("File not found: %s", e)
        sys.exit(1)
    except Exception as e:
        logger.error("Parsing failed: %s", e, exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
