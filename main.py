"""ElectionSMS — main entry point.

Orchestrates the contact-reading, validation, and summary-reporting
pipeline.  No SMS messages are sent from this module.
"""

import sys

from config import EXCEL_FILE, MESSAGE_FILE
from excel_reader import read_contacts
from message_reader import read_message
from models import Contact
from utils import print_contact_preview, print_header, print_message_preview, print_summary
from validator import ValidationResult, validate_contacts


def main() -> None:
    """Run the full read → validate → report pipeline."""
    print_header()

    # ── Step 1: Read contacts from Excel ─────────────────────────────
    try:
        contacts: list[Contact] = read_contacts(EXCEL_FILE)
    except FileNotFoundError as exc:
        print(f"  [ERROR] {exc}")
        sys.exit(1)
    except ValueError as exc:
        print(f"  [ERROR] {exc}")
        sys.exit(1)

    total_contacts: int = len(contacts)

    # ── Step 2: Validate contacts ────────────────────────────────────
    result: ValidationResult = validate_contacts(contacts)

    # ── Step 3: Read SMS message template ────────────────────────────
    try:
        message: str = read_message(MESSAGE_FILE)
    except (FileNotFoundError, ValueError, UnicodeDecodeError) as exc:
        print(f"  [ERROR] {exc}")
        sys.exit(1)

    # ── Step 4: Display professional summary ─────────────────────────
    print_summary(total_contacts, result)
    print_contact_preview(result.valid_contacts)
    print_message_preview(message)

    print("  ⚠  No SMS messages were sent. This is a dry-run report only.")
    print()


if __name__ == "__main__":
    main()