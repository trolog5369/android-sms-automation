"""Sequential Manual SMS Workflow Manager.

Manages step-by-step manual SMS sending where the application prepares
each message in the Android SMS composer via ADB intent and the user
manually presses Send on their phone screen.

CRITICAL SAFETY RULES:
- NO automatic sending.
- NO accessibility service / touch injection / input tap simulation.
- NO root / NO hidden automation.
"""

import datetime
import logging
import sys
import time
from dataclasses import dataclass
from typing import Optional

from config import (
    LOG_DIR,
    SEQUENCE_LOG_FILE,
    SEPARATOR,
    SMS_AUTO_SEND_ENABLED,
)
from models import Contact
from sms_composer import SMSComposerResult, open_sms_composer

# Reconfigure stdout and stdin for UTF-8 on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
if hasattr(sys.stdin, "reconfigure"):
    try:
        sys.stdin.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    except Exception:
        pass

logger: logging.Logger = logging.getLogger(__name__)

# Safety tripwire: refuse to run if auto-send is enabled
if SMS_AUTO_SEND_ENABLED:
    raise RuntimeError(
        "SMS_AUTO_SEND_ENABLED is True in config.py. "
        "Automatic sending is strictly forbidden. Set it to False."
    )


@dataclass
class SequenceLogEntry:
    """Represents a logged step in the manual sequence."""
    timestamp: str
    index: int
    name: str
    phone: str
    status: str  # "sent" or "skipped"
    method: str = "manual"


def get_logged_phone_numbers() -> set[str]:
    """Read logs/manual_sequence.log and return all logged phone numbers."""
    logged: set[str] = set()
    if not SEQUENCE_LOG_FILE.exists():
        return logged

    try:
        with open(SEQUENCE_LOG_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                parts = [p.strip() for p in line.strip().split("|")]
                if len(parts) >= 5:
                    phone = parts[3]
                    status = parts[4]
                    if status in ("sent", "skipped"):
                        logged.add(phone)
    except Exception as exc:
        logger.error("Error reading sequence log file: %s", exc)

    return logged


def log_sequence_step(index: int, name: str, phone: str, status: str) -> None:
    """Append a single step record to logs/manual_sequence.log."""
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry_line = f"{now_str} | {index} | {name} | {phone} | {status} | manual\n"

    try:
        with open(SEQUENCE_LOG_FILE, "a", encoding="utf-8") as fh:
            fh.write(entry_line)
        logger.info("Logged sequence step: %s (%s) -> %s", name, phone, status)
    except Exception as exc:
        logger.error("Failed to write to sequence log file: %s", exc)


def get_sequence_log_counts() -> tuple[int, int]:
    """Return (sent_count, skipped_count) from logs/manual_sequence.log."""
    sent = 0
    skipped = 0
    if not SEQUENCE_LOG_FILE.exists():
        return (0, 0)

    try:
        with open(SEQUENCE_LOG_FILE, "r", encoding="utf-8") as fh:
            for line in fh:
                parts = [p.strip() for p in line.strip().split("|")]
                if len(parts) >= 5:
                    status = parts[4].lower()
                    if status == "sent":
                        sent += 1
                    elif status == "skipped":
                        skipped += 1
    except Exception:
        pass

    return (sent, skipped)


def format_elapsed_time(seconds: float) -> str:
    """Format duration seconds into human-readable string."""
    mins, secs = divmod(int(seconds), 60)
    hrs, mins = divmod(mins, 60)
    if hrs > 0:
        return f"{hrs}h {mins}m {secs}s"
    elif mins > 0:
        return f"{mins}m {secs}s"
    return f"{secs}s"


def run_manual_sequence(
    contacts: list[Contact],
    message: str,
    start_index: Optional[int] = None,
    limit: Optional[int] = None,
    resume: bool = False,
) -> None:
    """Execute the sequential manual SMS workflow.

    Args:
        contacts: List of valid :class:`~models.Contact` objects.
        message: SMS body from message.txt.
        start_index: 1-based start index (optional).
        limit: Max number of contacts to process in this run (optional).
        resume: If True, skip contacts already present in the log file.
    """
    total_valid = len(contacts)

    if total_valid == 0:
        print("  No valid contacts to process.")
        return

    # ── 1. Determine contacts to process ─────────────────────────────
    already_logged_phones = get_logged_phone_numbers() if resume else set()

    # Build work items as tuples of (original_1_based_index, Contact)
    indexed_contacts = [(i + 1, c) for i, c in enumerate(contacts)]

    if resume:
        indexed_contacts = [
            (idx, c) for idx, c in indexed_contacts if c.mobile_number not in already_logged_phones
        ]
        logger.info("Resume mode: %d contacts remain after filtering logged ones.", len(indexed_contacts))

    # Apply --start (1-based index)
    if start_index is not None and start_index > 1:
        indexed_contacts = [(idx, c) for idx, c in indexed_contacts if idx >= start_index]

    # Apply --limit
    if limit is not None and limit > 0:
        indexed_contacts = indexed_contacts[:limit]

    work_count = len(indexed_contacts)

    if work_count == 0:
        print("  No contacts match the specified sequence filter (--resume / --start / --limit).")
        return

    # Initial statistics counters
    sent_count, skipped_count = get_sequence_log_counts() if resume else (0, 0)
    processed_this_run = 0
    start_time = time.time()

    print()
    print(SEPARATOR)
    print("  Manual Sequential SMS Workflow")
    print(SEPARATOR)
    print(f"  Total Valid Contacts : {total_valid}")
    print(f"  Contacts To Process  : {work_count}")
    if resume:
        print(f"  Already Logged       : {sent_count} sent, {skipped_count} skipped")
    print(SEPARATOR)
    print()

    try:
        raw_input = input("Start manual SMS sequence? (y/N): ")
        confirm = raw_input.strip().lower()
        logger.info("Confirm raw: %r, parsed: %r", raw_input, confirm)
    except (KeyboardInterrupt, EOFError) as exc:
        logger.error("Input exception: %s", exc)
        confirm = "n"

    if confirm not in ("y", "yes"):
        print("  Manual sequence cancelled.")
        return

    print()

    # ── 2. Sequential Loop ───────────────────────────────────────────
    for step_num, (orig_idx, contact) in enumerate(indexed_contacts, start=1):
        # Open SMS composer (force=True so sequence stepping is never blocked by cooldown)
        result: SMSComposerResult = open_sms_composer(contact.mobile_number, message, force=True)

        sim_slot = result.selected_sim.slot if result.selected_sim else "unknown"
        carrier = result.selected_sim.carrier if result.selected_sim else "unknown"
        sub_id = result.selected_sim.subscription_id if result.selected_sim else "not set"

        print(SEPARATOR)
        print(f"Contact {orig_idx} / {total_valid}  (Step {step_num} of {work_count})")
        print()
        print(f"Name:    {contact.advocate_name}")
        print(f"Phone:   {contact.mobile_number}")
        print()
        print(f"SIM:             SIM {sim_slot}")
        print(f"Carrier:         {carrier}")
        print(f"Subscription ID: {sub_id}")
        print()

        if result.success:
            print("Composer opened successfully.")
        else:
            print(f"WARNING: Composer failed: {result.error_message}")

        print()
        print("Waiting for manual Send...")
        print()
        print("After pressing Send on your phone,")
        print("press ENTER here to continue.")
        print("Type 's' then ENTER to skip this contact.")
        print("Type 'q' then ENTER to quit.")
        print(SEPARATOR)
        print()

        try:
            choice = input("Choice [ENTER=Sent / s=Skip / q=Quit]: ").strip().lower()
        except (KeyboardInterrupt, EOFError):
            choice = "q"

        if choice in ("q", "quit"):
            print()
            print("  Sequence quit by user.")
            log_sequence_step(orig_idx, contact.advocate_name, contact.mobile_number, "quit")
            break

        elif choice in ("s", "skip"):
            status = "skipped"
            skipped_count += 1
            print(f"  -> Marked as SKIPPED: {contact.advocate_name}")
        else:
            status = "sent"
            sent_count += 1
            print(f"  -> Marked as SENT: {contact.advocate_name}")

        log_sequence_step(orig_idx, contact.advocate_name, contact.mobile_number, status)
        processed_this_run += 1
        remaining_count = work_count - step_num

        print()
        print("Progress:")
        print(f"  Sent      : {sent_count}")
        print(f"  Skipped   : {skipped_count}")
        print(f"  Remaining : {remaining_count}")
        print()

    # ── 3. Completion Summary ────────────────────────────────────────
    elapsed = time.time() - start_time
    remaining_total = max(0, total_valid - (sent_count + skipped_count))

    print(SEPARATOR)
    print("  Manual SMS Sequence Summary")
    print(SEPARATOR)
    print()
    print(f"  Total Contacts : {total_valid}")
    print(f"  Sent           : {sent_count}")
    print(f"  Skipped        : {skipped_count}")
    print(f"  Remaining      : {remaining_total}")
    print(f"  Elapsed Time   : {format_elapsed_time(elapsed)}")
    print()
    print(SEPARATOR)
    print()
    logger.info(
        "Manual sequence finished. Processed: %d, Sent: %d, Skipped: %d, Elapsed: %.1fs",
        processed_this_run,
        sent_count,
        skipped_count,
        elapsed,
    )
