"""Application configuration constants.

Centralizes all configurable values in one place so that no magic
strings or numbers are scattered across the codebase.
"""

from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).resolve().parent
EXCEL_FILE: Path = BASE_DIR / "Ghodnadi Bar Clean.xlsx"
MESSAGE_FILE: Path = BASE_DIR / "message.txt"
LOG_DIR: Path = BASE_DIR / "logs"

# ── Excel column mapping ────────────────────────────────────────────
COL_SERIAL_NO: str = "No"
COL_ADVOCATE_NAME: str = "Advocate Name"
COL_MOBILE_NUMBER: str = "Mobile no."

# ── Validation rules ────────────────────────────────────────────────
PHONE_DIGIT_LENGTH: int = 10

# ── Display ──────────────────────────────────────────────────────────
PREVIEW_COUNT: int = 10
SEPARATOR: str = "-" * 50

# ── ADB settings ─────────────────────────────────────────────────────
# Explicit path to the ADB executable.  Set this if ADB lives in a
# non-standard location that is not covered by the automatic search.
# When set, this takes priority over the automatic search.
# Example: r"D:\Android\sdk\platform-tools\adb.exe"
ADB_EXECUTABLE: str | None = None

# Additional directories to probe for ``adb.exe``, checked *after* the
# built-in locations (system PATH → project tools/ → SDK defaults).
# Each entry should be a :class:`pathlib.Path` pointing to a directory
# that may contain ``adb.exe``.
ADB_SEARCH_PATHS: list[Path] = []

# ── Test Recipients for Single SMS Verification ──────────────────────
# Controlled test numbers used for single manual send verification.
TEST_RECIPIENTS: dict[str, str] = {
    "Vaishali Gaikwad": "9657902071",
    "Pramod Gaikwad": "9922222249",
    "Sai Gaikwad": "9371222249",
}
DEFAULT_TEST_RECIPIENT_KEY: str = "Vaishali Gaikwad"

# Recipient used ONLY for generic composer testing (not a real campaign number).
SMS_TEST_RECIPIENT: str = TEST_RECIPIENTS[DEFAULT_TEST_RECIPIENT_KEY]

# ── SMS Sending SIM Configuration ───────────────────────────────────
# The SIM slot index (0-based) to use as the outgoing SMS sender.
#   0 = SIM 1 (first physical slot)
#   1 = SIM 2 (second physical slot)
# Default: 1 (SIM 2 — Vi India in the current hardware setup)
# Change this when you swap SIMs or run on different hardware.
SMS_SENDING_SIM_SLOT: int = 1

# Android subscription ID for the sending SIM.
# This is discovered automatically at runtime from getprop.
# Set to None to force auto-discovery every time.
# Set to a specific int (e.g. 2) to hard-override for testing.
SMS_SENDING_SIM_SUBSCRIPTION_ID: int | None = None

# Safety guard — NEVER set this to True unless SMS sending is fully implemented.
# While False, the SMS composer opens pre-filled but does NOT send automatically.
SMS_AUTO_SEND_ENABLED: bool = False

# Minimum seconds required between consecutive SMS composer test launches
# to prevent spamming intents / notifications on the phone.
SMS_TEST_COOLDOWN_SECONDS: int = 10
SMS_TEST_LOCK_FILE: Path = LOG_DIR / ".sms_test_lock"

# ── App metadata ─────────────────────────────────────────────────────
APP_NAME: str = "Election SMS Automation"
APP_VERSION: str = "1.0.0"
