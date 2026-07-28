"""Tests for sequence_manager module (Milestone 6).

Test categories:
  - Sequence log file writing & parsing
  - Resume filtering by logged phone numbers
  - Start & limit contact slicing
  - Safety guard verification
"""

import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import SEQUENCE_LOG_FILE, SMS_AUTO_SEND_ENABLED
from models import Contact
from sequence_manager import (
    format_elapsed_time,
    get_logged_phone_numbers,
    get_sequence_log_counts,
    log_sequence_step,
    run_manual_sequence,
)


@pytest.fixture(autouse=True)
def clean_sequence_log(tmp_path):
    """Temporary sequence log file for isolation."""
    test_log = tmp_path / "test_manual_sequence.log"
    with patch("sequence_manager.SEQUENCE_LOG_FILE", test_log):
        yield test_log


class TestSequenceLogging:
    """Tests for sequence log file operations."""

    def test_log_step_appends_file(self, clean_sequence_log):
        """log_sequence_step writes formatted record."""
        log_sequence_step(1, "Test Person", "9876543210", "sent")
        assert clean_sequence_log.exists()
        content = clean_sequence_log.read_text(encoding="utf-8")
        assert "1 | Test Person | 9876543210 | sent | manual" in content

    def test_get_logged_phone_numbers(self, clean_sequence_log):
        """get_logged_phone_numbers retrieves logged phones."""
        log_sequence_step(1, "Person A", "9111111111", "sent")
        log_sequence_step(2, "Person B", "9222222222", "skipped")
        log_sequence_step(3, "Person C", "9333333333", "quit")

        logged = get_logged_phone_numbers()
        assert "9111111111" in logged
        assert "9222222222" in logged
        assert "9333333333" not in logged  # quit is not a completed step

    def test_get_sequence_log_counts(self, clean_sequence_log):
        """get_sequence_log_counts counts sent vs skipped."""
        log_sequence_step(1, "Person A", "9111111111", "sent")
        log_sequence_step(2, "Person B", "9222222222", "sent")
        log_sequence_step(3, "Person C", "9333333333", "skipped")

        sent, skipped = get_sequence_log_counts()
        assert sent == 2
        assert skipped == 1


class TestTimeFormatting:
    """Tests for format_elapsed_time helper."""

    def test_seconds_only(self):
        assert format_elapsed_time(45) == "45s"

    def test_minutes_and_seconds(self):
        assert format_elapsed_time(145) == "2m 25s"

    def test_hours_minutes_seconds(self):
        assert format_elapsed_time(3725) == "1h 2m 5s"


class TestSequenceWorkflow:
    """Tests for run_manual_sequence filtering and workflow logic."""

    def test_cancel_prompt_exits(self, clean_sequence_log):
        """Refusing initial prompt exits cleanly without calling composer."""
        contacts = [Contact("1", "A", "9000000001")]
        with patch("builtins.input", return_value="n"), \
             patch("sequence_manager.open_sms_composer") as mock_composer:
            run_manual_sequence(contacts, "Test Msg")
            mock_composer.assert_not_called()

    def test_start_and_limit_slicing(self, clean_sequence_log):
        """--start and --limit isolate requested contact range."""
        contacts = [
            Contact(str(i), f"Person {i}", f"900000000{i}")
            for i in range(1, 10)
        ]
        # Simulate pressing ENTER ('') for step 1 then 'q' to quit
        inputs = iter(["y", "", "q"])
        mock_result = MagicMock(success=True, selected_sim=MagicMock(slot=2, carrier="Vi", subscription_id="1"))

        with patch("builtins.input", side_effect=lambda _: next(inputs)), \
             patch("sequence_manager.open_sms_composer", return_value=mock_result) as mock_composer:
            run_manual_sequence(contacts, "Test Msg", start_index=3, limit=2)
            # Should launch for contact index 3 (9000000003) and 4 (9000000004)
            mock_composer.assert_any_call("9000000003", "Test Msg", force=True)

    def test_resume_skips_logged_contacts(self, clean_sequence_log):
        """--resume skips contacts that are already in log."""
        log_sequence_step(1, "Person 1", "9000000001", "sent")

        contacts = [
            Contact("1", "Person 1", "9000000001"),
            Contact("2", "Person 2", "9000000002"),
        ]

        inputs = iter(["y", "q"])
        mock_result = MagicMock(success=True, selected_sim=MagicMock(slot=2, carrier="Vi", subscription_id="1"))

        with patch("builtins.input", side_effect=lambda _: next(inputs)), \
             patch("sequence_manager.open_sms_composer", return_value=mock_result) as mock_composer:
            run_manual_sequence(contacts, "Test Msg", resume=True)
            # Person 1 skipped, Person 2 launched
            mock_composer.assert_called_with("9000000002", "Test Msg", force=True)


class TestSafetyGuard:
    """Safety checks for sequence_manager."""

    def test_auto_send_disabled_flag(self):
        """SMS_AUTO_SEND_ENABLED must remain False."""
        assert SMS_AUTO_SEND_ENABLED is False
