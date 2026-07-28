"""Utility and display helpers.

Provides formatted output functions used by main.py for printing
the professional summary report.

Device diagnostics have moved to :mod:`diagnostics`.
"""

import sys

from config import APP_NAME, PREVIEW_COUNT, SEPARATOR
from models import Contact
from validator import ValidationResult

# Reconfigure stdout to handle UTF-8 (Marathi / Devanagari) on Windows
# consoles that default to CP1252 or similar legacy code pages.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]


def print_header() -> None:
    """Print the application header banner."""
    print()
    print(SEPARATOR)
    print(f"  {APP_NAME}")
    print(SEPARATOR)
    print()


def print_summary(
    total: int,
    result: ValidationResult,
) -> None:
    """Print a summary of contact validation statistics.

    Args:
        total: Total number of raw contacts read from Excel.
        result: The :class:`ValidationResult` from the validator.
    """
    print(f"  Total contacts:              {total}")
    print(f"  Valid contacts:              {len(result.valid_contacts)}")
    print(f"  Invalid contacts:            {len(result.invalid_contacts)}")
    print(f"  Duplicate contacts removed:  {result.duplicates_removed}")
    print()


def print_contact_preview(contacts: list[Contact], count: int = PREVIEW_COUNT) -> None:
    """Print a table-style preview of the first *count* contacts.

    Args:
        contacts: The list of valid contacts.
        count: Number of contacts to preview (default from config).
    """
    preview: list[Contact] = contacts[:count]

    print(f"  Preview — first {len(preview)} contacts:")
    print(f"  {'No.':<6} {'Name':<35} {'Mobile'}")
    print(f"  {'-' * 6} {'-' * 35} {'-' * 12}")

    for contact in preview:
        print(f"  {contact.serial_no:<6} {contact.advocate_name:<35} {contact.mobile_number}")
    print()


def print_message_preview(message: str) -> None:
    """Print a preview of the SMS message body.

    Args:
        message: The message text to display.
    """
    print("  Message Preview:")
    print(f"  {'-' * 16}")
    print()
    for line in message.splitlines():
        print(f"  {line}")
    print()
    print(SEPARATOR)
    print()
