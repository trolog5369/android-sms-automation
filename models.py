"""Data models for the ElectionSMS application.

This module defines the core data structures used throughout the project
using Python dataclasses for clean, type-safe representations.
"""

from dataclasses import dataclass


@dataclass
class Contact:
    """Represents a single contact entry from the voter list.

    Attributes:
        serial_no: The serial number or identifier from the Excel sheet.
        advocate_name: Full name of the advocate / voter.
        mobile_number: 10-digit mobile number stored as a string to preserve
                       leading zeros and avoid scientific-notation issues.
    """

    serial_no: str
    advocate_name: str
    mobile_number: str

    def __str__(self) -> str:
        """Return a human-readable string representation."""
        return f"{self.serial_no:<6} {self.advocate_name:<35} {self.mobile_number}"
