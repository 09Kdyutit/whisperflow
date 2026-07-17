"""Insert text into the frontmost app.

Default mode pastes via the clipboard (fast, reliable for long text) and then
restores whatever was on the clipboard before. "Type" mode synthesizes
keystrokes directly for apps that block pasting. Both need Accessibility trust.
"""

import threading
import time

from AppKit import NSPasteboard, NSPasteboardItem, NSPasteboardTypeString
import Quartz

KVK_ANSI_V = 9
CLIPBOARD_RESTORE_DELAY = 0.6
TYPE_CHUNK = 20
TYPE_CHUNK_DELAY = 0.008


def insert_text(text: str, mode: str = "paste"):
    if not text:
        return
    if mode == "type":
        _type_text(text)
    else:
        _paste_text(text)


# ----------------------------------------------------------------- paste


def _snapshot_pasteboard(pb):
    """Capture current pasteboard contents (all types we can read)."""
    saved = []
    try:
        for item in pb.pasteboardItems() or []:
            entry = []
            for t in item.types() or []:
                try:
                    data = item.dataForType_(t)
                    if data is not None:
                        entry.append((t, data))
                except Exception:
                    pass
            if entry:
                saved.append(entry)
    except Exception:
        pass
    return saved


def _write_items(pb, saved):
    pb.clearContents()
    items = []
    for entry in saved:
        item = NSPasteboardItem.alloc().init()
        for t, data in entry:
            try:
                item.setData_forType_(data, t)
            except Exception:
                pass
        items.append(item)
    if items:
        pb.writeObjects_(items)


# All clipboard state is guarded by one lock so overlapping dictations (two
# within CLIPBOARD_RESTORE_DELAY) can never clobber each other or lose the
# user's real clipboard. `_pending` remembers the true pre-dictation snapshot
# and the changeCount our last paste produced.
_paste_lock = threading.Lock()
_pending = None  # {"saved": [...], "our_change_count": int}


def _paste_text(text: str):
    pb = NSPasteboard.generalPasteboard()

    with _paste_lock:
        global _pending
        # If a restore is still pending and the pasteboard is untouched since
        # our own last paste, the live contents are just that transient
        # transcript — the real original lives in `_pending`. Reuse it so a
        # rapid second dictation doesn't snapshot our own text as "original".
        # Otherwise (the user copied something in between) snapshot live.
        if _pending is not None and pb.changeCount() == _pending["our_change_count"]:
            saved = _pending["saved"]
        else:
            saved = _snapshot_pasteboard(pb)

        pb.clearContents()
        pb.setString_forType_(text, NSPasteboardTypeString)
        our_change_count = pb.changeCount()
        _pending = {"saved": saved, "our_change_count": our_change_count}

    _press_cmd_v()

    def restore():
        time.sleep(CLIPBOARD_RESTORE_DELAY)
        with _paste_lock:
            global _pending
            # Superseded by a newer paste: that paste now owns restoration.
            if _pending is None or _pending["our_change_count"] != our_change_count:
                return
            # The user copied something after our paste: leave it alone.
            if pb.changeCount() != our_change_count:
                _pending = None
                return
            try:
                _write_items(pb, _pending["saved"])
            except Exception:
                pass
            _pending = None

    threading.Thread(target=restore, daemon=True).start()


def _press_cmd_v():
    source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    down = Quartz.CGEventCreateKeyboardEvent(source, KVK_ANSI_V, True)
    up = Quartz.CGEventCreateKeyboardEvent(source, KVK_ANSI_V, False)
    Quartz.CGEventSetFlags(down, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventSetFlags(up, Quartz.kCGEventFlagMaskCommand)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
    Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)


# ------------------------------------------------------------------ type


def _type_text(text: str):
    """Synthesize unicode keystrokes in small chunks."""
    source = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStateHIDSystemState)
    for i in range(0, len(text), TYPE_CHUNK):
        chunk = text[i : i + TYPE_CHUNK]
        # CGEventKeyboardSetUnicodeString wants UTF-16 code units, not
        # codepoints — they differ for emoji and other non-BMP characters.
        utf16_units = len(chunk.encode("utf-16-le")) // 2
        down = Quartz.CGEventCreateKeyboardEvent(source, 0, True)
        Quartz.CGEventKeyboardSetUnicodeString(down, utf16_units, chunk)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, down)
        up = Quartz.CGEventCreateKeyboardEvent(source, 0, False)
        Quartz.CGEventKeyboardSetUnicodeString(up, utf16_units, chunk)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, up)
        time.sleep(TYPE_CHUNK_DELAY)
