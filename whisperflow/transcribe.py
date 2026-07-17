"""On-device speech-to-text using Whisper via Apple MLX."""

import re
import threading

import numpy as np

MIN_DURATION_SEC = 0.25
MIN_RMS = 0.0015  # below this the clip is treated as silence

# Whisper hallucinates these on silence/noise-only clips. Kept deliberately
# narrow: only phrases a person almost never dictates as a whole utterance, so
# legitimate short dictations ("Thank you.", "Yes", "No") are NOT swallowed.
# "thank you" is intentionally excluded — it is far too common a real dictation.
# Entries are compared after stripping surrounding " .!?", so no trailing
# punctuation here.
_HALLUCINATIONS = {
    "thanks for watching",
    "thank you for watching",
    "please subscribe",
    "subscribe to my channel",
    "",
}


class Transcriber:
    def __init__(self, config):
        self.config = config
        self._load_lock = threading.Lock()
        self._loaded_repo = None

    @staticmethod
    def _model_path(repo):
        """Local snapshot path for `repo`, downloading it first if needed.

        mlx_whisper re-checks Hugging Face on every fresh model load unless
        it is given a local directory — which stalls (or fails) offline.
        Resolving the path ourselves keeps everything after the one-time
        download fully offline, and keys mlx_whisper's in-process model
        cache consistently by path.
        """
        from huggingface_hub import snapshot_download

        try:
            return snapshot_download(repo_id=repo, local_files_only=True)
        except Exception:
            return snapshot_download(repo_id=repo)  # one-time download

    def preload(self):
        """Download + load the model (first run downloads from Hugging Face)."""
        repo = self.config.get("model_repo")
        with self._load_lock:
            import mlx_whisper  # deferred: heavy import

            path = self._model_path(repo)
            # Transcribing a second of silence forces the weight load and
            # warms the compiled graph so the first real dictation is fast.
            silence = np.zeros(16000, dtype=np.float32)
            mlx_whisper.transcribe(silence, path_or_hf_repo=path, fp16=True)
            self._loaded_repo = repo

    @property
    def is_ready(self):
        return self._loaded_repo == self.config.get("model_repo")

    def transcribe(self, audio: np.ndarray) -> str:
        """Transcribe float32 mono 16 kHz audio. Returns cleaned text ('' if silence)."""
        duration = len(audio) / 16000.0
        if duration < MIN_DURATION_SEC:
            return ""
        rms = float(np.sqrt(np.mean(np.square(audio)))) if len(audio) else 0.0
        if rms < MIN_RMS:
            return ""

        import mlx_whisper

        # Pin to the model that is actually loaded. If the user switches models
        # mid-dictation, transcribe with the ready one rather than blocking on a
        # synchronous download of the newly-selected (not-yet-loaded) model.
        repo = self._loaded_repo or self.config.get("model_repo")
        language = self.config.get("language")
        with self._load_lock:
            result = mlx_whisper.transcribe(
                audio,
                path_or_hf_repo=self._model_path(repo),
                language=language,
                fp16=True,
                condition_on_previous_text=False,
            )

        text = (result.get("text") or "").strip()
        if text.lower().strip(" .!?") in _HALLUCINATIONS and duration < 2.5:
            return ""
        return self._post_process(text)

    def _post_process(self, text: str) -> str:
        if not text:
            return ""

        # Custom dictionary from config (case-insensitive). The replacement goes
        # through a lambda so backslashes and "\1" in user-supplied corrections
        # are inserted literally, not as regex references. Word boundaries are
        # applied only where the phrase edge is itself a word character, so keys
        # ending in punctuation ("c++", ".net") still match.
        replacements = self.config.get("replacements") or {}
        for heard, corrected in replacements.items():
            if not heard or not isinstance(corrected, str):
                continue
            left = r"(?<!\w)" if heard[:1].isalnum() or heard[:1] == "_" else ""
            right = r"(?!\w)" if heard[-1:].isalnum() or heard[-1:] == "_" else ""
            text = re.sub(
                left + re.escape(heard) + right,
                lambda _m, c=corrected: c,
                text,
                flags=re.IGNORECASE,
            )

        # Spoken commands: "new line" / "new paragraph" become real newlines.
        # A comma before the command is consumed; a sentence-ending period
        # is kept ("…everything. New paragraph. Best" → "…everything.\n\nBest").
        if self.config.get("spoken_commands"):
            text = re.sub(
                r",?\s*\bnew paragraph\b[,.]?\s*", "\n\n", text,
                flags=re.IGNORECASE,
            )
            text = re.sub(
                r",?\s*\bnew line\b[,.]?\s*", "\n", text,
                flags=re.IGNORECASE,
            )
            # Re-capitalize after inserted breaks.
            text = re.sub(
                r"\n([a-z])", lambda m: "\n" + m.group(1).upper(), text
            )

        # Trim surrounding spaces/tabs but preserve newlines produced by spoken
        # commands, so dictating "new line" (or a trailing "new paragraph")
        # still emits the break instead of being stripped to nothing.
        return text.strip(" \t")
