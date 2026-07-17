# WhisperFlow — project description

Reusable blurbs for applications, résumés, and portfolios.

## One-liner

WhisperFlow is a free, open-source macOS app that turns speech into text
entirely on-device — double-tap Shift, speak, and your words are typed into any
app, with no cloud, account, or subscription.

## Short (activities list / résumé bullet)

Built and open-sourced WhisperFlow, a macOS voice-dictation app that runs
OpenAI's Whisper model 100% on-device via Apple's MLX framework. Designed a
global hotkey gesture, a real-time audio pipeline, and clipboard-safe text
insertion, then packaged it as a background menu-bar app that auto-starts at
login. Released under the MIT license for anyone to use for free.

## Paragraph (essay / personal statement)

I created WhisperFlow because I wanted the convenience of paid dictation tools
without sending my voice to someone else's servers. It's a macOS app that lets
you dictate into any program — you double-tap the Shift key, speak, and tap
Shift again, and your words are transcribed and typed wherever your cursor is.
The key idea is that everything runs locally: I run OpenAI's Whisper speech model
directly on the Mac's GPU through Apple's MLX framework, so no audio ever leaves
the machine. Building it meant solving real engineering problems — capturing the
microphone in real time, detecting a global keyboard gesture without interfering
with normal typing, safely pasting text while preserving whatever was already on
the clipboard, and packaging it all as a background app that starts automatically
and survives crashes. I open-sourced it under the MIT license so anyone can use
it, study how it works, or build on it for free.

## Technical highlights

- **On-device ML:** OpenAI Whisper (large-v3-turbo) via Apple MLX — private,
  offline after a one-time model download.
- **Systems programming:** global input monitoring, real-time audio capture, and
  synthetic keyboard/clipboard events through macOS's Cocoa/Quartz APIs (PyObjC).
- **Robustness:** single-instance locking, clipboard restoration across rapid
  dictations, graceful handling of missing permissions, and a launchd service
  for auto-start and crash recovery.
- **Language & stack:** Python, PyObjC (AppKit/Quartz/AVFoundation), mlx-whisper.
- **Distribution:** MIT-licensed, one-command install, menu-bar UI.

## Links

- Source: https://github.com/09Kdyutit/whisperflow
