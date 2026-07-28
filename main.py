"""ElectionSMS — main entry point.

Orchestrates the contact-reading, validation, device-verification,
and summary-reporting pipeline.  No SMS messages are sent from this module.
"""

import logging
import sys

from config import EXCEL_FILE, LOG_DIR, MESSAGE_FILE
from diagnostics import DiagnosticsReport, run_diagnostics
from excel_reader import read_contacts
from exceptions import (
    ADBCommandError,
    ADBNotFoundError,
    ADBTimeoutError,
    DeviceUnauthorizedError,
    MultipleDevicesError,
    NoDeviceConnectedError,
)
from message_reader import read_message
from models import Contact
from utils import (
    print_contact_preview,
    print_header,
    print_message_preview,
    print_summary,
)
from validator import ValidationResult, validate_contacts

# ── Logging configuration ────────────────────────────────────────────
LOG_DIR.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(name)s  %(message)s",
    handlers=[
        logging.FileHandler(LOG_DIR / "election_sms.log", encoding="utf-8"),
    ],
)
logger: logging.Logger = logging.getLogger(__name__)


def main() -> None:
    """Run the full read → validate → device-check → report pipeline."""
    logger.info("Application started.")
    print_header()

    # ── Step 1: Read contacts from Excel ─────────────────────────────
    try:
        contacts: list[Contact] = read_contacts(EXCEL_FILE)
    except FileNotFoundError as exc:
        logger.error("Excel file error: %s", exc)
        print(f"  [ERROR] {exc}")
        sys.exit(1)
    except ValueError as exc:
        logger.error("Excel column error: %s", exc)
        print(f"  [ERROR] {exc}")
        sys.exit(1)

    total_contacts: int = len(contacts)

    # ── Step 2: Validate contacts ────────────────────────────────────
    result: ValidationResult = validate_contacts(contacts)
    logger.info(
        "Validation: %d valid, %d invalid, %d duplicates removed.",
        len(result.valid_contacts),
        len(result.invalid_contacts),
        result.duplicates_removed,
    )

    # ── Step 3: Read SMS message template ────────────────────────────
    try:
        message: str = read_message(MESSAGE_FILE)
    except (FileNotFoundError, ValueError, UnicodeDecodeError) as exc:
        logger.error("Message file error: %s", exc)
        print(f"  [ERROR] {exc}")
        sys.exit(1)

    # ── Step 4: Display contact summary ──────────────────────────────
    print_summary(total_contacts, result)
    print_contact_preview(result.valid_contacts)
    print_message_preview(message)

    # ── Step 5: Run Android diagnostics ──────────────────────────────
    report: DiagnosticsReport = run_diagnostics()

    if not report.ready_to_send:
        print("  Cannot proceed without a connected Android device.")
        print("  Please connect your device, enable USB debugging, and try again.")
        print()
        logger.info("Exiting — device not ready.")
        sys.exit(1)

    print("  ⚠  No SMS messages were sent. This is a dry-run report only.")
    print()
    logger.info("Dry-run report complete. No SMS sent.")


if __name__ == "__main__":
    main()