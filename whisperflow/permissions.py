"""macOS permission checks: Accessibility (hotkeys + typing) and Microphone."""

import subprocess


def accessibility_trusted(prompt=False):
    """True if this process is trusted for Accessibility.

    With prompt=True, macOS shows the system dialog pointing the user at
    System Settings (the grant applies to the hosting terminal app).
    """
    try:
        from ApplicationServices import (
            AXIsProcessTrusted,
            AXIsProcessTrustedWithOptions,
            kAXTrustedCheckOptionPrompt,
        )

        if prompt:
            return bool(
                AXIsProcessTrustedWithOptions(
                    {kAXTrustedCheckOptionPrompt: True}
                )
            )
        return bool(AXIsProcessTrusted())
    except Exception:
        return False


def microphone_status():
    """'authorized' | 'denied' | 'undetermined' | 'restricted' | 'unknown'"""
    try:
        from AVFoundation import (
            AVCaptureDevice,
            AVMediaTypeAudio,
        )

        status = AVCaptureDevice.authorizationStatusForMediaType_(
            AVMediaTypeAudio
        )
        return {
            0: "undetermined",
            1: "restricted",
            2: "denied",
            3: "authorized",
        }.get(status, "unknown")
    except Exception:
        return "unknown"


def request_microphone():
    """Trigger the system microphone prompt if not yet determined."""
    try:
        from AVFoundation import AVCaptureDevice, AVMediaTypeAudio

        AVCaptureDevice.requestAccessForMediaType_completionHandler_(
            AVMediaTypeAudio, lambda granted: None
        )
    except Exception:
        pass


def open_accessibility_settings():
    subprocess.run(
        ["open",
         "x-apple.systempreferences:com.apple.preference.security"
         "?Privacy_Accessibility"],
        check=False,
    )


def open_microphone_settings():
    subprocess.run(
        ["open",
         "x-apple.systempreferences:com.apple.preference.security"
         "?Privacy_Microphone"],
        check=False,
    )


def open_keyboard_settings():
    subprocess.run(
        ["open", "x-apple.systempreferences:com.apple.Keyboard-Settings"
         ".extension"],
        check=False,
    )
