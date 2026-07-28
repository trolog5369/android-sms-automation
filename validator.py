"""Contact validation module.

Filters out blank numbers, duplicates, and numbers that are not
exactly 10 digits.  Returns both the valid and invalid contact lists
so the caller can report on data quality.
"""

from dataclasses import dataclass

from config import PHONE_DIGIT_LENGTH
from models import Contact


@dataclass
class ValidationResult:
    """Holds the output of the validation pipeline.

    Attributes:
        valid_contacts: Contacts that passed all checks.
        invalid_contacts: Contacts that failed validation (blank, wrong length).
        duplicates_removed: Number of duplicate phone numbers that were removed.
    """

    valid_contacts: list[Contact]
    invalid_contacts: list[Contact]
    duplicates_removed: int


def validate_contacts(contacts: list[Contact]) -> ValidationResult:
    """Run the full validation pipeline on a list of contacts.

    Pipeline steps (in order):
    1. Remove contacts with blank phone numbers.
    2. Remove contacts with duplicate phone numbers (keep first occurrence).
    3. Separate contacts whose phone numbers are not exactly 10 digits.

    Args:
        contacts: Raw contact list from :func:`excel_reader.read_contacts`.

    Returns:
        A :class:`ValidationResult` containing valid contacts, invalid
        contacts, and the count of duplicates removed.
    """
    # Step 1 — remove blank phone numbers
    non_blank: list[Contact] = _remove_blank_numbers(contacts)
    blank_count: int = len(contacts) - len(non_blank)

    # Step 2 — remove duplicates (keep first occurrence)
    deduplicated, duplicates_removed = _remove_duplicates(non_blank)

    # Step 3 — validate digit length
    valid: list[Contact] = []
    invalid: list[Contact] = []

    for contact in deduplicated:
        if _is_valid_phone(contact.mobile_number):
            valid.append(contact)
        else:
            invalid.append(contact)

    # Contacts with blank numbers are also considered invalid
    blank_contacts: list[Contact] = [
        c for c in contacts if c.mobile_number == ""
    ]
    invalid = blank_contacts + invalid

    return ValidationResult(
        valid_contacts=valid,
        invalid_contacts=invalid,
        duplicates_removed=duplicates_removed,
    )


def _remove_blank_numbers(contacts: list[Contact]) -> list[Contact]:
    """Filter out contacts whose mobile number is empty.

    Args:
        contacts: The contact list to filter.

    Returns:
        A new list with only non-blank phone numbers.
    """
    return [c for c in contacts if c.mobile_number != ""]


def _remove_duplicates(contacts: list[Contact]) -> tuple[list[Contact], int]:
    """Remove contacts with duplicate phone numbers, keeping the first occurrence.

    Args:
        contacts: The contact list to deduplicate.

    Returns:
        A tuple of (deduplicated list, number of duplicates removed).
    """
    seen: set[str] = set()
    unique: list[Contact] = []
    duplicates: int = 0

    for contact in contacts:
        if contact.mobile_number in seen:
            duplicates += 1
        else:
            seen.add(contact.mobile_number)
            unique.append(contact)

    return unique, duplicates


def _is_valid_phone(number: str) -> bool:
    """Check whether a phone number string is exactly 10 digits.

    Args:
        number: The phone number string to validate.

    Returns:
        ``True`` if the number consists of exactly
        :data:`config.PHONE_DIGIT_LENGTH` digits, ``False`` otherwise.
    """
    return number.isdigit() and len(number) == PHONE_DIGIT_LENGTH
