"""SMS Composer module — opens the Android SMS composer via ADB intent.

This module launches the default SMS app with a pre-filled recipient
and message body using ``android.intent.action.SENDTO``.

**CRITICAL SAFETY RULE:** This module NEVER sends SMS automatically.
It only opens the composer. The user must tap Send manually.

Dual-SIM handling:
    Android's SENDTO intent accepts a ``subscription`` extra (integer)
    that requests a specific subscription ID.  Whether the SMS app
    *honours* this extra depends on the manufacturer and Android version.

    Vivo devices running Android 14 with Google Messages: the subscription
    extra is passed through, but the app may still show a SIM picker or
    override it silently.  This behaviour is documented in the result.
"""

import logging
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Optional

from adb_manager import (
    SIMInfo,
    discover_adb,
    execute_adb,
    get_sim_info,
    get_sms_subscription_id,
    verify_single_device,
)
from config import (
    LOG_DIR,
    SMS_AUTO_SEND_ENABLED,
    SMS_SENDING_SIM_SLOT,
    SMS_SENDING_SIM_SUBSCRIPTION_ID,
    SMS_TEST_COOLDOWN_SECONDS,
    SMS_TEST_LOCK_FILE,
)
from exceptions import (
    ADBCommandError,
    ADBNotFoundError,
    ADBTimeoutError,
    DeviceUnauthorizedError,
    MultipleDevicesError,
    NoDeviceConnectedError,
)

logger: logging.Logger = logging.getLogger(__name__)

# Safety tripwire: this module refuses to proceed if auto-send is on
if SMS_AUTO_SEND_ENABLED:
    raise RuntimeError(
        "SMS_AUTO_SEND_ENABLED is True in config.py. "
        "Automatic sending is not implemented. Set it to False."
    )


# ── Data models ──────────────────────────────────────────────────────

@dataclass
class SelectedSIM:
    """The SIM chosen for sending.

    Attributes:
        sim_info: The :class:`~adb_manager.SIMInfo` for this SIM, or ``None``
                  if detection failed.
        slot: 1-based slot number.
        subscription_id: Android subscription ID string.
        carrier: Carrier name.
        selection_method: How this SIM was chosen
                          (``"config"``, ``"auto"``, ``"fallback"``).
    """
    sim_info: Optional[SIMInfo] = None
    slot: int = 0
    subscription_id: str = ""
    carrier: str = "unknown"
    selection_method: str = "unknown"


@dataclass
class SMSComposerResult:
    """Outcome of an SMS composer open attempt.

    Attributes:
        success: True if the composer opened without ADB errors.
        recipient: The phone number passed to the intent.
        message: The message body passed.
        message_length: Character count of the message.
        unicode_detected: True if the message contains non-ASCII characters.
        selected_sim: The :class:`SelectedSIM` used.
        sim_selection_honoured: Whether Android is expected to honour
                                the subscription extra (None = unknown).
        sim_selection_note: Human-readable note about SIM selection behaviour.
        intent_command: The full ADB command that was executed.
        intent_output: Raw output from the ``am start`` command.
        error_message: Error description if ``success`` is False.
        logs: List of diagnostic log lines.
    """
    success: bool = False
    recipient: str = ""
    message: str = ""
    message_length: int = 0
    unicode_detected: bool = False
    selected_sim: Optional[SelectedSIM] = None
    sim_selection_honoured: Optional[bool] = None
    sim_selection_note: str = ""
    intent_command: str = ""
    intent_output: str = ""
    error_message: str = ""
    logs: list = field(default_factory=list)


# ── SIM selection ────────────────────────────────────────────────────

def resolve_sending_sim() -> SelectedSIM:
    """Determine which SIM to use for sending based on config and device state.

    Priority order:
    1. ``config.SMS_SENDING_SIM_SUBSCRIPTION_ID`` (explicit subscription override)
    2. ``config.SMS_SENDING_SIM_SLOT`` (slot-based lookup → resolved to sub ID)
    3. Auto-discover from ``multi_sim_sms`` setting

    Returns:
        A :class:`SelectedSIM` describing the chosen SIM.
    """
    # Gather live SIM info
    try:
        sims: list[SIMInfo] = get_sim_info()
    except Exception:
        sims = []

    # ① Explicit subscription ID override in config
    if SMS_SENDING_SIM_SUBSCRIPTION_ID is not None:
        sub_id = str(SMS_SENDING_SIM_SUBSCRIPTION_ID)
        # Try to find matching SIMInfo
        match = next((s for s in sims if s.subscription_id == sub_id), None)
        return SelectedSIM(
            sim_info=match,
            slot=match.slot if match else 0,
            subscription_id=sub_id,
            carrier=match.carrier if match else "unknown",
            selection_method="config (subscription_id override)",
        )

    # ② Slot-based lookup (config.SMS_SENDING_SIM_SLOT, 0-based → 1-based)
    target_slot = SMS_SENDING_SIM_SLOT + 1  # convert 0-based config to 1-based slot
    slot_match = next((s for s in sims if s.slot == target_slot), None)

    if slot_match:
        return SelectedSIM(
            sim_info=slot_match,
            slot=slot_match.slot,
            subscription_id=slot_match.subscription_id,
            carrier=slot_match.carrier,
            selection_method=f"config (slot {target_slot})",
        )

    # ③ Auto-discover from multi_sim_sms setting
    try:
        auto_sub = get_sms_subscription_id()
        if auto_sub:
            auto_match = next((s for s in sims if s.subscription_id == auto_sub), None)
            return SelectedSIM(
                sim_info=auto_match,
                slot=auto_match.slot if auto_match else 0,
                subscription_id=auto_sub,
                carrier=auto_match.carrier if auto_match else "unknown",
                selection_method="auto (multi_sim_sms setting)",
            )
    except Exception:
        pass

    # ④ Fallback: use first loaded SIM
    loaded = next((s for s in sims if s.state == "LOADED"), None)
    if loaded:
        return SelectedSIM(
            sim_info=loaded,
            slot=loaded.slot,
            subscription_id=loaded.subscription_id,
            carrier=loaded.carrier,
            selection_method="fallback (first loaded SIM)",
        )

    return SelectedSIM(selection_method="unknown (no SIM detected)")


# ── Intent construction ──────────────────────────────────────────────

def _build_intent_command(recipient: str, message: str, subscription_id: str) -> list[str]:
    """Build the ``am start`` command list for the SENDTO intent.

    The message body is URL-encoded before embedding to correctly
    handle Unicode (Marathi / Devanagari) characters without shell
    escaping issues.

    Args:
        recipient: The phone number to pre-fill.
        message: The message body (may contain Unicode).
        subscription_id: Android subscription ID string (may be empty).

    Returns:
        A list of strings suitable for passing to ``execute_adb``.
    """
    # URL-encode the recipient into the smsto URI
    encoded_recipient = urllib.parse.quote(recipient, safe="")
    smsto_uri = f"smsto:{encoded_recipient}"

    # Build the shell command string
    # Use --es to pass the body; the message must be shell-quoted
    # We use single quotes and escape internal single quotes
    escaped_body = message.replace("'", "'\\''")
    cmd = f"shell am start -a android.intent.action.SENDTO -d '{smsto_uri}' --es sms_body '{escaped_body}'"

    if subscription_id:
        cmd += f" --ei subscription {subscription_id}"

    return cmd


def _detect_unicode(text: str) -> bool:
    """Return True if the text contains non-ASCII characters."""
    return any(ord(c) > 127 for c in text)


def reset_cooldown_lock() -> None:
    """Remove the lock file if it exists (useful for testing)."""
    if SMS_TEST_LOCK_FILE.exists():
        try:
            SMS_TEST_LOCK_FILE.unlink()
        except OSError:
            pass


def _check_cooldown(force: bool = False) -> tuple[bool, str]:
    """Check if the cooldown period has elapsed since the last composer launch."""
    now = time.time()
    if SMS_TEST_LOCK_FILE.exists():
        try:
            last_run = float(SMS_TEST_LOCK_FILE.read_text(encoding="utf-8").strip())
            elapsed = now - last_run
            if elapsed < SMS_TEST_COOLDOWN_SECONDS and not force:
                remaining = int(SMS_TEST_COOLDOWN_SECONDS - elapsed) + 1
                return (
                    False,
                    f"SMS composer test was launched {int(elapsed)}s ago. "
                    f"Cooldown period is {SMS_TEST_COOLDOWN_SECONDS}s to prevent notification spam. "
                    f"Please wait {remaining}s before trying again."
                )
        except (ValueError, OSError):
            pass

    # Update lock file
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        SMS_TEST_LOCK_FILE.write_text(str(now), encoding="utf-8")
    except OSError:
        pass

    return (True, "")


# ── Public API ───────────────────────────────────────────────────────

def open_sms_composer(recipient: str, message: str, force: bool = False) -> SMSComposerResult:
    """Open the Android SMS composer with a pre-filled recipient and message.

    Flow:
    1. Check anti-spam cooldown protection.
    2. Verify exactly one authorized device is connected.
    3. Resolve the sending SIM from config.
    4. Build the Android SENDTO intent.
    5. Launch the intent via ADB.
    6. Verify the SMS app started.
    7. Return a :class:`SMSComposerResult`.

    **Does NOT send the SMS.** The composer opens and waits for the user.

    Args:
        recipient: The phone number to fill as the SMS recipient.
        message: The message body (supports Unicode / Marathi text).
        force: If True, bypass the cooldown protection.

    Returns:
        A populated :class:`SMSComposerResult`.
    """
    result = SMSComposerResult(
        recipient=recipient,
        message=message,
        message_length=len(message),
        unicode_detected=_detect_unicode(message),
    )

    logs = result.logs

    # ── Cooldown Check ───────────────────────────────────────────────
    allowed, cooldown_msg = _check_cooldown(force=force)
    if not allowed:
        result.success = False
        result.error_message = cooldown_msg
        logs.append(f"REPEATED LAUNCH BLOCKED: {cooldown_msg}")
        return result

    # ── Diagnostics header ───────────────────────────────────────────
    logs.append(f"Recipient       : {recipient}")
    logs.append(f"Message Length  : {len(message)} characters")
    logs.append(f"Unicode Detected: {'YES' if result.unicode_detected else 'NO'}")

    # ── Step 1: Device check ─────────────────────────────────────────
    try:
        serial: str = verify_single_device()
        logs.append(f"Device          : {serial} (authorized)")
    except (
        ADBNotFoundError,
        NoDeviceConnectedError,
        MultipleDevicesError,
        DeviceUnauthorizedError,
        ADBCommandError,
        ADBTimeoutError,
    ) as exc:
        result.error_message = str(exc)
        logs.append(f"Device check FAILED: {exc}")
        return result

    # ── Step 2: Resolve sending SIM ──────────────────────────────────
    selected = resolve_sending_sim()
    result.selected_sim = selected

    logs.append(f"Sending SIM     : SIM {selected.slot} ({selected.carrier})")
    logs.append(f"Subscription ID : {selected.subscription_id or 'not set'}")
    logs.append(f"Selection Method: {selected.selection_method}")

    # Document SIM selection behaviour for Vivo/Android 14
    if selected.subscription_id:
        result.sim_selection_note = (
            "The --ei subscription extra was passed to the SMS intent. "
            "Whether the app honours it depends on the manufacturer (Vivo/Android 14). "
            "Google Messages may show a SIM picker or use its own default."
        )
        result.sim_selection_honoured = None  # cannot confirm without visual check
    else:
        result.sim_selection_note = (
            "No subscription ID could be determined — "
            "Android will use its own default SMS SIM."
        )

    logs.append(f"SIM Note        : {result.sim_selection_note}")

    # ── Step 3: Build and execute intent ─────────────────────────────
    cmd = _build_intent_command(recipient, message, selected.subscription_id)
    result.intent_command = cmd
    logs.append(f"Intent Command  : adb {cmd}")

    try:
        output: str = execute_adb(cmd)
        result.intent_output = output
        logs.append(f"Intent Output   : {output}")
    except (ADBCommandError, ADBTimeoutError) as exc:
        result.error_message = str(exc)
        logs.append(f"Intent FAILED   : {exc}")
        return result

    # ── Step 4: Verify the app started ──────────────────────────────
    # Give the app a moment to launch
    time.sleep(1)
    try:
        window_output: str = execute_adb("shell dumpsys window windows")
        # Look for the SMS app package in the focused window
        sms_active = any(
            pkg in window_output
            for pkg in (
                "com.google.android.apps.messaging",
                "com.android.mms",
                "com.samsung.android.messaging",
                "com.vivo.message",
            )
        )
        if sms_active:
            logs.append("SMS Intent Status: SUCCESS — SMS app is in foreground")
        else:
            logs.append("SMS Intent Status: WARNING — could not confirm SMS app is foreground")
    except (ADBCommandError, ADBTimeoutError):
        logs.append("SMS Intent Status: could not verify foreground app")

    # If intent returned "Starting: Intent" it succeeded
    if "Starting: Intent" in result.intent_output or result.intent_output == "":
        result.success = True
        logs.append("Result          : COMPOSER OPENED (no SMS sent)")
    else:
        result.error_message = f"Unexpected intent output: {result.intent_output}"
        logs.append(f"Result          : UNEXPECTED OUTPUT — {result.intent_output}")

    return result


def print_composer_result(result: SMSComposerResult) -> None:
    """Print a formatted report of the SMS composer test result.

    Args:
        result: The :class:`SMSComposerResult` to display.
    """
    from config import SEPARATOR

    print()
    print(SEPARATOR)
    print("  SMS Composer Test")
    print(SEPARATOR)
    print()
    print(f"  Recipient       : {result.recipient}")
    print(f"  Message Length  : {result.message_length} characters")
    print(f"  Unicode         : {'YES (Marathi/Unicode detected)' if result.unicode_detected else 'NO (ASCII only)'}")
    print()

    if result.selected_sim:
        sim = result.selected_sim
        print(f"  Sending SIM     : SIM {sim.slot} ({sim.carrier})")
        print(f"  Subscription ID : {sim.subscription_id or 'not set'}")
        print(f"  Selection Method: {sim.selection_method}")
        print()

    print(f"  Intent Status   : {'✔ SUCCESS' if result.success else '✘ FAILED'}")

    if result.sim_selection_note:
        print()
        print("  SIM Selection Note:")
        print(f"    {result.sim_selection_note}")

    if result.error_message:
        print()
        print(f"  Error: {result.error_message}")

    print()
    print("  Diagnostic Log:")
    for line in result.logs:
        print(f"    {line}")

    print()
    print("  ⚠  SMS COMPOSER OPENED — NO MESSAGE WAS SENT AUTOMATICALLY")
    print(SEPARATOR)
    print()


def check_sent_sms_status(recipient_number: str) -> str:
    """Attempt to check sent SMS status via ADB without requesting extra permissions.

    Android restricts access to content://sms/sent to system/phone UID.
    This helper attempts the query and returns a clear diagnostic message if denied.
    """
    try:
        output = execute_adb(f"shell content query --uri content://sms/sent --where \"address='{recipient_number}'\"")
        if "Row:" in output:
            return f"Sent SMS record found in provider for {recipient_number}."
        elif output.strip():
            return f"Query output: {output.strip()}"
    except (ADBCommandError, ADBTimeoutError) as exc:
        pass

    return "Android does not expose sent SMS verification without additional permissions."


def print_single_test_send_report(result: SMSComposerResult, recipient_name: str) -> None:
    """Print detailed logging output for single SMS manual send test."""
    from config import SEPARATOR

    print()
    print(SEPARATOR)
    print("  Single SMS Manual Send Verification")
    print(SEPARATOR)
    print()
    print(f"  Recipient Name  : {recipient_name}")
    print(f"  Recipient Number: {result.recipient}")
    print(f"  Message Length  : {result.message_length} characters")
    print(f"  Unicode         : {'YES' if result.unicode_detected else 'NO'}")
    print()

    if result.selected_sim:
        sim = result.selected_sim
        print(f"  Selected SIM    : SIM {sim.slot}")
        print(f"  SIM Slot        : {sim.slot}")
        print(f"  Subscription ID : {sim.subscription_id or 'not set'}")
        print(f"  Carrier         : {sim.carrier}")
        print()

    print(f"  Composer Opened : {'YES ✔' if result.success else 'NO ✘'}")
    print("  User Send Req.  : YES (Manual tap required on phone screen)")
    print()

    if result.error_message:
        print(f"  Error: {result.error_message}")
        print()

    print(SEPARATOR)
    print()

