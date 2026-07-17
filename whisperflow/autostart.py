"""Start-at-login support via a per-user macOS LaunchAgent.

Installs ~/Library/LaunchAgents/com.whisperflow.agent.plist so launchd starts
WhisperFlow at login and relaunches it if it ever crashes (but not when the
user quits it cleanly). No terminal window is involved.
"""

import os
import plistlib
import subprocess

LABEL = "com.whisperflow.agent"
PLIST_PATH = os.path.expanduser(
    f"~/Library/LaunchAgents/{LABEL}.plist"
)
LOG_PATH = os.path.expanduser("~/.whisperflow/agent.log")

# Project root is the parent of this package directory.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUN_SH = os.path.join(PROJECT_ROOT, "run.sh")


def is_installed():
    return os.path.exists(PLIST_PATH)


def _plist_dict():
    return {
        "Label": LABEL,
        "ProgramArguments": ["/bin/bash", RUN_SH],
        "WorkingDirectory": PROJECT_ROOT,
        "RunAtLoad": True,
        # Relaunch only on a crash (non-zero exit). A clean Quit from the menu
        # exits 0 and stays quit.
        "KeepAlive": {"SuccessfulExit": False},
        "ProcessType": "Interactive",
        "StandardOutPath": LOG_PATH,
        "StandardErrorPath": LOG_PATH,
        # launchd hands processes a bare PATH; add Homebrew so run.sh finds
        # python3 and the venv resolves.
        "EnvironmentVariables": {
            "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin",
        },
    }


def install():
    """Write the plist and (re)load it so it's active now and at every login."""
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    os.makedirs(os.path.dirname(PLIST_PATH), exist_ok=True)
    with open(PLIST_PATH, "wb") as f:
        plistlib.dump(_plist_dict(), f)
    _reload()
    return True


def uninstall():
    """Unload and remove the LaunchAgent (does not stop the running app)."""
    _bootout()
    try:
        os.remove(PLIST_PATH)
    except FileNotFoundError:
        pass
    return True


# ------------------------------------------------------------ launchctl

def _uid():
    return os.getuid()


def _bootout():
    subprocess.run(
        ["launchctl", "bootout", f"gui/{_uid()}/{LABEL}"],
        capture_output=True, text=True,
    )


def _reload():
    # bootout first so a changed plist is picked up; ignore "not loaded".
    _bootout()
    subprocess.run(
        ["launchctl", "bootstrap", f"gui/{_uid()}", PLIST_PATH],
        capture_output=True, text=True,
    )
