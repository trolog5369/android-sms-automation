"""Tests for ADB discovery and device verification.

Test categories:
  - Discovery logic (mocked filesystem/PATH — no hardware needed)
  - Device verification (hardware-dependent tests clearly marked)

Tests that require a physical Android device are marked with
``@pytest.mark.hardware`` and will be skipped unless the marker
is explicitly requested (``pytest -m hardware``).
"""

import os
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure the project root is importable
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adb_manager import (
    DeviceInfo,
    discover_adb,
    execute_adb,
    get_adb_path,
    get_connected_devices,
    reset_adb_cache,
    verify_single_device,
)
from config import BASE_DIR
from exceptions import (
    ADBCommandError,
    ADBNotFoundError,
    ADBTimeoutError,
    DeviceUnauthorizedError,
    MultipleDevicesError,
    NoDeviceConnectedError,
)


# ── Fixtures ─────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def clear_adb_cache():
    """Reset the ADB path cache before each test."""
    reset_adb_cache()
    yield
    reset_adb_cache()


# ── 1. PATH installation discovery ───────────────────────────────────

class TestPathDiscovery:
    """Tests for ADB discovery via system PATH."""

    def test_adb_found_on_path(self):
        """discover_adb() finds adb via shutil.which when on PATH."""
        fake_path = r"C:\fake\platform-tools\adb.exe"

        with patch("adb_manager.shutil.which", return_value=fake_path), \
             patch("adb_manager.Path.is_file", return_value=True), \
             patch("adb_manager.Path.resolve", return_value=Path(fake_path)):
            result = discover_adb()
            assert result == fake_path or "adb" in result.lower()

    def test_adb_not_on_path_falls_through(self):
        """When PATH has no adb, discovery falls through to next source."""
        local_adb = BASE_DIR / "tools" / "platform-tools" / "adb.exe"

        with patch("adb_manager.shutil.which", return_value=None):
            # If the local copy exists, it should be found
            if local_adb.is_file():
                result = discover_adb()
                assert "adb" in result.lower()
            else:
                # No local copy either — should eventually raise
                with patch("adb_manager.Path.is_file", return_value=False), \
                     patch.dict(os.environ, {}, clear=True):
                    with pytest.raises(ADBNotFoundError):
                        discover_adb()


# ── 2. Local tools/platform-tools discovery ──────────────────────────

class TestLocalToolsDiscovery:
    """Tests for ADB discovery via project-local tools/platform-tools/."""

    def test_local_adb_exists(self):
        """Verify that tools/platform-tools/adb.exe actually exists in the project."""
        local_adb = BASE_DIR / "tools" / "platform-tools" / "adb.exe"
        assert local_adb.is_file(), (
            f"Expected adb.exe at {local_adb} — this file must exist for "
            "the local discovery path to work."
        )

    def test_local_adb_discovered_when_path_missing(self):
        """discover_adb() finds local adb when PATH has no adb."""
        local_adb = BASE_DIR / "tools" / "platform-tools" / "adb.exe"
        if not local_adb.is_file():
            pytest.skip("Local adb.exe not present")

        with patch("adb_manager.shutil.which", return_value=None):
            result = discover_adb()
            assert "platform-tools" in result
            assert result.endswith("adb.exe")


# ── 3. Custom configured location ───────────────────────────────────

class TestConfigDiscovery:
    """Tests for ADB discovery via config.ADB_EXECUTABLE."""

    def test_config_executable_used(self):
        """discover_adb() respects config.ADB_EXECUTABLE."""
        fake_config_path = r"D:\Custom\Android\adb.exe"

        with patch("adb_manager.shutil.which", return_value=None), \
             patch("adb_manager.ADB_EXECUTABLE", fake_config_path), \
             patch("adb_manager.Path.is_file", return_value=True), \
             patch("adb_manager.Path.resolve", return_value=Path(fake_config_path)):
            result = discover_adb()
            assert "adb" in result.lower()


# ── 4. Missing ADB ──────────────────────────────────────────────────

class TestMissingADB:
    """Tests for graceful handling when ADB is completely absent."""

    def test_adb_not_found_raises(self):
        """ADBNotFoundError is raised when adb is nowhere to be found."""
        with patch("adb_manager.shutil.which", return_value=None), \
             patch("adb_manager.ADB_EXECUTABLE", None), \
             patch("adb_manager.ADB_SEARCH_PATHS", []), \
             patch("adb_manager.Path.is_file", return_value=False), \
             patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ADBNotFoundError) as exc_info:
                discover_adb()

            # Verify the exception has structured details
            assert hasattr(exc_info.value, "details")
            details = exc_info.value.details()
            assert "Problem" in details
            assert "Cause" in details
            assert "Suggested Fix" in details

    def test_execute_adb_without_adb_raises(self):
        """execute_adb() raises ADBNotFoundError when adb is missing."""
        with patch("adb_manager.shutil.which", return_value=None), \
             patch("adb_manager.ADB_EXECUTABLE", None), \
             patch("adb_manager.ADB_SEARCH_PATHS", []), \
             patch("adb_manager.Path.is_file", return_value=False), \
             patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ADBNotFoundError):
                execute_adb("devices")


# ── 5. Connected device (hardware required) ─────────────────────────

class TestConnectedDevice:
    """Tests that require a physical Android device.

    These tests are marked with ``@pytest.mark.hardware`` and are
    skipped by default.  Run with ``pytest -m hardware`` to include them.
    """

    @pytest.mark.hardware
    def test_device_detected(self):
        """A connected, authorized device is detected and verified."""
        serial = verify_single_device()
        assert serial, "Expected a non-empty serial number"
        print(f"  [HARDWARE] Detected device: {serial}")

    @pytest.mark.hardware
    def test_device_info_populated(self):
        """get_device_info() returns a fully populated DeviceInfo."""
        from adb_manager import get_device_info

        serial = verify_single_device()
        info = get_device_info(serial)

        assert info.serial == serial
        assert info.manufacturer, "Manufacturer should not be empty"
        assert info.model, "Model should not be empty"
        assert info.android_version, "Android version should not be empty"
        print(f"  [HARDWARE] {info.manufacturer} {info.model} (Android {info.android_version})")


# ── 6. No device connected (mocked) ─────────────────────────────────

class TestNoDevice:
    """Tests for the no-device-connected scenario."""

    def test_no_device_raises(self):
        """NoDeviceConnectedError is raised when adb devices returns empty."""
        with patch("adb_manager.execute_adb", return_value="List of devices attached\n\n"):
            with pytest.raises(NoDeviceConnectedError) as exc_info:
                verify_single_device()

            details = exc_info.value.details()
            assert "Problem" in details
            assert "Fix" in details


# ── 7. Unauthorized device (mocked) ─────────────────────────────────

class TestUnauthorizedDevice:
    """Tests for the unauthorized-device scenario."""

    def test_unauthorized_raises(self):
        """DeviceUnauthorizedError is raised for an unauthorized device."""
        mock_output = "List of devices attached\nABCD1234\tunauthorized\n"

        with patch("adb_manager.execute_adb", return_value=mock_output):
            with pytest.raises(DeviceUnauthorizedError) as exc_info:
                verify_single_device()

            assert exc_info.value.serial == "ABCD1234"
            details = exc_info.value.details()
            assert "unauthorized" in details.lower() or "Problem" in details


# ── 8. Multiple devices (mocked) ────────────────────────────────────

class TestMultipleDevices:
    """Tests for the multiple-devices scenario."""

    def test_multiple_devices_raises(self):
        """MultipleDevicesError is raised when >1 device is connected."""
        mock_output = (
            "List of devices attached\n"
            "DEVICE_A\tdevice\n"
            "DEVICE_B\tdevice\n"
        )

        with patch("adb_manager.execute_adb", return_value=mock_output):
            with pytest.raises(MultipleDevicesError) as exc_info:
                verify_single_device()

            assert exc_info.value.count == 2


# ── 9. ADB timeout (mocked) ─────────────────────────────────────────

class TestADBTimeout:
    """Tests for ADB command timeout handling."""

    def test_timeout_raises(self):
        """ADBTimeoutError is raised when subprocess times out."""
        with patch("adb_manager.discover_adb", return_value=r"C:\fake\adb.exe"), \
             patch("adb_manager.subprocess.run", side_effect=subprocess.TimeoutExpired("adb", 15)):
            with pytest.raises(ADBTimeoutError) as exc_info:
                execute_adb("devices")

            assert exc_info.value.timeout_seconds == 15
            details = exc_info.value.details()
            assert "timed out" in details.lower()


# ── 10. Cache behavior ──────────────────────────────────────────────

class TestCacheBehavior:
    """Tests for the ADB path caching mechanism."""

    def test_cache_persists_across_calls(self):
        """discover_adb() caches the path and reuses it."""
        fake_path = r"C:\cached\adb.exe"

        with patch("adb_manager.shutil.which", return_value=fake_path), \
             patch("adb_manager.Path.is_file", return_value=True), \
             patch("adb_manager.Path.resolve", return_value=Path(fake_path)):
            first = discover_adb()

        # Second call should use cache, not call shutil.which again
        with patch("adb_manager.shutil.which") as mock_which:
            second = discover_adb()
            mock_which.assert_not_called()

        assert first == second

    def test_reset_clears_cache(self):
        """reset_adb_cache() clears the cached path."""
        fake_path = r"C:\cached\adb.exe"

        with patch("adb_manager.shutil.which", return_value=fake_path), \
             patch("adb_manager.Path.is_file", return_value=True), \
             patch("adb_manager.Path.resolve", return_value=Path(fake_path)):
            discover_adb()

        assert get_adb_path() is not None
        reset_adb_cache()
        assert get_adb_path() is None
