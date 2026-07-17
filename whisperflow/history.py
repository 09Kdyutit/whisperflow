"""Transcript history — append-only JSONL at ~/.whisperflow/history.jsonl."""

import json
import os
import time

from . import config as cfg


def append(text: str, duration: float, app_name: str = None, config=None):
    try:
        os.makedirs(cfg.CONFIG_DIR, exist_ok=True)
        entry = {
            "ts": time.time(),
            "text": text,
            "duration": round(duration, 2),
            "app": app_name,
        }
        with open(cfg.HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        if config is not None:
            _trim(config.get("max_history"))
    except OSError:
        pass


def recent(n=8):
    """Return up to n most recent entries, newest first."""
    try:
        with open(cfg.HISTORY_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return []
    out = []
    for line in reversed(lines[-n * 2 :]):
        try:
            entry = json.loads(line)
            if entry.get("text"):
                out.append(entry)
        except json.JSONDecodeError:
            continue
        if len(out) >= n:
            break
    return out


def _trim(max_entries):
    """Keep the history file from growing without bound."""
    try:
        with open(cfg.HISTORY_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()
        if len(lines) > max_entries * 2:
            with open(cfg.HISTORY_PATH, "w", encoding="utf-8") as f:
                f.writelines(lines[-max_entries:])
    except OSError:
        pass
