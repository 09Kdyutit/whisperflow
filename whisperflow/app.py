"""WhisperFlow menu-bar app: wires hotkey → recorder → whisper → insertion."""

import os
import threading
import time

import objc
from AppKit import (
    NSApplication,
    NSApplicationActivationPolicyAccessory,
    NSImage,
    NSMenu,
    NSMenuItem,
    NSPasteboard,
    NSPasteboardTypeString,
    NSSound,
    NSStatusBar,
    NSVariableStatusItemLength,
    NSWorkspace,
)
from Foundation import NSObject, NSTimer
from PyObjCTools import AppHelper

from . import APP_NAME, __version__, autostart, history, permissions
from .audio import Recorder, input_device_name
from .config import Config, HOTKEYS, LANGUAGES, MODELS
from .hotkey import HotkeyMonitor
from .insert import insert_text
from .overlay import Overlay
from .transcribe import Transcriber

IDLE = "idle"
RECORDING = "recording"
TRANSCRIBING = "transcribing"

TAP_MAX_SEC = 0.3          # press shorter than this is a "tap", not a hold
DOUBLE_TAP_WINDOW = 0.45   # two taps within this window = hands-free lock
MAX_RECORD_SEC = 300       # safety cap: a forgotten hands-free lock auto-stops

HOTKEY_LABELS = {
    "double_shift": "⇧⇧",
    "fn": "fn",
    "right_option": "right ⌥",
    "right_command": "right ⌘",
}


def _model_is_cached(repo):
    """True if the Hugging Face snapshot for `repo` is already on disk."""
    try:
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id=repo, local_files_only=True)
        return True
    except Exception:
        return False


class AppController(NSObject):
    """NSObject subclass so it can be a menu target / delegate."""

    def init(self):
        self = objc.super(AppController, self).init()
        if self is None:
            return None

        self.config = Config()
        self.recorder = Recorder()
        self.transcriber = Transcriber(self.config)
        self.overlay = Overlay()
        self.state = IDLE
        self.locked = False
        self._consume_release = False
        self._press_time = 0.0
        self._last_tap_time = 0.0
        self._stopped_at = 0.0
        self._preload_gen = 0
        self._max_timer = None
        self._model_status = "Loading model…"

        self.hotkey = HotkeyMonitor(
            self.config,
            on_press=self._on_press,
            on_release=self._on_release,
            on_escape=self._on_escape,
            on_tap=self._on_tap,
            on_double_tap=self._on_double_tap,
            on_shift_press=self._on_shift_press,
        )

        self._build_status_item()
        self._start_permission_flow()
        self._preload_model_async()
        return self

    # ----------------------------------------------------------- lifecycle

    def _start_permission_flow(self):
        permissions.request_microphone()
        if permissions.accessibility_trusted(prompt=True):
            self.hotkey.start()
        else:
            self._model_status = "Grant Accessibility access, then relaunch"
            # Poll until trust is granted, then start listening for the hotkey.
            self._trust_timer = (
                NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                    2.0, True, self._check_trust
                )
            )

    def _check_trust(self, timer):
        if permissions.accessibility_trusted():
            timer.invalidate()
            self.hotkey.start()
            self._update_status_line()

    def _preload_model_async(self):
        repo = self.config.get("model_repo")
        size = next((s for _, r, s in MODELS if r == repo), "")
        if _model_is_cached(repo) or not size:
            self._model_status = "Loading model…"
        else:
            self._model_status = f"Downloading model ({size})…"
        self._update_status_line()

        self._preload_gen += 1
        gen = self._preload_gen

        def work():
            try:
                self.transcriber.preload()
                AppHelper.callAfter(self._model_ready, gen)
            except Exception as exc:  # no internet on first run, disk full, …
                AppHelper.callAfter(self._model_failed, gen, str(exc))

        threading.Thread(target=work, daemon=True).start()

    def _model_ready(self, gen):
        if gen != self._preload_gen:
            return  # a newer model switch superseded this load
        self._model_status = None
        self._update_status_line()
        self._refresh_model_checkmarks()

    def _model_failed(self, gen, message):
        if gen != self._preload_gen:
            return
        self._model_status = "Model load failed — check internet, then pick a model to retry"
        self._update_status_line()
        self.overlay.show_message("Model download failed", 2.5)
        print(f"[whisperflow] model load failed: {message}")

    # -------------------------------------------------------------- hotkey

    def _on_press(self):
        if self.state == RECORDING and self.locked:
            # Tap while hands-free: stop and transcribe.
            self._consume_release = True
            self._stop_and_transcribe()
            return
        if self.state == TRANSCRIBING:
            self.overlay.show_message("Still transcribing…", 1.0)
            return
        if self.state != IDLE:
            return

        # Recording always starts un-locked. Whether this becomes a hold, a
        # single tap, or the second tap of a double-tap is decided on release,
        # so a quick tap followed by a genuine hold never engages the lock.
        self._press_time = time.monotonic()
        self._start_recording()

    def _on_release(self):
        if self._consume_release:
            self._consume_release = False
            return
        if self.state != RECORDING:
            return
        if self.locked:
            self.overlay.set_locked(True)
            return  # hands-free: keep recording until the next tap

        held = time.monotonic() - self._press_time
        if held >= TAP_MAX_SEC:
            self._stop_and_transcribe()
            return

        # A quick tap. Two taps within the window engage hands-free on the
        # recording that is already running; a lone tap teaches the gesture.
        now = time.monotonic()
        if now - self._last_tap_time <= DOUBLE_TAP_WINDOW:
            self._last_tap_time = 0.0
            self.locked = True
            self.overlay.set_locked(True)
            self._arm_max_timer()
            return  # keep recording, hands-free
        self._last_tap_time = now
        self._cancel_recording()
        label = HOTKEY_LABELS.get(self.config.get("hotkey"), "fn")
        self.overlay.show_message(
            f"Hold {label} to dictate · double-tap for hands-free", 1.8
        )

    def _on_escape(self):
        if self.state == RECORDING:
            self.locked = False
            self._cancel_recording()
            self.overlay.show_message("Canceled", 1.0)

    # Shift-gesture events (hotkey = double_shift). Recording here is always
    # hands-free: double-tap starts it, a single tap finishes it.

    def _on_shift_press(self):
        # Any clean Shift press ends an in-progress hands-free recording —
        # instantly, on key-down, so stopping never depends on tap timing or
        # hold duration. When idle it does nothing (the double-tap on release
        # is what starts a recording).
        if self.state == RECORDING:
            self._stop_and_transcribe()

    def _on_tap(self):
        # Fallback stop on release; normally _on_shift_press already handled it.
        if self.state == RECORDING:
            self._stop_and_transcribe()

    def _on_double_tap(self):
        if self.state == RECORDING:
            return
        if self.state == TRANSCRIBING:
            # Double-tapping to stop (instead of the single tap) is habit;
            # the first tap of the pair already stopped it, so stay quiet.
            if time.monotonic() - self._stopped_at > DOUBLE_TAP_WINDOW:
                self.overlay.show_message("Still transcribing…", 1.0)
            return
        self.locked = True
        self._start_recording()
        if self.state == RECORDING:
            self._arm_max_timer()

    # ----------------------------------------------------------- recording

    def _start_recording(self):
        if not self.transcriber.is_ready:
            self.locked = False
            self.overlay.show_message(
                self._model_status or "Model is still loading…", 2.0
            )
            return
        if permissions.microphone_status() == "denied":
            self.locked = False
            self.overlay.show_message(
                "Microphone access denied — enable it in System Settings", 2.8
            )
            permissions.open_microphone_settings()
            return
        try:
            self.recorder.start()
        except Exception as exc:
            self.locked = False
            self.overlay.show_message("Microphone unavailable", 2.0)
            print(f"[whisperflow] mic error: {exc}")
            return
        self.state = RECORDING
        self._play_sound("Pop")
        self.overlay.show_listening(
            lambda: self.recorder.level, locked=self.locked
        )
        self._set_icon("mic.fill")
        self._update_status_line()

    def _arm_max_timer(self):
        """Auto-stop a hands-free recording that runs past the safety cap."""
        self._disarm_max_timer()
        self._max_timer = NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
            MAX_RECORD_SEC, False, self._max_timer_fired
        )

    def _disarm_max_timer(self):
        if self._max_timer is not None:
            self._max_timer.invalidate()
            self._max_timer = None

    def _max_timer_fired(self, _timer):
        self._max_timer = None
        if self.state == RECORDING:
            self.overlay.show_message("Reached the recording limit — wrapping up", 1.6)
            self._stop_and_transcribe()

    def _cancel_recording(self):
        self._disarm_max_timer()
        self.recorder.cancel()
        self.state = IDLE
        self.locked = False
        self._set_icon("waveform")
        self._update_status_line()

    def _stop_and_transcribe(self):
        self._disarm_max_timer()
        audio = self.recorder.stop()
        self.state = TRANSCRIBING
        self.locked = False
        self._stopped_at = time.monotonic()
        duration = len(audio) / 16000.0
        self._play_sound("Bottle")

        if duration < 0.25:
            self.state = IDLE
            self.overlay.hide()
            self._set_icon("waveform")
            self._update_status_line()
            return

        self.overlay.show_transcribing()
        self._set_icon("ellipsis.circle")
        self._update_status_line()

        def work():
            try:
                text = self.transcriber.transcribe(audio)
                error = None
            except Exception as exc:
                text, error = "", str(exc)
            AppHelper.callAfter(self._finish_transcription, text, duration, error)

        threading.Thread(target=work, daemon=True).start()

    def _finish_transcription(self, text, duration, error):
        self.state = IDLE
        self._set_icon("waveform")
        self._update_status_line()

        if error:
            self.overlay.show_message("Transcription failed", 2.0)
            print(f"[whisperflow] transcription error: {error}")
            return
        if not text:
            self.overlay.show_message("Didn't catch that", 1.2)
            return

        # Record history before inserting, so the transcript survives even
        # if insertion fails (it stays recoverable from Recent Transcripts).
        app_name = None
        try:
            front = NSWorkspace.sharedWorkspace().frontmostApplication()
            app_name = front.localizedName() if front else None
        except Exception:
            pass
        history.append(text, duration, app_name, self.config)

        out = text + " " if self.config.get("trailing_space") and not text.endswith("\n") else text
        try:
            insert_text(out, self.config.get("insert_mode"))
        except Exception as exc:
            print(f"[whisperflow] insert error: {exc}")
            self.overlay.show_message("Couldn't type — copied to clipboard", 2.2)
            pb = NSPasteboard.generalPasteboard()
            pb.clearContents()
            pb.setString_forType_(text, NSPasteboardTypeString)
            return

        self.overlay.hide()

    # ------------------------------------------------------------ menu bar

    def _build_status_item(self):
        self.status_item = NSStatusBar.systemStatusBar().statusItemWithLength_(
            NSVariableStatusItemLength
        )
        self._set_icon("waveform")

        menu = NSMenu.alloc().init()
        menu.setAutoenablesItems_(False)

        self.status_line = self._add_item(menu, "Starting…", None)
        self.status_line.setEnabled_(False)
        menu.addItem_(NSMenuItem.separatorItem())

        # Recent transcripts (rebuilt each time the menu opens)
        self.history_menu = NSMenu.alloc().init()
        history_item = self._add_item(menu, "Recent Transcripts", None)
        history_item.setSubmenu_(self.history_menu)
        menu.addItem_(NSMenuItem.separatorItem())

        # Model picker
        model_menu = NSMenu.alloc().init()
        self.model_items = []
        for label, repo, _size in MODELS:
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                label, "selectModel:", ""
            )
            item.setTarget_(self)
            item.setRepresentedObject_(repo)
            model_menu.addItem_(item)
            self.model_items.append(item)
        self._add_submenu(menu, "Model", model_menu)
        self._refresh_model_checkmarks()

        # Hotkey picker
        hotkey_menu = NSMenu.alloc().init()
        self.hotkey_items = []
        for label, key in HOTKEYS:
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                label, "selectHotkey:", ""
            )
            item.setTarget_(self)
            item.setRepresentedObject_(key)
            hotkey_menu.addItem_(item)
            self.hotkey_items.append(item)
        hotkey_menu.addItem_(NSMenuItem.separatorItem())
        kb = self._make_item("Using fn? Set Globe key to “Do Nothing”…",
                             "openKeyboardSettings:")
        hotkey_menu.addItem_(kb)
        self._add_submenu(menu, "Hotkey", hotkey_menu)
        self._refresh_hotkey_checkmarks()

        # Language picker
        lang_menu = NSMenu.alloc().init()
        self.lang_items = []
        for label, code in LANGUAGES:
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                label, "selectLanguage:", ""
            )
            item.setTarget_(self)
            item.setRepresentedObject_(code)
            lang_menu.addItem_(item)
            self.lang_items.append(item)
        self._add_submenu(menu, "Language", lang_menu)
        self._refresh_language_checkmarks()

        # Insert mode
        insert_menu = NSMenu.alloc().init()
        self.insert_items = []
        for label, mode in [("Paste (fast)", "paste"), ("Type (compatible)", "type")]:
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                label, "selectInsertMode:", ""
            )
            item.setTarget_(self)
            item.setRepresentedObject_(mode)
            insert_menu.addItem_(item)
            self.insert_items.append(item)
        self._add_submenu(menu, "Insert Mode", insert_menu)
        self._refresh_insert_checkmarks()

        menu.addItem_(NSMenuItem.separatorItem())
        self.launch_item = self._add_item(
            menu, "Launch at Login", "toggleLaunchAtLogin:"
        )
        self.sounds_item = self._add_item(menu, "Sounds", "toggleSounds:")
        self.space_item = self._add_item(menu, "Trailing Space", "toggleTrailingSpace:")
        self.commands_item = self._add_item(
            menu, "“New Line” Commands", "toggleSpokenCommands:"
        )
        self._refresh_toggles()

        menu.addItem_(NSMenuItem.separatorItem())
        self._add_item(menu, "Fix Permissions…", "fixPermissions:")
        self._add_item(menu, "About WhisperFlow", "showAbout:")
        quit_item = self._add_item(menu, "Quit WhisperFlow", "quitApp:")
        quit_item.setKeyEquivalent_("q")

        # Delegate goes on the history submenu so it rebuilds on open.
        self.history_menu.setDelegate_(self)
        self.status_item.setMenu_(menu)
        self._update_status_line()

    def _make_item(self, title, action):
        item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
            title, action, ""
        )
        item.setTarget_(self)
        return item

    def _add_item(self, menu, title, action):
        item = self._make_item(title, action)
        menu.addItem_(item)
        return item

    def _add_submenu(self, menu, title, submenu):
        item = self._add_item(menu, title, None)
        item.setSubmenu_(submenu)
        return item

    def _set_icon(self, symbol):
        button = self.status_item.button()
        image = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
            symbol, APP_NAME
        )
        if image is not None:
            button.setImage_(image)
        else:
            button.setTitle_("WF")

    def _update_status_line(self):
        if self._model_status:
            text = self._model_status
        elif self.state == RECORDING:
            text = "Listening…"
        elif self.state == TRANSCRIBING:
            text = "Transcribing…"
        elif not permissions.accessibility_trusted():
            text = "⚠ Grant Accessibility to enable the hotkey"
        elif self.config.get("hotkey") == "double_shift":
            text = "Ready — double-tap ⇧ to dictate, tap ⇧ to finish"
        else:
            label = HOTKEY_LABELS.get(self.config.get("hotkey"), "fn")
            text = f"Ready — hold {label} to dictate"
        self.status_line.setTitle_(text)

    # NSMenuDelegate — rebuild history each time the menu opens.
    def menuNeedsUpdate_(self, menu):
        if menu is not self.history_menu:
            return
        menu.removeAllItems()
        entries = history.recent(8)
        if not entries:
            empty = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                "No transcripts yet", None, ""
            )
            empty.setEnabled_(False)
            menu.addItem_(empty)
            return
        for entry in entries:
            text = entry["text"]
            title = text if len(text) <= 60 else text[:57] + "…"
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title, "copyHistoryItem:", ""
            )
            item.setTarget_(self)
            item.setRepresentedObject_(text)
            menu.addItem_(item)

    # ------------------------------------------------------- menu actions

    def selectModel_(self, sender):
        repo = sender.representedObject()
        if repo == self.config.get("model_repo") and self.transcriber.is_ready:
            return
        self.config.set("model_repo", repo)
        self._refresh_model_checkmarks()
        self._preload_model_async()

    def selectHotkey_(self, sender):
        self.config.set("hotkey", sender.representedObject())
        self._refresh_hotkey_checkmarks()
        self._update_status_line()

    def selectLanguage_(self, sender):
        self.config.set("language", sender.representedObject())
        self._refresh_language_checkmarks()

    def selectInsertMode_(self, sender):
        self.config.set("insert_mode", sender.representedObject())
        self._refresh_insert_checkmarks()

    def toggleLaunchAtLogin_(self, sender):
        try:
            if autostart.is_installed():
                autostart.uninstall()
                self.overlay.show_message("Launch at Login turned off", 1.6)
            else:
                autostart.install()
                self.overlay.show_message(
                    "Launch at Login is on — WhisperFlow starts automatically", 2.2
                )
        except Exception as exc:
            self.overlay.show_message("Couldn't change Launch at Login", 2.0)
            print(f"[whisperflow] autostart error: {exc}")
        self._refresh_toggles()

    def toggleSounds_(self, sender):
        self.config.set("sounds", not self.config.get("sounds"))
        self._refresh_toggles()

    def toggleTrailingSpace_(self, sender):
        self.config.set("trailing_space", not self.config.get("trailing_space"))
        self._refresh_toggles()

    def toggleSpokenCommands_(self, sender):
        self.config.set("spoken_commands", not self.config.get("spoken_commands"))
        self._refresh_toggles()

    def copyHistoryItem_(self, sender):
        pb = NSPasteboard.generalPasteboard()
        pb.clearContents()
        pb.setString_forType_(sender.representedObject(), NSPasteboardTypeString)

    def openKeyboardSettings_(self, sender):
        permissions.open_keyboard_settings()

    def fixPermissions_(self, sender):
        permissions.request_microphone()
        trusted = permissions.accessibility_trusted(prompt=True)
        if not trusted:
            permissions.open_accessibility_settings()
        if permissions.microphone_status() == "denied":
            permissions.open_microphone_settings()
        device = input_device_name()
        mic = permissions.microphone_status()
        self.overlay.show_message(
            f"Accessibility: {'✓' if trusted else '✗'}   "
            f"Mic: {'✓' if mic == 'authorized' else mic}   "
            f"Input: {device or 'none'}",
            3.0,
        )

    def showAbout_(self, sender):
        self.overlay.show_message(
            f"WhisperFlow v{__version__} — 100% on-device dictation", 2.5
        )

    def quitApp_(self, sender):
        self.hotkey.stop()
        self.recorder.cancel()
        NSApplication.sharedApplication().terminate_(self)

    # ----------------------------------------------------------- helpers

    def _refresh_model_checkmarks(self):
        current = self.config.get("model_repo")
        for item in self.model_items:
            item.setState_(1 if item.representedObject() == current else 0)

    def _refresh_hotkey_checkmarks(self):
        current = self.config.get("hotkey")
        for item in self.hotkey_items:
            item.setState_(1 if item.representedObject() == current else 0)

    def _refresh_language_checkmarks(self):
        current = self.config.get("language")
        for item in self.lang_items:
            item.setState_(1 if item.representedObject() == current else 0)

    def _refresh_insert_checkmarks(self):
        current = self.config.get("insert_mode")
        for item in self.insert_items:
            item.setState_(1 if item.representedObject() == current else 0)

    def _refresh_toggles(self):
        self.launch_item.setState_(1 if autostart.is_installed() else 0)
        self.sounds_item.setState_(1 if self.config.get("sounds") else 0)
        self.space_item.setState_(1 if self.config.get("trailing_space") else 0)
        self.commands_item.setState_(1 if self.config.get("spoken_commands") else 0)

    def _play_sound(self, name):
        if not self.config.get("sounds"):
            return
        try:
            sound = NSSound.soundNamed_(name)
            if sound is not None:
                sound.setVolume_(0.25)
                sound.play()
        except Exception:
            pass


_instance_lock_handle = None  # module-level so the lock lives for the process


def _acquire_single_instance_lock():
    """Return an open, exclusively-flocked file, or None if already running."""
    import fcntl
    from .config import CONFIG_DIR

    os.makedirs(CONFIG_DIR, exist_ok=True)
    handle = open(os.path.join(CONFIG_DIR, "whisperflow.lock"), "w")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        handle.close()
        return None
    return handle


def main():
    global _instance_lock_handle
    _instance_lock_handle = _acquire_single_instance_lock()
    if _instance_lock_handle is None:
        print(f"{APP_NAME} is already running — look for the waveform icon "
              "in your menu bar. (Quit it from there before relaunching.)")
        return

    app = NSApplication.sharedApplication()
    app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    controller = AppController.alloc().init()
    assert controller is not None
    print(f"{APP_NAME} v{__version__} running — look for the waveform icon "
          "in your menu bar.")
    AppHelper.runEventLoop()
