"""Android Debug Bridge (ADB) manager module.

Provides a reusable wrapper around common ``adb`` shell commands for
device discovery, verification, and information retrieval.

**Key design change (Milestone 3):** The module never assumes that
``adb`` is available on the system PATH.  Instead, :func:`discover_adb`
searches multiple locations in a defined priority order, caches the
result, and every subsequent ADB call uses the fully-qualified path.

This module does **not** open any apps or send any SMS — it only
queries device metadata.
"""

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from config import ADB_EXECUTABLE, ADB_SEARCH_PATHS, BASE_DIR
from exceptions import (
    ADBCommandError,
    ADBNotFoundError,
    ADBTimeoutError,
    DeviceUnauthorizedError,
    MultipleDevicesError,
    NoDeviceConnectedError,
)

logger: logging.Logger = logging.getLogger(__name__)

# ── Module-level cache ───────────────────────────────────────────────
_adb_path: Optional[str] = None

# Default timeout for ADB commands (seconds)
_ADB_TIMEOUT: int = 15


# ── Data model for device info ───────────────────────────────────────

@dataclass
class DeviceInfo:
    """Aggregated metadata about the connected Android device.

    Attributes:
        serial: The ADB serial number (e.g. ``ABCD1234``).
        manufacturer: Device manufacturer (e.g. ``samsung``).
        model: Device model name (e.g. ``SM-A505F``).
        android_version: Android OS version string (e.g. ``13``).
        usb_debugging: Whether USB debugging is confirmed enabled.
        default_sms_app: Package name of the default SMS app.
        sim_count: Number of active SIM cards detected.
        default_sms_sim: Index/ID of the default SIM for SMS.
    """

    serial: str = ""
    manufacturer: str = ""
    model: str = ""
    android_version: str = ""
    usb_debugging: str = ""
    default_sms_app: str = ""
    sim_count: str = ""
    default_sms_sim: str = ""


# ── ADB Discovery ───────────────────────────────────────────────────

def discover_adb() -> str:
    """Locate the ``adb.exe`` executable and cache the result.

    Search order:

    1. System PATH (``shutil.which``)
    2. Project-local ``tools/platform-tools/adb.exe``
    3. ``config.ADB_EXECUTABLE`` (user override)
    4. ``config.ADB_SEARCH_PATHS`` (extra directories)
    5. Android SDK default locations (``ANDROID_HOME``, ``LOCALAPPDATA``)

    Returns:
        The absolute path to the ``adb`` executable.

    Raises:
        ADBNotFoundError: If ``adb`` cannot be located anywhere.
    """
    global _adb_path

    # Return cached value if already discovered
    if _adb_path is not None:
        return _adb_path

    candidates: list[tuple[str, str]] = []  # (description, path)

    # ① System PATH
    path_adb: str | None = shutil.which("adb")
    if path_adb:
        candidates.append(("System PATH", path_adb))

    # ② Project-local tools/platform-tools/
    local_adb: Path = BASE_DIR / "tools" / "platform-tools" / "adb.exe"
    if local_adb.is_file():
        candidates.append(("Project tools/platform-tools/", str(local_adb)))

    # ③ config.ADB_EXECUTABLE (explicit user override)
    if ADB_EXECUTABLE and Path(ADB_EXECUTABLE).is_file():
        candidates.append(("config.ADB_EXECUTABLE", ADB_EXECUTABLE))

    # ④ config.ADB_SEARCH_PATHS
    for search_dir in ADB_SEARCH_PATHS:
        candidate: Path = Path(search_dir) / "adb.exe"
        if candidate.is_file():
            candidates.append((f"ADB_SEARCH_PATHS ({search_dir})", str(candidate)))

    # ⑤ Android SDK default locations
    sdk_env_vars: list[str] = ["ANDROID_HOME", "ANDROID_SDK_ROOT"]
    for var in sdk_env_vars:
        sdk_root: str | None = os.environ.get(var)
        if sdk_root:
            sdk_adb: Path = Path(sdk_root) / "platform-tools" / "adb.exe"
            if sdk_adb.is_file():
                candidates.append((f"${var}", str(sdk_adb)))

    # LOCALAPPDATA fallback (Windows default SDK location)
    local_app_data: str | None = os.environ.get("LOCALAPPDATA")
    if local_app_data:
        default_sdk_adb: Path = (
            Path(local_app_data) / "Android" / "Sdk" / "platform-tools" / "adb.exe"
        )
        if default_sdk_adb.is_file():
            candidates.append(("LOCALAPPDATA/Android/Sdk", str(default_sdk_adb)))

    # Log all candidates found
    if candidates:
        for desc, path in candidates:
            logger.debug("ADB candidate [%s]: %s", desc, path)

        # Use the first candidate found (highest priority)
        chosen_desc, chosen_path = candidates[0]
        _adb_path = str(Path(chosen_path).resolve())
        logger.info("ADB discovered via %s: %s", chosen_desc, _adb_path)
        return _adb_path

    # Nothing found
    logger.error("ADB executable not found in any search location.")
    raise ADBNotFoundError()


def reset_adb_cache() -> None:
    """Clear the cached ADB path.

    Useful for testing or when the user changes configuration at runtime.
    """
    global _adb_path
    _adb_path = None
    logger.debug("ADB path cache cleared.")


def get_adb_path() -> Optional[str]:
    """Return the currently cached ADB path, or ``None`` if not yet discovered.

    This is a read-only accessor for diagnostics and testing.
    """
    return _adb_path


# ── Public API ───────────────────────────────────────────────────────

def execute_adb(command: str) -> str:
    """Run an ``adb`` command using the discovered executable path.

    Args:
        command: The ADB sub-command to run (e.g. ``"devices"``
                 or ``"shell getprop ro.build.version.release"``).

    Returns:
        The stripped stdout output from the command.

    Raises:
        ADBNotFoundError: If ADB is not installed.
        ADBTimeoutError: If the command times out.
        ADBCommandError: If the command exits with a non-zero code.
    """
    adb_exe: str = discover_adb()

    # Build command as a list for safety (no shell=True needed)
    cmd_parts: list[str] = [adb_exe] + command.split()
    logger.debug("Executing: %s", cmd_parts)

    try:
        result: subprocess.CompletedProcess[str] = subprocess.run(
            cmd_parts,
            capture_output=True,
            text=True,
            timeout=_ADB_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        logger.error("ADB command timed out: %s", command)
        raise ADBTimeoutError(command=command, timeout_seconds=_ADB_TIMEOUT)

    if result.returncode != 0:
        logger.error(
            "ADB command failed (exit %d): %s — %s",
            result.returncode,
            command,
            result.stderr.strip(),
        )
        raise ADBCommandError(
            command=command,
            returncode=result.returncode,
            stderr=result.stderr,
        )

    output: str = result.stdout.strip()
    logger.debug("Output: %s", output)
    return output


def get_connected_devices() -> list[dict[str, str]]:
    """Return a list of devices reported by ``adb devices``.

    Each device is represented as a dict with keys ``serial`` and
    ``status`` (e.g. ``device``, ``unauthorized``, ``offline``).

    Returns:
        A list of device dicts. May be empty if nothing is connected.

    Raises:
        ADBNotFoundError: If ADB is not installed.
    """
    output: str = execute_adb("devices")
    devices: list[dict[str, str]] = []

    for line in output.strip().splitlines():
        # Skip the header line ("List of devices attached")
        if line.startswith("List of") or not line.strip():
            continue

        parts: list[str] = line.split()
        if len(parts) >= 2:
            devices.append({"serial": parts[0], "status": parts[1]})

    logger.info("Found %d device(s): %s", len(devices), devices)
    return devices


def verify_single_device() -> str:
    """Ensure exactly one authorized device is connected.

    Returns:
        The serial number of the single authorized device.

    Raises:
        NoDeviceConnectedError: If no devices are found.
        MultipleDevicesError: If more than one device is found.
        DeviceUnauthorizedError: If the device has not authorized
            USB debugging.
    """
    devices: list[dict[str, str]] = get_connected_devices()

    if len(devices) == 0:
        logger.error("No devices connected.")
        raise NoDeviceConnectedError()

    if len(devices) > 1:
        logger.error("Multiple devices connected: %d", len(devices))
        raise MultipleDevicesError(count=len(devices))

    device = devices[0]

    if device["status"] == "unauthorized":
        logger.error("Device %s is unauthorized.", device["serial"])
        raise DeviceUnauthorizedError(serial=device["serial"])

    if device["status"] != "device":
        logger.warning(
            "Device %s has unexpected status: %s",
            device["serial"],
            device["status"],
        )
        raise NoDeviceConnectedError(
            f"Device {device['serial']!r} status is {device['status']!r}, "
            "not 'device'. Check your USB connection."
        )

    logger.info("Verified single device: %s", device["serial"])
    return device["serial"]


# ── Device property queries ──────────────────────────────────────────

def get_android_version() -> str:
    """Query the Android OS version of the connected device.

    Returns:
        The version string (e.g. ``"13"`` or ``"14"``).
    """
    version: str = execute_adb("shell getprop ro.build.version.release")
    logger.info("Android version: %s", version)
    return version


def get_device_model() -> str:
    """Query the model name of the connected device.

    Returns:
        The model string (e.g. ``"SM-A505F"`` or ``"Pixel 7"``).
    """
    model: str = execute_adb("shell getprop ro.product.model")
    logger.info("Device model: %s", model)
    return model


def get_manufacturer() -> str:
    """Query the manufacturer of the connected device.

    Returns:
        The manufacturer string (e.g. ``"samsung"`` or ``"Google"``).
    """
    manufacturer: str = execute_adb("shell getprop ro.product.manufacturer")
    logger.info("Manufacturer: %s", manufacturer)
    return manufacturer


def get_usb_debugging_status() -> str:
    """Query whether USB debugging is enabled on the device.

    Returns:
        ``"enabled"`` or ``"disabled"``.
    """
    try:
        value: str = execute_adb("shell settings get global adb_enabled")
        status = "enabled" if value.strip() == "1" else "disabled"
    except (ADBCommandError, ADBTimeoutError):
        status = "unknown"
    logger.info("USB debugging: %s", status)
    return status


def get_default_sms_app() -> str:
    """Query the default SMS application package name.

    Returns:
        The package name string (e.g. ``"com.google.android.apps.messaging"``),
        or ``"unknown"`` if the query fails.
    """
    try:
        value: str = execute_adb("shell settings get secure sms_default_application")
        app = value.strip() if value.strip() and value.strip() != "null" else "unknown"
    except (ADBCommandError, ADBTimeoutError):
        app = "unknown"
    logger.info("Default SMS app: %s", app)
    return app


def get_sim_count() -> str:
    """Query the number of active SIM cards.

    Returns:
        A string representing the SIM count (e.g. ``"1"``, ``"2"``),
        or ``"unknown"`` if the query fails.
    """
    try:
        value: str = execute_adb(
            "shell settings get global multi_sim_data_call"
        )
        # Try a more reliable approach via telephony
        sim_info: str = execute_adb(
            "shell service call iphonesubinfo 1"
        )
        # Fallback: count SIM-related entries
        sub_list: str = execute_adb(
            "shell content query --uri content://telephony/siminfo"
        )
        # Count rows returned
        rows = [line for line in sub_list.splitlines() if line.startswith("Row:")]
        count = str(len(rows)) if rows else "1"
    except (ADBCommandError, ADBTimeoutError):
        count = "unknown"
    logger.info("SIM count: %s", count)
    return count


def get_default_sms_sim() -> str:
    """Query the default SIM slot used for SMS.

    Returns:
        The SIM subscription ID or slot description,
        or ``"unknown"`` if the query fails.
    """
    try:
        value: str = execute_adb(
            "shell settings get global multi_sim_sms"
        )
        sim = value.strip() if value.strip() and value.strip() != "null" else "default"
    except (ADBCommandError, ADBTimeoutError):
        sim = "unknown"
    logger.info("Default SMS SIM: %s", sim)
    return sim


def get_device_info(serial: str) -> DeviceInfo:
    """Collect all device metadata into a single :class:`DeviceInfo` object.

    Args:
        serial: The device serial number (from :func:`verify_single_device`).

    Returns:
        A populated :class:`DeviceInfo` instance.
    """
    return DeviceInfo(
        serial=serial,
        manufacturer=get_manufacturer(),
        model=get_device_model(),
        android_version=get_android_version(),
        usb_debugging=get_usb_debugging_status(),
        default_sms_app=get_default_sms_app(),
        sim_count=get_sim_count(),
        default_sms_sim=get_default_sms_sim(),
    )
