"""Android diagnostics module.

Collects and displays a comprehensive health report covering ADB
status, device connectivity, and SMS readiness.  All queries are
wrapped in error handling so the report is always printed — missing
fields show ``N/A`` rather than crashing.

This module does **not** send SMS or open any apps.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from adb_manager import (
    DeviceInfo,
    discover_adb,
    get_adb_path,
    get_device_info,
    verify_single_device,
)
from config import SEPARATOR
from exceptions import (
    ADBCommandError,
    ADBNotFoundError,
    ADBTimeoutError,
    DeviceUnauthorizedError,
    MultipleDevicesError,
    NoDeviceConnectedError,
)

logger: logging.Logger = logging.getLogger(__name__)


@dataclass
class DiagnosticsReport:
    """Complete health-check result.

    Attributes:
        adb_executable: Absolute path to the discovered ``adb.exe``, or ``None``.
        adb_status: Human-readable ADB status (``OK``, ``NOT FOUND``, etc.).
        phone_connected: ``YES``, ``NO``, or an error description.
        serial_number: Device serial, or ``N/A``.
        manufacturer: Device manufacturer, or ``N/A``.
        device_model: Device model name, or ``N/A``.
        android_version: OS version string, or ``N/A``.
        usb_debugging: ``enabled``, ``disabled``, or ``N/A``.
        default_sms_app: Package name, or ``N/A``.
        sim_count: Number of SIMs, or ``N/A``.
        default_sms_sim: Default SMS SIM info, or ``N/A``.
        ready_to_send: Overall readiness boolean.
        error_details: Formatted error string if something went wrong, or ``None``.
    """

    adb_executable: Optional[str] = None
    adb_status: str = "UNKNOWN"
    phone_connected: str = "NO"
    serial_number: str = "N/A"
    manufacturer: str = "N/A"
    device_model: str = "N/A"
    android_version: str = "N/A"
    usb_debugging: str = "N/A"
    default_sms_app: str = "N/A"
    sim_count: str = "N/A"
    default_sms_sim: str = "N/A"
    ready_to_send: bool = False
    error_details: Optional[str] = None


def run_diagnostics() -> DiagnosticsReport:
    """Collect and return a full Android diagnostics report.

    This function never raises — all exceptions are caught and
    translated into descriptive report fields.

    Returns:
        A populated :class:`DiagnosticsReport`.
    """
    report = DiagnosticsReport()

    # ── Step 1: Discover ADB ─────────────────────────────────────────
    try:
        adb_path: str = discover_adb()
        report.adb_executable = adb_path
        report.adb_status = "OK"
        logger.info("Diagnostics: ADB found at %s", adb_path)
    except ADBNotFoundError as exc:
        report.adb_status = "NOT FOUND"
        report.error_details = exc.details()
        logger.error("Diagnostics: ADB not found.")
        _print_report(report)
        return report

    # ── Step 2: Verify device ────────────────────────────────────────
    try:
        serial: str = verify_single_device()
        report.phone_connected = "YES"
        report.serial_number = serial
        logger.info("Diagnostics: Device connected — %s", serial)
    except NoDeviceConnectedError as exc:
        report.phone_connected = "NO"
        report.error_details = exc.details()
        logger.error("Diagnostics: No device connected.")
        _print_report(report)
        return report
    except MultipleDevicesError as exc:
        report.phone_connected = f"MULTIPLE ({exc.count})"
        report.error_details = exc.details()
        logger.error("Diagnostics: Multiple devices.")
        _print_report(report)
        return report
    except DeviceUnauthorizedError as exc:
        report.phone_connected = "UNAUTHORIZED"
        report.serial_number = exc.serial
        report.error_details = exc.details()
        logger.error("Diagnostics: Device unauthorized.")
        _print_report(report)
        return report
    except (ADBCommandError, ADBTimeoutError) as exc:
        report.phone_connected = "ERROR"
        report.error_details = exc.details()
        logger.error("Diagnostics: ADB command error during device check.")
        _print_report(report)
        return report

    # ── Step 3: Gather device info ───────────────────────────────────
    try:
        info: DeviceInfo = get_device_info(serial)
        report.manufacturer = info.manufacturer or "N/A"
        report.device_model = info.model or "N/A"
        report.android_version = info.android_version or "N/A"
        report.usb_debugging = info.usb_debugging or "N/A"
        report.default_sms_app = info.default_sms_app or "N/A"
        report.sim_count = info.sim_count or "N/A"
        report.default_sms_sim = info.default_sms_sim or "N/A"
        report.ready_to_send = True
        logger.info("Diagnostics: Device info collected successfully.")
    except (ADBCommandError, ADBTimeoutError) as exc:
        report.error_details = exc.details()
        logger.error("Diagnostics: Failed to gather device info.")

    _print_report(report)
    return report


def _print_report(report: DiagnosticsReport) -> None:
    """Print the diagnostics report to stdout.

    Args:
        report: The :class:`DiagnosticsReport` to display.
    """
    ready_label: str = "YES ✔" if report.ready_to_send else "NO ✘"

    print()
    print(SEPARATOR)
    print("  Android Diagnostics")
    print(SEPARATOR)
    print()
    print(f"  ADB Executable  : {report.adb_executable or 'NOT FOUND'}")
    print(f"  ADB Status      : {report.adb_status}")
    print()
    print(f"  Phone Connected : {report.phone_connected}")
    print(f"  Serial Number   : {report.serial_number}")
    print(f"  Manufacturer    : {report.manufacturer}")
    print(f"  Device Model    : {report.device_model}")
    print(f"  Android Version : {report.android_version}")
    print(f"  USB Debugging   : {report.usb_debugging}")
    print()
    print(f"  Default SMS App : {report.default_sms_app}")
    print(f"  SIM Count       : {report.sim_count}")
    print(f"  Default SMS SIM : {report.default_sms_sim}")
    print()
    print(f"  READY TO SEND   : {ready_label}")
    print()

    if report.error_details:
        print(SEPARATOR)
        print("  Error Details")
        print(SEPARATOR)
        print()
        print(report.error_details)
        print()

    print(SEPARATOR)
    print()
