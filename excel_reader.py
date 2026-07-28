"""Excel file reader for loading voter contact lists.

Handles reading the Excel spreadsheet, converting scientific-notation
phone numbers into proper 10-digit strings, preserving leading zeros,
and skipping blank rows.
"""

from pathlib import Path

import pandas as pd

from config import COL_ADVOCATE_NAME, COL_MOBILE_NUMBER, COL_SERIAL_NO
from models import Contact


def read_contacts(file_path: Path) -> list[Contact]:
    """Read contacts from an Excel (.xlsx/.xls) or CSV (.csv) file and return a list of Contact objects.

    This function:
    - Automatically detects file format (.xlsx / .xls vs .csv).
    - Reads the file with pandas.
    - Drops rows where *all* cells are empty.
    - Converts float / scientific-notation mobile numbers to 10-digit strings.
    - Preserves leading zeros by treating the result as a string throughout.

    Args:
        file_path: Absolute or relative path to the ``.xlsx`` or ``.csv`` file.

    Returns:
        A list of :class:`Contact` instances parsed from the file.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        ValueError: If file format is unsupported or expected columns are missing.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Contact file not found: {file_path}")

    ext = file_path.suffix.lower()
    if ext in (".xlsx", ".xls"):
        df: pd.DataFrame = pd.read_excel(file_path)
    elif ext == ".csv":
        df: pd.DataFrame = pd.read_csv(file_path, dtype=str)
    else:
        raise ValueError(f"Unsupported file format: '{ext}'. Expected .xlsx, .xls, or .csv")

    _validate_columns(df)

    # Drop rows where every cell is NaN
    df = df.dropna(how="all")

    contacts: list[Contact] = []
    for _, row in df.iterrows():
        serial_no = _clean_string(row.get(COL_SERIAL_NO, ""))
        advocate_name = _clean_string(row.get(COL_ADVOCATE_NAME, ""))
        mobile_number = _convert_mobile_number(row.get(COL_MOBILE_NUMBER))

        contacts.append(
            Contact(
                serial_no=serial_no,
                advocate_name=advocate_name,
                mobile_number=mobile_number,
            )
        )

    return contacts


def _validate_columns(df: pd.DataFrame) -> None:
    """Ensure the DataFrame contains the required columns.

    Args:
        df: The DataFrame read from Excel.

    Raises:
        ValueError: If any expected column is missing.
    """
    required = {COL_SERIAL_NO, COL_ADVOCATE_NAME, COL_MOBILE_NUMBER}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Missing expected columns in Excel file: {missing}")


def _convert_mobile_number(value: object) -> str:
    """Convert a raw mobile-number cell value to a clean 10-digit string.

    Handles:
    - ``float`` / scientific notation  →  ``int``  →  zero-padded string
    - ``int``                          →  zero-padded string
    - ``str``                          →  stripped, kept as-is
    - ``NaN`` / ``None``               →  empty string

    Args:
        value: The raw cell value from pandas.

    Returns:
        A string representation of the mobile number, or ``""`` if blank.
    """
    if pd.isna(value):
        return ""

    if isinstance(value, float):
        # Convert scientific notation (e.g. 9.139339e+09) → int → str
        value = int(value)

    number_str: str = str(value).strip()

    # Zero-pad to 10 digits if the number is shorter (preserves leading zeros)
    if number_str.isdigit() and len(number_str) < 10:
        number_str = number_str.zfill(10)

    return number_str


def _clean_string(value: object) -> str:
    """Convert a cell value to a trimmed string, treating NaN as empty.

    Args:
        value: The raw cell value.

    Returns:
        A stripped string, or ``""`` if the value is NaN / None.
    """
    if pd.isna(value):
        return ""
    return str(value).strip()
