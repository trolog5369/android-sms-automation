"""Application configuration constants.

Centralizes all configurable values in one place so that no magic
strings or numbers are scattered across the codebase.
"""

from pathlib import Path

# ── Paths ────────────────────────────────────────────────────────────
BASE_DIR: Path = Path(__file__).resolve().parent

# IMPORTANT:
# Use test_contacts.csv during testing/verification.
CONTACT_FILE: Path = BASE_DIR / "test_contacts.csv"

MESSAGE_FILE: Path = BASE_DIR / "message.txt"
LOG_DIR: Path = BASE_DIR / "logs"

# ── Excel column mapping ─────────────────────────────────────────────
COL_SERIAL_NO: str = "No"
COL_ADVOCATE_NAME: str = "Advocate Name"
COL_MOBILE_NUMBER: str = "Mobile no."

# ── Validation rules ────────────────────────────────────────────────
PHONE_DIGIT_LENGTH: int = 10

# ── Display ─────────────────────────────────────────────────────────
PREVIEW_COUNT: int = 10
SEPARATOR: str = "-" * 50

# ── ADB settings ─────────────────────────────────────────────────────
ADB_EXECUTABLE: str | None = None

ADB_SEARCH_PATHS: list[Path] = []

# ── Controlled Test Recipients ───────────────────────────────────────
# ONLY for manual verification.
# These are NOT campaign contacts.

TEST_RECIPIENTS: dict[str, str] = {
    "Pranav Gaikwad": "9615222249",
    "Vaishali Gaikwad": "9657902071",
    "Pramod Gaikwad": "9922222249",
    "Om Gaikwad": "8857992249",
    "Sai Gaikwad": "9371222249",
    "Dadasaheb Gaikwad": "8070222249",
}

DEFAULT_TEST_RECIPIENT_KEY: str = "Pranav Gaikwad"

SMS_TEST_RECIPIENT: str = TEST_RECIPIENTS[DEFAULT_TEST_RECIPIENT_KEY]


# ── SMS Sending SIM Configuration ───────────────────────────────────
# 0 = SIM 1
# 1 = SIM 2
SMS_SENDING_SIM_SLOT: int = 1


# Auto discovery
SMS_SENDING_SIM_SUBSCRIPTION_ID: int | None = None


# SAFETY LOCK
# MUST REMAIN FALSE DURING TESTING
SMS_AUTO_SEND_ENABLED: bool = False


# ── Sequence Settings ────────────────────────────────────────────────
SMS_TEST_COOLDOWN_SECONDS: int = 10

SMS_TEST_LOCK_FILE: Path = LOG_DIR / ".sms_test_lock"

SEQUENCE_LOG_FILE: Path = LOG_DIR / "manual_sequence.log"


# ── App Metadata ─────────────────────────────────────────────────────
APP_NAME: str = "Election SMS Automation"
APP_VERSION: str = "1.0.0"