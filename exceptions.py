"""Custom exceptions for the ElectionSMS application.

Each exception maps to a specific, recoverable error condition so that
callers can catch exactly the failure mode they care about and display
a helpful message to the user.

Every exception exposes a :meth:`details` method that returns a
structured **Problem → Cause → Suggested Fix** diagnostic string.
"""


class _DiagnosticMixin:
    """Mixin that gives every ADB exception a ``details()`` method.

    Subclasses set ``_problem``, ``_cause``, and ``_fix`` as instance
    attributes; this mixin formats them into a consistent block.
    """

    _problem: str
    _cause: str
    _fix: str

    def details(self) -> str:
        """Return a multi-line diagnostic string."""
        return (
            f"  Problem:        {self._problem}\n"
            f"  Cause:          {self._cause}\n"
            f"  Suggested Fix:  {self._fix}"
        )


class ADBNotFoundError(_DiagnosticMixin, Exception):
    """Raised when the ``adb`` executable cannot be found in any search location."""

    def __init__(self, message: str = "ADB is not installed or not found in any search location.") -> None:
        super().__init__(message)
        self._problem = "ADB executable not found."
        self._cause = (
            "adb.exe is not on the system PATH, not in tools/platform-tools/, "
            "and no valid path was set in config.ADB_EXECUTABLE."
        )
        self._fix = (
            "Install Android SDK Platform-Tools "
            "(https://developer.android.com/tools/releases/platform-tools), "
            "place them in tools/platform-tools/, or set ADB_EXECUTABLE in config.py."
        )


class NoDeviceConnectedError(_DiagnosticMixin, Exception):
    """Raised when no Android device is detected by ADB."""

    def __init__(self, message: str = "No Android device is connected.") -> None:
        super().__init__(message)
        self._problem = "No Android device detected."
        self._cause = "No device is plugged in, or USB debugging is not enabled on the device."
        self._fix = (
            "Connect your Android device via USB, enable USB debugging in "
            "Developer Options, and try again."
        )


class MultipleDevicesError(_DiagnosticMixin, Exception):
    """Raised when more than one Android device is connected.

    This project expects exactly one device at a time to avoid
    accidentally sending SMS from the wrong device.
    """

    def __init__(self, count: int = 0) -> None:
        msg = (
            f"Multiple devices detected ({count}). "
            "Please connect only one device."
        )
        super().__init__(msg)
        self.count = count
        self._problem = f"Multiple devices detected ({count})."
        self._cause = "More than one USB device or Android emulator is connected."
        self._fix = "Disconnect all extra devices/emulators so only one remains."


class DeviceUnauthorizedError(_DiagnosticMixin, Exception):
    """Raised when the connected device has not authorized USB debugging.

    The user must tap *Allow USB debugging* on the device screen.
    """

    def __init__(self, serial: str = "") -> None:
        msg = (
            f"Device {serial!r} is unauthorized. "
            "Please allow USB debugging on the device."
        )
        super().__init__(msg)
        self.serial = serial
        self._problem = f"Device {serial!r} is unauthorized."
        self._cause = "USB debugging authorization has not been granted on the phone."
        self._fix = (
            "Unlock your phone, tap 'Allow USB debugging' on the dialog, "
            "and re-run the application."
        )


class ADBTimeoutError(_DiagnosticMixin, Exception):
    """Raised when an ADB command exceeds the allowed timeout."""

    def __init__(self, command: str, timeout_seconds: int) -> None:
        msg = f"ADB command timed out after {timeout_seconds}s: {command}"
        super().__init__(msg)
        self.command = command
        self.timeout_seconds = timeout_seconds
        self._problem = f"ADB command timed out after {timeout_seconds} seconds."
        self._cause = (
            "The device may be unresponsive, the ADB server may be hung, "
            "or the USB connection is unstable."
        )
        self._fix = (
            "Run 'adb kill-server' then 'adb start-server', "
            "reconnect the USB cable, and try again."
        )


class ADBCommandError(_DiagnosticMixin, Exception):
    """Raised when an ADB command exits with a non-zero return code."""

    def __init__(self, command: str, returncode: int, stderr: str) -> None:
        msg = (
            f"ADB command failed (exit {returncode}): {command}\n"
            f"  stderr: {stderr.strip()}"
        )
        super().__init__(msg)
        self.command = command
        self.returncode = returncode
        self.stderr = stderr
        self._problem = f"ADB command '{command}' failed with exit code {returncode}."
        self._cause = f"stderr: {stderr.strip() or '(no output)'}"
        self._fix = (
            "Check that the device is connected and authorized, "
            "review the command and stderr output, and retry."
        )
