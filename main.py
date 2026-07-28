"""ElectionSMS — main entry point.

Orchestrates the contact-reading, validation, device-verification,
diagnostics, and SMS composer testing workflows.

CLI Modes:
  python main.py               Run full contact extraction, validation, and diagnostics.
  python main.py --diagnostics Run Android ADB & SIM health diagnostics only.
  python main.py --sms-test    Launch the Android SMS composer ONCE with pre-filled test message.

No SMS messages are sent automatically from this application.
"""

import argparse
import logging
import sys

from config import EXCEL_FILE, LOG_DIR, MESSAGE_FILE, SMS_TEST_RECIPIENT
from diagnostics import DiagnosticsReport, run_diagnostics
from excel_reader import read_contacts
from message_reader import read_message
from models import Contact
from sms_composer import SMSComposerResult, open_sms_composer, print_composer_result
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
    """Main entry point supporting --diagnostics, --sms-test, and default pipeline."""
    parser = argparse.ArgumentParser(
        description="ElectionSMS — Android SMS Automation & Diagnostics Tool",
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Run Android ADB discovery & SIM health report only.",
    )
    parser.add_argument(
        "--sms-test",
        action="store_true",
        help="Launch the Android SMS composer once with pre-filled test recipient and message.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Bypass cooldown anti-spam protection during --sms-test.",
    )

    args = parser.parse_args()

    logger.info("Application started. Args: %s", args)
    print_header()

    # ── Mode 1: --diagnostics only ──────────────────────────────────
    if args.diagnostics:
        logger.info("Running diagnostics mode.")
        report: DiagnosticsReport = run_diagnostics()
        if not report.ready_to_send:
            logger.warning("Diagnostics complete: Device not ready.")
            sys.exit(1)
        return

    # ── Mode 2: --sms-test only ─────────────────────────────────────
    if args.sms_test:
        logger.info("Running SMS test mode.")
        report = run_diagnostics()

        if not report.ready_to_send:
            print("  Cannot run SMS composer test: Android device is not connected or ready.")
            print()
            logger.error("SMS test aborted — device not ready.")
            sys.exit(1)

        try:
            message: str = read_message(MESSAGE_FILE)
        except (FileNotFoundError, ValueError, UnicodeDecodeError) as exc:
            logger.error("Message file error: %s", exc)
            print(f"  [ERROR] {exc}")
            sys.exit(1)

        logger.info("Starting SMS composer test for recipient: %s", SMS_TEST_RECIPIENT)
        composer_result: SMSComposerResult = open_sms_composer(
            SMS_TEST_RECIPIENT,
            message,
            force=args.force,
        )
        print_composer_result(composer_result)

        if not composer_result.success:
            logger.warning("SMS composer test did not complete: %s", composer_result.error_message)
        else:
            logger.info("SMS composer test completed successfully.")
        return

    # ── Mode 3: Default dry-run pipeline ────────────────────────────
    logger.info("Running default dry-run pipeline.")

    # Step 1: Read contacts
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

    # Step 2: Validate contacts
    result: ValidationResult = validate_contacts(contacts)
    logger.info(
        "Validation: %d valid, %d invalid, %d duplicates removed.",
        len(result.valid_contacts),
        len(result.invalid_contacts),
        result.duplicates_removed,
    )

    # Step 3: Read SMS message template
    try:
        message = read_message(MESSAGE_FILE)
    except (FileNotFoundError, ValueError, UnicodeDecodeError) as exc:
        logger.error("Message file error: %s", exc)
        print(f"  [ERROR] {exc}")
        sys.exit(1)

    # Step 4: Display contact & message preview
    print_summary(total_contacts, result)
    print_contact_preview(result.valid_contacts)
    print_message_preview(message)

    # Step 5: Run Android diagnostics
    report = run_diagnostics()

    print("  ⚠  Dry-Run Complete. No SMS messages were sent.")
    print("  ⚠  SMS Composer was NOT opened automatically.")
    print("  ℹ  To test launching the SMS composer, run: python main.py --sms-test")
    print()
    logger.info("Dry-run complete. No SMS sent, no composer opened.")


if __name__ == "__main__":
    main()