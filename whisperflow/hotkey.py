"""Global hotkey monitoring via NSEvent monitors (needs Accessibility trust).

For hold-style hotkeys (fn / right option / right command) this reports raw
press/release/escape events; the app layer owns the semantics (hold-to-talk,
double-tap lock, cancel).

The "double_shift" hotkey is gesture-based instead: shift is far too common
in normal typing to treat as a hold key, so this module detects clean shift
*taps* — a quick press+release with no other key or modifier involved — and
reports them as on_tap / on_double_tap. A shift press that types a capital
letter, participates in a shortcut chord, or is held too long never counts.
"""

import time

from AppKit import (
    NSEvent,
    NSEventMaskFlagsChanged,
    NSEventMaskKeyDown,
    NSEventModifierFlagCommand,
    NSEventModifierFlagControl,
    NSEventModifierFlagFunction,
    NSEventModifierFlagOption,
    NSEventTypeFlagsChanged,
    NSEventTypeKeyDown,
)

KEYCODE_FN = 63
KEYCODE_RIGHT_OPTION = 61
KEYCODE_RIGHT_COMMAND = 54
KEYCODE_ESCAPE = 53

_HOTKEY_SPECS = {
    "fn": (KEYCODE_FN, NSEventModifierFlagFunction),
    "right_option": (KEYCODE_RIGHT_OPTION, NSEventModifierFlagOption),
    "right_command": (KEYCODE_RIGHT_COMMAND, NSEventModifierFlagCommand),
}

# Same table indexed by keycode, for matching the release of a held key.
_KEYCODE_SPECS = {
    keycode: (name, flag) for name, (keycode, flag) in _HOTKEY_SPECS.items()
}

# Whether a given physical shift key is down comes from the device-dependent
# modifier bits (NX_DEVICELSHIFTKEYMASK / NX_DEVICERSHIFTKEYMASK), which
# disambiguates press vs release even when both shifts are involved.
_DEVICE_SHIFT_BITS = {56: 0x0002, 60: 0x0004}  # left shift, right shift

# Same idea for the hold-style hotkeys. The generic option/command flag stays
# set while the *sibling* key on the other side is held, so a right-⌥ hotkey
# would never see its release if left ⌥ was also down. The per-key device bits
# below track the specific physical key instead. (fn has no device bit, so it
# falls back to the generic function flag — fn has no sibling, so that's fine.)
_DEVICE_KEY_BITS = {
    61: 0x40,  # right option  NX_DEVICERALTKEYMASK
    58: 0x20,  # left option   NX_DEVICELALTKEYMASK
    54: 0x10,  # right command NX_DEVICERCMDKEYMASK
    55: 0x08,  # left command  NX_DEVICELCMDKEYMASK
}


def _key_is_down(event, keycode, generic_flag):
    """True if the specific hotkey `keycode` is currently pressed."""
    bit = _DEVICE_KEY_BITS.get(keycode)
    if bit is not None:
        return bool(event.modifierFlags() & bit)
    return bool(event.modifierFlags() & generic_flag)


_OTHER_MODIFIERS = (
    NSEventModifierFlagCommand
    | NSEventModifierFlagControl
    | NSEventModifierFlagOption
    | NSEventModifierFlagFunction
)

SHIFT_TAP_MAX_HOLD = 0.40      # held longer = typing capitals, not a tap
SHIFT_DOUBLE_TAP_WINDOW = 0.45  # two clean taps within this = the gesture


class HotkeyMonitor:
    """Watches for the configured hotkey. NSEvent monitors added from the
    main thread deliver on the main thread, so callbacks are main-thread."""

    def __init__(self, config, on_press, on_release, on_escape,
                 on_tap=None, on_double_tap=None, on_shift_press=None):
        self.config = config
        self.on_press = on_press
        self.on_release = on_release
        self.on_escape = on_escape
        self.on_tap = on_tap or (lambda: None)
        self.on_double_tap = on_double_tap or (lambda: None)
        # Fired the moment a clean Shift goes down (nothing else held). The app
        # uses it to stop an active hands-free recording instantly, so stopping
        # never depends on the press being a perfectly-timed quick tap.
        self.on_shift_press = on_shift_press or (lambda: None)
        # Keycode of the currently-held hotkey (None when not held). Tracking
        # the keycode rather than a boolean means a release still matches even
        # if the user switches hotkeys in the menu while holding the old one.
        self._pressed_keycode = None
        # Shift-gesture state: (keycode, press time) of the shift currently
        # down, whether that press has been disqualified, and when the last
        # clean tap finished.
        self._shift_down = None
        self._shift_dirty = False
        self._last_shift_tap = 0.0
        self._monitors = []

    def start(self):
        mask = NSEventMaskFlagsChanged | NSEventMaskKeyDown

        monitor = NSEvent.addGlobalMonitorForEventsMatchingMask_handler_(
            mask, self._handle_event
        )
        if monitor is not None:
            self._monitors.append(monitor)

        def local_handler(event):
            self._handle_event(event)
            return event  # never swallow events aimed at our own windows

        monitor = NSEvent.addLocalMonitorForEventsMatchingMask_handler_(
            mask, local_handler
        )
        if monitor is not None:
            self._monitors.append(monitor)

    def stop(self):
        for monitor in self._monitors:
            try:
                NSEvent.removeMonitor_(monitor)
            except Exception:
                pass
        self._monitors = []

    # ------------------------------------------------------------------

    def _handle_event(self, event):
        try:
            etype = event.type()

            if etype == NSEventTypeKeyDown:
                if event.keyCode() == KEYCODE_ESCAPE:
                    self.on_escape()
                # A real keystroke means any shift involved is typing a
                # capital letter — disqualify the current and pending taps.
                self._shift_dirty = True
                self._last_shift_tap = 0.0
                return

            if etype != NSEventTypeFlagsChanged:
                return

            if self.config.get("hotkey") == "double_shift":
                self._handle_shift_flags(event)
                return

            keycode = event.keyCode()

            if self._pressed_keycode is not None:
                # A hotkey is held: only its own release matters.
                if keycode != self._pressed_keycode:
                    return
                _, flag = _KEYCODE_SPECS[keycode]
                if not _key_is_down(event, keycode, flag):
                    self._pressed_keycode = None
                    self.on_release()
                return

            want_keycode, want_flag = _HOTKEY_SPECS.get(
                self.config.get("hotkey"), _HOTKEY_SPECS["fn"]
            )
            if keycode == want_keycode and _key_is_down(event, keycode, want_flag):
                self._pressed_keycode = keycode
                self.on_press()
        except Exception:
            # A crash inside an event monitor handler kills the run loop;
            # swallow anything unexpected.
            pass

    def _handle_shift_flags(self, event):
        keycode = event.keyCode()
        bit = _DEVICE_SHIFT_BITS.get(keycode)
        if bit is None:
            # Some other modifier moved: shift is part of a shortcut chord
            # (⌘⇧S and friends), not the dictation gesture.
            self._shift_dirty = True
            self._last_shift_tap = 0.0
            return

        now = time.monotonic()
        flags = event.modifierFlags()

        if flags & bit:  # this shift key went down
            if self._shift_down is not None:  # both shifts at once
                self._shift_dirty = True
                return
            self._shift_down = (keycode, now)
            other = bool(flags & _OTHER_MODIFIERS)
            self._shift_dirty = other
            # A clean Shift press (no chord) is the stop gesture. Signal it on
            # key-DOWN so stopping is instant and immune to how long it's held
            # or to a missed key-up event.
            if not other:
                self.on_shift_press()
            return

        # This shift key went up.
        down = self._shift_down
        self._shift_down = None
        if down is None or down[0] != keycode:
            return
        dirty = self._shift_dirty
        self._shift_dirty = False
        if dirty or (now - down[1]) > SHIFT_TAP_MAX_HOLD:
            self._last_shift_tap = 0.0
            return
        if now - self._last_shift_tap <= SHIFT_DOUBLE_TAP_WINDOW:
            self._last_shift_tap = 0.0
            self.on_double_tap()
        else:
            self._last_shift_tap = now
            self.on_tap()
