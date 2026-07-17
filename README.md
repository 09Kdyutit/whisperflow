# WhisperFlow 🎙️

**Voice dictation for macOS that runs 100% locally.** Double-tap Shift anywhere,
speak, tap Shift to finish — your words are transcribed on-device by Whisper
(Apple MLX) and typed straight into whatever app you're using.

No cloud. No subscription. No account. No audio ever leaves your Mac.

> A free, open-source, privacy-first take on apps like Wispr Flow — built for
> Apple Silicon.

![platform](https://img.shields.io/badge/platform-macOS%2013%2B-black)
![apple silicon](https://img.shields.io/badge/chip-Apple%20Silicon-black)
![python](https://img.shields.io/badge/python-3.11%E2%80%933.13-blue)
![license](https://img.shields.io/badge/license-MIT-green)

---

## Features

- **Fully on-device** — Whisper runs locally through Apple's MLX framework. Your
  voice never touches a network.
- **Works everywhere** — dictates into any app that accepts text: browsers,
  editors, chat, email, terminals.
- **Hands-free gesture** — double-tap Shift to start, tap Shift to finish. No
  key to hold down.
- **Live waveform HUD** — a small pill at the bottom of the screen shows it's
  listening, then transcribing.
- **Clipboard-safe** — paste-insertion restores your previous clipboard, even
  across rapid back-to-back dictations.
- **Spoken commands** — say "new line" / "new paragraph" for real line breaks.
- **Custom dictionary** — teach it names and jargon it keeps mishearing.
- **Launch at login** — one menu click; runs quietly in the menu bar forever.
- **Model choice** — from a 140 MB fast model up to full large-v3-turbo.

## Requirements

- A Mac with **Apple Silicon** (M1 or newer)
- **macOS 13** or later
- **Python 3.11–3.13** (`brew install python@3.12` if you don't have it)
- ~0.5 GB free disk for the app + one Whisper model
- Internet **once**, to download the model — fully offline after that

## Quick start

```bash
git clone https://github.com/09Kdyutit/whisperflow.git
cd whisperflow
./run.sh
```

First run does three one-time things:

1. Creates a Python virtualenv and installs dependencies (~1 min).
2. Downloads the default Whisper model (~440 MB).
3. Asks for two macOS permissions (below).

Then a **waveform icon** appears in your menu bar. Double-tap **Shift**, speak,
tap **Shift** once. Done.

## Permissions (one-time)

macOS attributes permissions to the app that launches WhisperFlow (Terminal,
iTerm, etc.):

| Permission | Where | Why |
|---|---|---|
| **Microphone** | System Settings › Privacy & Security › Microphone | to hear you |
| **Accessibility** | System Settings › Privacy & Security › Accessibility | global hotkey + typing text |

If the hotkey does nothing, open the menu-bar icon → **Fix Permissions…**, grant
Accessibility, and relaunch.

## Usage

| Gesture | Action |
|---|---|
| **Double-tap ⇧ Shift** | Start dictating (hands-free) |
| **Tap ⇧ once** while recording | Finish — text is typed into the active app |
| **Esc** while recording | Cancel |

Typing capital letters or shortcuts like ⌘⇧S never triggers dictation — only two
quick, clean Shift taps (nothing else pressed) start it.

Prefer hold-to-talk? Pick **fn**, **Right ⌥**, or **Right ⌘** in the Hotkey menu
(hold + speak + release). If you use **fn**, also set System Settings › Keyboard
› *"Press 🌐 key to"* → **Do Nothing**, or macOS pops the emoji picker.

## Menu-bar options

- **Model** — Turbo q4 (default, best speed/accuracy at 440 MB), Turbo HQ
  (1.5 GB), Small, Base. Switching downloads the new model once.
- **Hotkey** — Double-tap Shift (default), fn, Right ⌥, or Right ⌘.
- **Language** — auto-detect (default) or pin a language for speed and accuracy.
- **Insert Mode** — *Paste* (default, instant even for long text; restores your
  clipboard) or *Type* (synthesizes real keystrokes for apps that block paste).
- **Recent Transcripts** — click any entry to copy it again.
- **"New Line" Commands** — say "new line" / "new paragraph" to insert breaks.
- **Launch at Login** — start WhisperFlow automatically, forever.

## Custom dictionary

If Whisper mishears a name or term, add corrections to
`~/.whisperflow/config.json`:

```json
"replacements": { "cloud code": "Claude Code", "new york": "New York" }
```

## Troubleshooting

```bash
./run.sh --doctor                 # check permissions, mic, and model
./run.sh --transcribe test.wav    # test transcription without the GUI
```

- **Hotkey does nothing** → Accessibility isn't granted to your terminal app;
  grant it and relaunch.
- **"Didn't catch that"** → mic permission missing, or you spoke very quietly.
- **Transcribed but nothing typed** → try Insert Mode → *Type*. (Secure password
  fields block synthetic input by design.)
- **First dictation is slow** → the model warms up once per launch; later
  dictations are near-instant.

## How it works

```
double-tap ⇧  →  mic capture (16 kHz mono)  →  Whisper via MLX (on-device)
              →  text post-processing  →  pasted/typed into the focused app
```

- `hotkey.py` — global gesture detection via `NSEvent` monitors
- `audio.py` — microphone capture with `sounddevice`
- `transcribe.py` — Whisper inference through `mlx-whisper`
- `insert.py` — clipboard-safe paste / synthetic keystrokes via Quartz
- `overlay.py` — the floating waveform HUD (`NSPanel`)
- `app.py` — the menu-bar app that wires it all together

## Privacy

Audio is captured in memory, transcribed on your GPU via MLX, and discarded.
Transcripts are stored only in `~/.whisperflow/history.jsonl` on your disk. The
only network access ever is the one-time model download from Hugging Face.

## Contributing

Issues and pull requests are welcome. To hack on it:

```bash
./run.sh --doctor          # sanity-check your environment
python -m whisperflow      # run from your active virtualenv
```

## License

[MIT](LICENSE) — free to use, modify, and distribute.

## Acknowledgements

Built on [OpenAI Whisper](https://github.com/openai/whisper),
[Apple MLX](https://github.com/ml-explore/mlx), and
[mlx-whisper](https://github.com/ml-explore/mlx-examples).
