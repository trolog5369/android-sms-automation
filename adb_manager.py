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


# ── Data models ───────────────────────────────────────────────────────

@dataclass
class SIMInfo:
    """Metadata for a single physical SIM card.

    Attributes:
        slot: 1-based physical slot number (1 = first slot, 2 = second).
        state: SIM state string from ``gsm.sim.state``
               (``LOADED``, ``ABSENT``, ``PIN_REQUIRED``, etc.).
        carrier: Operator name from ``persist.radio.simN.spn`` or
                 ``gsm.sim.operator.alpha`` (e.g. ``"airtel"``).
        subscription_id: Android subscription ID (from
                         ``settings get global multi_sim_sms`` et al.).
                         This is *not* the same as the slot number.
        phone_number: MSISDN if Android exposes it; empty string otherwise.
                      Most devices/carriers do not expose this via ADB.
    """

    slot: int = 0
    state: str = ""
    carrier: str = ""
    subscription_id: str = ""
    phone_number: str = ""


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
        sim_info: List of :class:`SIMInfo` for each detected SIM.
        sms_subscription_id: Subscription ID currently set for SMS.
    """

    serial: str = ""
    manufacturer: str = ""
    model: str = ""
    android_version: str = ""
    usb_debugging: str = ""
    default_sms_app: str = ""
    sim_info: list = None  # list[SIMInfo]
    sms_subscription_id: str = ""

    def __post_init__(self) -> None:
        if self.sim_info is None:
            self.sim_info = []



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
            stdin=subprocess.DEVNULL,
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

    Queries the Android role manager (``dumpsys role``) which is the
    authoritative source for Android 10+ devices.  Falls back to the
    legacy settings key for older devices.

    Returns:
        The package name string (e.g. ``"com.google.android.apps.messaging"``),
        or ``"unknown"`` if the query fails.
    """
    # Primary: Android Role Manager (Android 10+)
    try:
        role_output: str = execute_adb("shell dumpsys role")
        for line in role_output.splitlines():
            line = line.strip()
            if line.startswith("holders=") and line != "holders=":
                # Find the "holders=" line immediately after the SMS role block
                pkg = line.split("=", 1)[1].strip()
                if pkg and pkg != "null":
                    logger.info("Default SMS app (role): %s", pkg)
                    return pkg
    except (ADBCommandError, ADBTimeoutError):
        pass

    # Fallback: parse SMS role block explicitly
    try:
        role_output = execute_adb("shell dumpsys role")
        in_sms_block = False
        for line in role_output.splitlines():
            stripped = line.strip()
            if "android.app.role.SMS" in stripped:
                in_sms_block = True
            if in_sms_block and stripped.startswith("holders="):
                pkg = stripped.split("=", 1)[1].strip()
                if pkg and pkg != "null":
                    logger.info("Default SMS app (role block): %s", pkg)
                    return pkg
    except (ADBCommandError, ADBTimeoutError):
        pass

    # Last resort: legacy settings keys
    for key in ("secure sms_default_application", "global sms_default_application"):
        try:
            value: str = execute_adb(f"shell settings get {key}")
            v = value.strip()
            if v and v not in ("null", "N/A"):
                logger.info("Default SMS app (settings/%s): %s", key, v)
                return v
        except (ADBCommandError, ADBTimeoutError):
            continue

    logger.warning("Could not determine default SMS app.")
    return "unknown"


def get_sim_info() -> list:
    """Detect all SIM cards using permission-free ``getprop`` APIs.

    Does **not** use ``content://telephony/siminfo`` (requires system UID)
    or any API that needs PHONE permission.  Parses the following props:

    * ``ro.telephony.sim_slots.count``    — total physical slots
    * ``gsm.sim.state``                   — comma-separated state per slot
    * ``gsm.sim.operator.alpha``          — comma-separated carrier per slot
    * ``persist.radio.simN.spn``          — human-readable carrier name

    Subscription IDs (for multi-SIM routing) are read separately from
    ``settings get global multi_sim_sms`` / ``multi_sim_data_call``.

    Returns:
        A list of :class:`SIMInfo` objects, one per detected SIM.
        Empty list if the device is single-SIM or props are unavailable.
    """
    sims: list[SIMInfo] = []

    # ── 1. How many physical slots? ──────────────────────────────────────
    try:
        slot_count_raw: str = execute_adb("shell getprop ro.telephony.sim_slots.count")
        slot_count: int = int(slot_count_raw.strip()) if slot_count_raw.strip().isdigit() else 1
    except (ADBCommandError, ADBTimeoutError, ValueError):
        slot_count = 1

    # ── 2. Per-slot state array ──────────────────────────────────────────
    try:
        states_raw: str = execute_adb("shell getprop gsm.sim.state")
        states: list[str] = [s.strip() for s in states_raw.split(",")]
    except (ADBCommandError, ADBTimeoutError):
        states = ["UNKNOWN"] * slot_count

    # Pad to slot_count
    while len(states) < slot_count:
        states.append("UNKNOWN")

    # ── 3. Per-slot operator alpha (carrier) array ──────────────────────
    try:
        carriers_raw: str = execute_adb("shell getprop gsm.sim.operator.alpha")
        carriers: list[str] = [c.strip() for c in carriers_raw.split(",")]
    except (ADBCommandError, ADBTimeoutError):
        carriers = [""] * slot_count

    while len(carriers) < slot_count:
        carriers.append("")

    # ── 4. Build per-SIM records ────────────────────────────────────────
    for slot_idx in range(slot_count):
        slot_num = slot_idx + 1  # 1-based for display
        state = states[slot_idx] if slot_idx < len(states) else "UNKNOWN"

        # Carrier: prefer persist.radio.simN.spn (richer name), else gsm prop
        spn_carrier: str = ""
        try:
            spn_raw = execute_adb(f"shell getprop persist.radio.sim{slot_num}.spn")
            spn_carrier = spn_raw.strip()
        except (ADBCommandError, ADBTimeoutError):
            pass

        carrier = spn_carrier or (carriers[slot_idx] if slot_idx < len(carriers) else "")

        # Phone number: try iphonesubinfo (slot-specific call) — often empty on real devices
        phone_number = ""
        try:
            # service call iphonesubinfo 15 i32 <slot_idx> returns line 1 for that slot
            ph_raw = execute_adb(f"shell service call iphonesubinfo 15 i32 {slot_idx}")
            # Parse parceled string: extract chars between quotes in result parcel
            import re
            parts = re.findall(r"'([^']+)'", ph_raw)
            candidate = "".join(parts).strip().replace(".", "")
            if candidate and candidate not in ("null", "N/A"):
                phone_number = candidate
        except (ADBCommandError, ADBTimeoutError, ImportError):
            pass

        sim = SIMInfo(
            slot=slot_num,
            state=state,
            carrier=carrier or "unknown",
            subscription_id="",      # filled in next step
            phone_number=phone_number,
        )
        sims.append(sim)

    # ── 5. Map subscription IDs & detailed SIM info ──────────────────────
    # Android assigns subscription IDs (sub IDs) that are NOT the same as slot
    # numbers. We query dumpsys isub or dumpsys telephony.registry.
    # dumpsys isub output example:
    #   Logical SIM slot 0: subId=2
    #   Logical SIM slot 1: subId=1
    try:
        isub_output = execute_adb("shell dumpsys isub")
        import re
        # Parse slot -> subId mapping
        # "Logical SIM slot 0: subId=2"
        slot_map = re.findall(r"Logical SIM slot (\d+):\s*subId=(\d+)", isub_output)
        for s_idx_str, sub_id in slot_map:
            s_idx = int(s_idx_str)
            if s_idx < len(sims):
                sims[s_idx].subscription_id = sub_id

        # Also parse SubscriptionInfoInternal for carrier/number if available
        # e.g., simSlotIndex=1 ... carrierName=Vi India
        sub_blocks = re.findall(r"id=(\d+).*?simSlotIndex=(-?\d+).*?carrierName=([^ ]+)", isub_output)
        for sub_id, slot_idx_str, carrier_name in sub_blocks:
            s_idx = int(slot_idx_str)
            if 0 <= s_idx < len(sims):
                if not sims[s_idx].subscription_id:
                    sims[s_idx].subscription_id = sub_id
                if carrier_name and carrier_name != "null":
                    sims[s_idx].carrier = carrier_name
    except (ADBCommandError, ADBTimeoutError, ImportError):
        pass

    # Fallback to dumpsys telephony.registry if subscription_id still empty
    if any(not sim.subscription_id for sim in sims):
        try:
            registry = execute_adb("shell dumpsys telephony.registry")
            current_phone_id: int = -1
            sub_id_map: dict[int, str] = {}  # phone_id -> sub_id
            for line in registry.splitlines():
                stripped = line.strip()
                if stripped.startswith("Phone Id="):
                    try:
                        current_phone_id = int(stripped.split("=")[1])
                    except ValueError:
                        current_phone_id = -1
                if current_phone_id >= 0 and "mSubscriptionId=" in stripped:
                    try:
                        sub_id_val = stripped.split("mSubscriptionId=")[1].split()[0]
                        if sub_id_val.lstrip("-").isdigit() and int(sub_id_val) > 0:
                            if current_phone_id not in sub_id_map:
                                sub_id_map[current_phone_id] = sub_id_val
                    except (IndexError, ValueError):
                        pass

            for sim in sims:
                if not sim.subscription_id:
                    phone_id = sim.slot - 1
                    if phone_id in sub_id_map:
                        sim.subscription_id = sub_id_map[phone_id]
        except (ADBCommandError, ADBTimeoutError):
            pass

    logger.info("SIM info: %s", [(s.slot, s.carrier, s.subscription_id) for s in sims])
    return sims


def get_sms_subscription_id() -> str:
    """Return the current Android subscription ID used for SMS.

    This is read from ``settings get global multi_sim_sms`` and represents
    an Android subscription ID, **not** a slot number.  Returns an empty
    string if the device is single-SIM or the setting is not configured.
    """
    try:
        value: str = execute_adb("shell settings get global multi_sim_sms")
        v = value.strip()
        if v and v not in ("null", "-1", "N/A"):
            logger.info("SMS subscription ID: %s", v)
            return v
    except (ADBCommandError, ADBTimeoutError):
        pass
    return ""


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
        sim_info=get_sim_info(),
        sms_subscription_id=get_sms_subscription_id(),
    )
