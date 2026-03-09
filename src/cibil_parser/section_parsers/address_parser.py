"""
Parser for the Address(es) section.

Addresses appear in a table where each address occupies 2 rows:
  Row A: ADDRESS : <full address string>
  Row B: CATEGORY: XX | RESIDENCE CODE: YY | DATE REPORTED: YYYY-MM-DD

Some addresses have the category embedded in the same cell as the address.
"""

from __future__ import annotations

import logging
import re
from typing import Any, Optional

from ..models import Address
from .utils import clean_value, get_table_extract, split_label_value

logger = logging.getLogger(__name__)


def parse_addresses(boxes: list[dict[str, Any]]) -> list[Address]:
    """
    Parse the ADDRESS(ES) section.

    Strategy:
    1. Find table boxes in the section.
    2. Walk rows in pairs: address row + metadata row.
    3. Handle cases where CATEGORY is embedded in the address row.
    """
    addresses: list[Address] = []

    for box in boxes:
        table_extract = get_table_extract(box)
        if not table_extract:
            continue

        current_address: Optional[Address] = None

        for row in table_extract:
            combined = " ".join((c or "") for c in row).strip()
            combined_upper = combined.upper()

            # Detect an address row
            if combined_upper.startswith("ADDRESS"):
                # Save previous address if any
                if current_address and current_address.address:
                    addresses.append(current_address)

                current_address = Address()

                # Extract the address string
                for cell in row:
                    if cell and cell.strip().upper().startswith("ADDRESS"):
                        addr_text = cell.strip()
                        # Remove "ADDRESS : " or "ADDRESS:" prefix
                        addr_text = re.sub(
                            r"^ADDRESS\s*:\s*", "", addr_text, flags=re.IGNORECASE
                        )

                        # Check if CATEGORY is embedded in the same cell
                        cat_match = re.search(
                            r"CATEGORY:\s*(\d+)", addr_text, re.IGNORECASE
                        )
                        if cat_match:
                            current_address.category = cat_match.group(1)
                            addr_text = addr_text[: cat_match.start()].strip()

                        # Extract state code and pin code from address string
                        # Pattern: ", ,XX, XXXXXX" at the end
                        addr_parts_match = re.search(
                            r",\s*,\s*(\d{1,2})\s*,\s*(\d{6})\s*$", addr_text
                        )
                        if addr_parts_match:
                            current_address.state_code = addr_parts_match.group(1)
                            current_address.pin_code = addr_parts_match.group(2)
                            addr_text = addr_text[: addr_parts_match.start()].strip()

                        current_address.address = clean_value(addr_text)
                        break

            # Detect a metadata row (CATEGORY / RESIDENCE CODE / DATE REPORTED)
            elif "CATEGORY" in combined_upper or "RESIDENCE CODE" in combined_upper or "DATE REPORTED" in combined_upper:
                if not current_address:
                    current_address = Address()

                for cell in row:
                    if not cell:
                        continue
                    cell_stripped = cell.strip()
                    cell_upper = cell_stripped.upper()

                    if "CATEGORY:" in cell_upper:
                        _, val = split_label_value(cell_stripped)
                        if val:
                            current_address.category = clean_value(val)

                    if "RESIDENCE CODE:" in cell_upper:
                        _, val = split_label_value(cell_stripped)
                        if val:
                            current_address.residence_code = clean_value(val)

                    if "DATE REPORTED:" in cell_upper:
                        _, val = split_label_value(cell_stripped)
                        if val:
                            current_address.date_reported = clean_value(val)

        # Don't forget the last address
        if current_address and current_address.address:
            addresses.append(current_address)

    return addresses
