"""Configuration — persisted as JSON at ~/.whisperflow/config.json."""

import json
import os
import threading

CONFIG_DIR = os.path.expanduser("~/.whisperflow")
CONFIG_PATH = os.path.join(CONFIG_DIR, "config.json")
HISTORY_PATH = os.path.join(CONFIG_DIR, "history.jsonl")

MODELS = [
    # (menu label, hugging face repo, approx download size)
    ("Turbo (recommended, 440 MB)", "mlx-community/whisper-large-v3-turbo-q4", "440 MB"),
    ("Turbo HQ (1.5 GB)", "mlx-community/whisper-large-v3-turbo", "1.5 GB"),
    ("Small (460 MB)", "mlx-community/whisper-small-mlx", "460 MB"),
    ("Base (fastest, 140 MB)", "mlx-community/whisper-base-mlx", "140 MB"),
]

HOTKEYS = [
    ("Double-tap Shift ⇧⇧", "double_shift"),
    ("fn (Globe)", "fn"),
    ("Right Option ⌥", "right_option"),
    ("Right Command ⌘", "right_command"),
]

LANGUAGES = [
    ("Auto-detect", None),
    ("English", "en"),
    ("Spanish", "es"),
    ("French", "fr"),
    ("German", "de"),
    ("Hindi", "hi"),
    ("Portuguese", "pt"),
    ("Japanese", "ja"),
    ("Chinese", "zh"),
]

DEFAULTS = {
    "model_repo": "mlx-community/whisper-large-v3-turbo-q4",
    "hotkey": "double_shift",        # double_shift | fn | right_option | right_command
    "language": None,                # None = auto-detect
    "insert_mode": "paste",          # paste | type
    "sounds": True,
    "trailing_space": True,
    "spoken_commands": True,         # "new line" / "new paragraph" -> newlines
    "replacements": {},              # custom dictionary: {"heard": "corrected"}
    "max_history": 200,
}

_lock = threading.Lock()


class Config:
    def __init__(self):
        self._data = dict(DEFAULTS)
        self.load()

    def load(self):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                for key, default in DEFAULTS.items():
                    if key not in stored:
                        continue
                    value = stored[key]
                    # A hand-edited config with the wrong type falls back to
                    # the default instead of crashing later.
                    if key == "language":
                        if value is None or isinstance(value, str):
                            self._data[key] = value
                    elif isinstance(value, type(default)):
                        self._data[key] = value
        except (OSError, ValueError):
            # Missing, unreadable, non-JSON, or non-UTF-8 config → keep defaults.
            # (JSONDecodeError and UnicodeDecodeError are both ValueError.)
            pass

    def save(self):
        with _lock:
            os.makedirs(CONFIG_DIR, exist_ok=True)
            tmp = CONFIG_PATH + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, indent=2, ensure_ascii=False)
            os.replace(tmp, CONFIG_PATH)

    def get(self, key):
        return self._data.get(key, DEFAULTS.get(key))

    def set(self, key, value):
        self._data[key] = value
        self.save()
