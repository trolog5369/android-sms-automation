"""Message template reader.

Reads the SMS message body from a plain-text file using UTF-8 encoding
so that Marathi, Hindi, and other non-ASCII characters are preserved.
"""

from pathlib import Path


def read_message(file_path: Path) -> str:
    """Read and return the message content from a text file.

    The file is opened with UTF-8 encoding to correctly handle Marathi
    / Devanagari characters.  Leading and trailing whitespace is
    stripped, but internal formatting (line breaks, etc.) is preserved.

    Args:
        file_path: Path to the message template file (e.g. ``message.txt``).

    Returns:
        The message string with outer whitespace trimmed.

    Raises:
        FileNotFoundError: If *file_path* does not exist.
        UnicodeDecodeError: If the file is not valid UTF-8.
    """
    if not file_path.exists():
        raise FileNotFoundError(f"Message file not found: {file_path}")

    with open(file_path, "r", encoding="utf-8") as fh:
        content: str = fh.read().strip()

    if not content:
        raise ValueError(f"Message file is empty: {file_path}")

    return content
