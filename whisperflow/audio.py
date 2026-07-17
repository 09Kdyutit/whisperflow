"""Microphone capture at 16 kHz mono float32 (what Whisper expects)."""

import math
import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000


class Recorder:
    """Push-to-talk recorder. start() opens the mic, stop() returns audio.

    The macOS mic-in-use indicator only lights while a stream is open,
    so the stream is opened on demand rather than kept hot.
    """

    def __init__(self):
        self._stream = None
        self._chunks = []
        self._lock = threading.Lock()
        self._level = 0.0  # smoothed RMS in 0..1, read by the overlay

    @property
    def level(self):
        return self._level

    @property
    def is_recording(self):
        return self._stream is not None

    def start(self):
        if self._stream is not None:
            return
        with self._lock:
            self._chunks = []
        self._level = 0.0

        def callback(indata, frames, time_info, status):
            data = indata[:, 0].copy()
            with self._lock:
                self._chunks.append(data)
            rms = float(np.sqrt(np.mean(np.square(data)))) if len(data) else 0.0
            # Map typical speech RMS (~0.003..0.15) onto 0..1 with a log curve.
            loud = max(0.0, min(1.0, (math.log10(max(rms, 1e-5)) + 5.0) / 4.0))
            self._level = 0.6 * self._level + 0.4 * loud

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=1024,
            callback=callback,
        )
        stream.start()
        self._stream = stream

    def stop(self):
        """Stop recording and return the captured audio as float32 mono."""
        stream = self._stream
        self._stream = None
        self._level = 0.0
        if stream is not None:
            try:
                stream.stop()
                stream.close()
            except Exception:
                pass
        with self._lock:
            chunks, self._chunks = self._chunks, []
        if not chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(chunks)

    def cancel(self):
        self.stop()


def input_device_name():
    """Name of the default input device, or None if there is none."""
    try:
        info = sd.query_devices(kind="input")
        return info.get("name")
    except Exception:
        return None
