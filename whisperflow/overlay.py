"""Floating pill HUD at the bottom of the screen (Wispr-Flow style).

Shows an animated waveform while listening, a pulse while transcribing,
and short text hints. All methods must be called on the main thread.
"""

import math
import time
from collections import deque

import objc
from AppKit import (
    NSBackingStoreBuffered,
    NSBezierPath,
    NSColor,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSMakeRect,
    NSPanel,
    NSScreen,
    NSView,
    NSWindowCollectionBehaviorCanJoinAllSpaces,
    NSWindowCollectionBehaviorFullScreenAuxiliary,
    NSWindowCollectionBehaviorStationary,
    NSWindowStyleMaskBorderless,
    NSWindowStyleMaskNonactivatingPanel,
)
from Foundation import NSString, NSTimer

PILL_WIDTH = 240.0
PILL_HEIGHT = 44.0
BOTTOM_MARGIN = 28.0
NUM_BARS = 24

MODE_HIDDEN = "hidden"
MODE_LISTENING = "listening"
MODE_TRANSCRIBING = "transcribing"
MODE_MESSAGE = "message"


class PillView(NSView):
    def initWithFrame_(self, frame):
        self = objc.super(PillView, self).initWithFrame_(frame)
        if self is None:
            return None
        self.mode = MODE_HIDDEN
        self.locked = False
        self.message = ""
        self.levels = deque([0.0] * NUM_BARS, maxlen=NUM_BARS)
        self.phase = 0.0
        return self

    def isFlipped(self):
        return False

    def drawRect_(self, rect):
        bounds = self.bounds()

        # Pill background
        path = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            bounds, PILL_HEIGHT / 2.0, PILL_HEIGHT / 2.0
        )
        NSColor.colorWithCalibratedWhite_alpha_(0.08, 0.92).setFill()
        path.fill()

        if self.mode == MODE_LISTENING:
            self._draw_waveform(bounds)
        elif self.mode == MODE_TRANSCRIBING:
            self._draw_pulse_dots(bounds)
        elif self.mode == MODE_MESSAGE:
            self._draw_message(bounds)

    def _draw_waveform(self, bounds):
        # Red recording dot on the left
        dot_size = 8.0
        dot_x = 22.0
        dot_rect = NSMakeRect(
            dot_x, bounds.size.height / 2.0 - dot_size / 2.0, dot_size, dot_size
        )
        color = (
            NSColor.systemOrangeColor() if self.locked
            else NSColor.systemRedColor()
        )
        color.setFill()
        NSBezierPath.bezierPathWithOvalInRect_(dot_rect).fill()

        # Waveform bars
        left = dot_x + dot_size + 14.0
        right = bounds.size.width - 24.0
        span = right - left
        bar_w = 3.0
        gap = (span - NUM_BARS * bar_w) / max(NUM_BARS - 1, 1)
        mid_y = bounds.size.height / 2.0
        levels = list(self.levels)

        NSColor.whiteColor().setFill()
        for i, level in enumerate(levels):
            wobble = 0.15 * math.sin(self.phase + i * 0.9)
            h = 3.0 + (bounds.size.height - 18.0) * max(
                0.0, min(1.0, level + wobble * level)
            )
            x = left + i * (bar_w + gap)
            bar = NSMakeRect(x, mid_y - h / 2.0, bar_w, h)
            NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
                bar, bar_w / 2.0, bar_w / 2.0
            ).fill()

    def _draw_pulse_dots(self, bounds):
        n = 3
        dot = 7.0
        gap = 12.0
        total = n * dot + (n - 1) * gap
        x0 = (bounds.size.width - total) / 2.0
        mid_y = bounds.size.height / 2.0
        for i in range(n):
            t = (math.sin(self.phase * 2.0 - i * 0.9) + 1.0) / 2.0
            alpha = 0.25 + 0.75 * t
            NSColor.colorWithCalibratedWhite_alpha_(1.0, alpha).setFill()
            rect = NSMakeRect(
                x0 + i * (dot + gap), mid_y - dot / 2.0, dot, dot
            )
            NSBezierPath.bezierPathWithOvalInRect_(rect).fill()

    def _draw_message(self, bounds):
        text = NSString.stringWithString_(self.message or "")
        attrs = {
            NSFontAttributeName: NSFont.systemFontOfSize_(13.0),
            NSForegroundColorAttributeName:
                NSColor.colorWithCalibratedWhite_alpha_(1.0, 0.95),
        }
        size = text.sizeWithAttributes_(attrs)
        point = (
            max((bounds.size.width - size.width) / 2.0, 10.0),
            (bounds.size.height - size.height) / 2.0,
        )
        text.drawAtPoint_withAttributes_(point, attrs)


class Overlay:
    """Owns the NSPanel + animation timer. Main-thread only."""

    def __init__(self):
        rect = NSMakeRect(0, 0, PILL_WIDTH, PILL_HEIGHT)
        panel = NSPanel.alloc().initWithContentRect_styleMask_backing_defer_(
            rect,
            NSWindowStyleMaskBorderless | NSWindowStyleMaskNonactivatingPanel,
            NSBackingStoreBuffered,
            False,
        )
        panel.setOpaque_(False)
        panel.setBackgroundColor_(NSColor.clearColor())
        panel.setHasShadow_(True)
        panel.setIgnoresMouseEvents_(True)
        panel.setLevel_(25)  # NSStatusWindowLevel
        panel.setCollectionBehavior_(
            NSWindowCollectionBehaviorCanJoinAllSpaces
            | NSWindowCollectionBehaviorFullScreenAuxiliary
            | NSWindowCollectionBehaviorStationary
        )
        panel.setHidesOnDeactivate_(False)

        self.view = PillView.alloc().initWithFrame_(rect)
        panel.setContentView_(self.view)
        self.panel = panel

        self._timer = None
        self._level_source = None
        self._hide_at = None
        self._width = PILL_WIDTH

    # ------------------------------------------------------------- public

    def show_listening(self, level_source, locked=False):
        self.view.mode = MODE_LISTENING
        self.view.locked = locked
        self.view.levels.clear()
        self.view.levels.extend([0.0] * NUM_BARS)
        self._level_source = level_source
        self._hide_at = None
        self._width = PILL_WIDTH
        self._present()

    def set_locked(self, locked):
        self.view.locked = locked
        self.view.setNeedsDisplay_(True)

    def show_transcribing(self):
        self.view.mode = MODE_TRANSCRIBING
        self._level_source = None
        self._hide_at = None
        self._width = PILL_WIDTH
        self._present()

    def show_message(self, text, duration=1.6):
        self.view.mode = MODE_MESSAGE
        self.view.message = text
        self._level_source = None
        self._hide_at = time.monotonic() + duration
        ns = NSString.stringWithString_(text)
        attrs = {NSFontAttributeName: NSFont.systemFontOfSize_(13.0)}
        needed = ns.sizeWithAttributes_(attrs).width + 48.0
        self._width = max(PILL_WIDTH, min(needed, 600.0))
        self._present()

    def hide(self):
        self.view.mode = MODE_HIDDEN
        self._level_source = None
        self._hide_at = None
        self._stop_timer()
        self.panel.orderOut_(None)

    # ------------------------------------------------------------ internal

    def _present(self):
        self._position()
        self.view.setNeedsDisplay_(True)
        self.panel.orderFrontRegardless()
        self._start_timer()

    def _position(self):
        screen = NSScreen.mainScreen()
        if screen is None:
            screens = NSScreen.screens()
            if not screens:
                return
            screen = screens[0]
        vis = screen.visibleFrame()
        x = vis.origin.x + (vis.size.width - self._width) / 2.0
        y = vis.origin.y + BOTTOM_MARGIN
        self.panel.setFrame_display_(
            NSMakeRect(x, y, self._width, PILL_HEIGHT), True
        )

    def _start_timer(self):
        if self._timer is not None:
            return
        self._timer = (
            NSTimer.scheduledTimerWithTimeInterval_repeats_block_(
                1.0 / 30.0, True, self._tick
            )
        )

    def _stop_timer(self):
        if self._timer is not None:
            self._timer.invalidate()
            self._timer = None

    def _tick(self, _timer):
        self.view.phase += 0.25
        if self._level_source is not None:
            try:
                self.view.levels.append(float(self._level_source()))
            except Exception:
                self.view.levels.append(0.0)
        if self._hide_at is not None and time.monotonic() >= self._hide_at:
            self.hide()
            return
        self.view.setNeedsDisplay_(True)
