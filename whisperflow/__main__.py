"""Entry point: `python -m whisperflow` launches the menu-bar app.

Also provides:
  python -m whisperflow --transcribe FILE.wav   one-off transcription test
  python -m whisperflow --doctor                environment / permission check
"""

import argparse
import sys


def _cmd_transcribe(path):
    import wave

    import numpy as np

    from .config import Config
    from .transcribe import Transcriber

    with wave.open(path, "rb") as wf:
        if wf.getsampwidth() != 2 or wf.getframerate() != 16000 or wf.getnchannels() != 1:
            sys.exit(
                f"{path} must be 16 kHz mono 16-bit WAV. Convert with:\n"
                f"  afconvert -f WAVE -d LEI16@16000 -c 1 input.aiff output.wav"
            )
        frames = wf.readframes(wf.getnframes())
    audio = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0

    transcriber = Transcriber(Config())
    print("Loading model (downloads on first run)…", file=sys.stderr)
    transcriber.preload()
    text = transcriber.transcribe(audio)
    print(text)


def _cmd_doctor():
    import platform

    from . import __version__
    from .audio import input_device_name
    from .config import Config
    from . import permissions

    config = Config()
    print(f"WhisperFlow v{__version__}")
    print(f"  Python:        {platform.python_version()} ({platform.machine()})")
    print(f"  Model:         {config.get('model_repo')}")
    print(f"  Hotkey:        {config.get('hotkey')}")
    print(f"  Input device:  {input_device_name() or 'NONE FOUND'}")
    print(f"  Microphone:    {permissions.microphone_status()}")
    trusted = permissions.accessibility_trusted()
    print(f"  Accessibility: {'trusted' if trusted else 'NOT TRUSTED'}")
    if not trusted:
        print(
            "\n  → Grant Accessibility to your terminal app in\n"
            "    System Settings › Privacy & Security › Accessibility,\n"
            "    then relaunch WhisperFlow."
        )
    try:
        import mlx_whisper  # noqa: F401
        print("  mlx-whisper:   installed")
    except ImportError:
        print("  mlx-whisper:   MISSING — run ./run.sh to install")


def main():
    parser = argparse.ArgumentParser(prog="whisperflow")
    parser.add_argument("--transcribe", metavar="WAV",
                        help="transcribe a 16 kHz mono WAV file and exit")
    parser.add_argument("--doctor", action="store_true",
                        help="print environment and permission status")
    args = parser.parse_args()

    if args.transcribe:
        _cmd_transcribe(args.transcribe)
    elif args.doctor:
        _cmd_doctor()
    else:
        from .app import main as run_app
        run_app()


if __name__ == "__main__":
    main()
