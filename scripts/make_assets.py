"""Generate WhisperFlow's app icon and README hero image with CoreGraphics.

Pure pyobjc (already a project dependency) — no Pillow/cairo needed.
Run inside the venv:  ./.venv/bin/python scripts/make_assets.py
Outputs:
  assets/icon-1024.png
  assets/AppIcon.icns
  docs/hero.png
"""

import math
import os
import subprocess

from AppKit import (
    NSBitmapImageFileTypePNG,
    NSBitmapImageRep,
    NSBezierPath,
    NSColor,
    NSDeviceRGBColorSpace,
    NSFont,
    NSFontAttributeName,
    NSForegroundColorAttributeName,
    NSGradient,
    NSGraphicsContext,
    NSMakeRect,
    NSMutableParagraphStyle,
    NSParagraphStyleAttributeName,
)
from Foundation import NSMakePoint, NSString

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "assets")
DOCS = os.path.join(ROOT, "docs")

# Brand gradient (indigo → violet) used across icon and hero.
TOP = NSColor.colorWithSRGBRed_green_blue_alpha_(0.36, 0.34, 0.96, 1.0)
BOTTOM = NSColor.colorWithSRGBRed_green_blue_alpha_(0.62, 0.33, 0.98, 1.0)

# Waveform bar heights (fraction of the available height), symmetric.
BARS = [0.30, 0.52, 0.76, 0.95, 0.76, 0.52, 0.30]


def _new_rep(w, h):
    rep = NSBitmapImageRep.alloc().initWithBitmapDataPlanes_pixelsWide_pixelsHigh_bitsPerSample_samplesPerPixel_hasAlpha_isPlanar_colorSpaceName_bytesPerRow_bitsPerPixel_(
        None, int(w), int(h), 8, 4, True, False, NSDeviceRGBColorSpace, 0, 0
    )
    return rep


def _begin(rep):
    ctx = NSGraphicsContext.graphicsContextWithBitmapImageRep_(rep)
    NSGraphicsContext.saveGraphicsState()
    NSGraphicsContext.setCurrentContext_(ctx)
    return ctx


def _end(rep, path):
    NSGraphicsContext.restoreGraphicsState()
    png = rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    png.writeToFile_atomically_(path, True)


def _waveform(cx, cy, span_w, span_h, bar_w, color, bars=BARS):
    color.setFill()
    n = len(bars)
    gap = (span_w - n * bar_w) / (n - 1)
    x = cx - span_w / 2.0
    for frac in bars:
        h = max(bar_w, span_h * frac)
        rect = NSMakeRect(x, cy - h / 2.0, bar_w, h)
        NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
            rect, bar_w / 2.0, bar_w / 2.0
        ).fill()
        x += bar_w + gap


def draw_icon(size):
    rep = _new_rep(size, size)
    _begin(rep)

    inset = size * 0.085
    rect = NSMakeRect(inset, inset, size - 2 * inset, size - 2 * inset)
    radius = (size - 2 * inset) * 0.225
    squircle = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        rect, radius, radius
    )
    NSGradient.alloc().initWithStartingColor_endingColor_(TOP, BOTTOM).drawInBezierPath_angle_(
        squircle, -90.0
    )

    inner = size - 2 * inset
    _waveform(
        cx=size / 2.0,
        cy=size / 2.0,
        span_w=inner * 0.56,
        span_h=inner * 0.52,
        bar_w=inner * 0.072,
        color=NSColor.whiteColor(),
    )
    _end(rep, os.path.join(ASSETS, f"_icon_{size}.png"))
    return os.path.join(ASSETS, f"_icon_{size}.png")


def build_icns():
    iconset = os.path.join(ASSETS, "AppIcon.iconset")
    os.makedirs(iconset, exist_ok=True)
    specs = [
        (16, "16x16"), (32, "16x16@2x"), (32, "32x32"), (64, "32x32@2x"),
        (128, "128x128"), (256, "128x128@2x"), (256, "256x256"),
        (512, "256x256@2x"), (512, "512x512"), (1024, "512x512@2x"),
    ]
    for px, name in specs:
        rep = _new_rep(px, px)
        _begin(rep)
        inset = px * 0.085
        rect = NSMakeRect(inset, inset, px - 2 * inset, px - 2 * inset)
        radius = (px - 2 * inset) * 0.225
        sq = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(rect, radius, radius)
        NSGradient.alloc().initWithStartingColor_endingColor_(TOP, BOTTOM).drawInBezierPath_angle_(sq, -90.0)
        inner = px - 2 * inset
        _waveform(px / 2.0, px / 2.0, inner * 0.56, inner * 0.52, inner * 0.072, NSColor.whiteColor())
        _end(rep, os.path.join(iconset, f"icon_{name}.png"))
    subprocess.run(
        ["iconutil", "-c", "icns", iconset, "-o", os.path.join(ASSETS, "AppIcon.icns")],
        check=True,
    )


def _text(s, x, y, size, color, weight=None, align_center_width=None):
    style = NSMutableParagraphStyle.alloc().init()
    if align_center_width is not None:
        style.setAlignment_(1)  # center
    font = (
        NSFont.systemFontOfSize_weight_(size, weight)
        if weight is not None
        else NSFont.systemFontOfSize_(size)
    )
    attrs = {
        NSFontAttributeName: font,
        NSForegroundColorAttributeName: color,
        NSParagraphStyleAttributeName: style,
    }
    ns = NSString.stringWithString_(s)
    if align_center_width is not None:
        ns.drawInRect_withAttributes_(
            NSMakeRect(x, y, align_center_width, size * 1.6), attrs
        )
    else:
        ns.drawAtPoint_withAttributes_(NSMakePoint(x, y), attrs)


def draw_hero():
    W, H = 1280, 640
    rep = _new_rep(W, H)
    _begin(rep)

    # Dark backdrop
    bg = NSBezierPath.bezierPathWithRect_(NSMakeRect(0, 0, W, H))
    NSGradient.alloc().initWithStartingColor_endingColor_(
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.10, 0.10, 0.14, 1.0),
        NSColor.colorWithSRGBRed_green_blue_alpha_(0.04, 0.04, 0.06, 1.0),
    ).drawInBezierPath_angle_(bg, -90.0)

    # The pill (matches the real on-screen HUD)
    pill_w, pill_h = 360, 76
    px = (W - pill_w) / 2.0
    py = H - 210
    pill = NSBezierPath.bezierPathWithRoundedRect_xRadius_yRadius_(
        NSMakeRect(px, py, pill_w, pill_h), pill_h / 2.0, pill_h / 2.0
    )
    NSColor.colorWithSRGBRed_green_blue_alpha_(0.10, 0.10, 0.11, 0.98).setFill()
    pill.fill()
    # Red record dot
    NSColor.systemRedColor().setFill()
    dot = 13
    NSBezierPath.bezierPathWithOvalInRect_(
        NSMakeRect(px + 34, py + pill_h / 2.0 - dot / 2.0, dot, dot)
    ).fill()
    # Waveform inside the pill
    _waveform(px + pill_w * 0.60, py + pill_h / 2.0, pill_w * 0.52, pill_h * 0.6,
              8.0, NSColor.whiteColor())

    # Title + tagline
    _text("WhisperFlow", 0, 250, 84,
          NSColor.whiteColor(), weight=0.4, align_center_width=W)
    _text("Local voice dictation for macOS", 0, 176, 30,
          NSColor.colorWithSRGBRed_green_blue_alpha_(0.85, 0.85, 0.92, 1.0),
          weight=0.0, align_center_width=W)
    _text("Double-tap Shift, speak, done — 100% on-device · open source · MIT",
          0, 120, 22,
          NSColor.colorWithSRGBRed_green_blue_alpha_(0.60, 0.60, 0.70, 1.0),
          align_center_width=W)

    _end(rep, os.path.join(DOCS, "hero.png"))


def main():
    os.makedirs(ASSETS, exist_ok=True)
    os.makedirs(DOCS, exist_ok=True)
    draw_icon(1024)
    os.replace(os.path.join(ASSETS, "_icon_1024.png"),
               os.path.join(ASSETS, "icon-1024.png"))
    build_icns()
    draw_hero()
    # Clean the intermediate iconset dir.
    subprocess.run(["rm", "-rf", os.path.join(ASSETS, "AppIcon.iconset")], check=False)
    print("assets written: assets/icon-1024.png, assets/AppIcon.icns, docs/hero.png")


if __name__ == "__main__":
    main()
