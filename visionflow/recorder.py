"""Captura de áudio do microfone usando sounddevice."""

from __future__ import annotations

import io
import threading
import wave

import numpy as np
import sounddevice as sd

from visionflow.config import AudioConfig


class AudioRecorder:
    """Grava áudio do microfone em memória (WAV 16-bit PCM)."""

    def __init__(self, config: AudioConfig | None = None) -> None:
        cfg = config or AudioConfig()
        self.sample_rate = cfg.sample_rate
        self.channels = cfg.channels
        self._frames: list[np.ndarray] = []
        self._stream: sd.InputStream | None = None
        self._recording = False
        self._lock = threading.Lock()

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        """Inicia a gravação."""
        with self._lock:
            if self._recording:
                return
            self._frames.clear()
            self._recording = True

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="int16",
            blocksize=1024,
            callback=self._audio_callback,
        )
        self._stream.start()

    def stop(self) -> bytes:
        """Para a gravação e retorna os bytes WAV."""
        with self._lock:
            self._recording = False

        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None

        return self._build_wav()

    def _audio_callback(
        self, indata: np.ndarray, frames: int, time_info: object, status: sd.CallbackFlags
    ) -> None:
        if self._recording:
            self._frames.append(indata.copy())

    def _build_wav(self) -> bytes:
        """Combina frames gravados em um arquivo WAV em memória."""
        if not self._frames:
            return b""

        audio_data = np.concatenate(self._frames, axis=0)
        buf = io.BytesIO()

        with wave.open(buf, "wb") as wf:
            wf.setnchannels(self.channels)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(audio_data.tobytes())

        return buf.getvalue()
