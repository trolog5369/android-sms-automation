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

# ── App metadata ─────────────────────────────────────────────────────
APP_NAME: str = "Election SMS Automation"
APP_VERSION: str = "1.0.0"
