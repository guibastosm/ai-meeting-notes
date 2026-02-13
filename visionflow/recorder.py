"""Captura de áudio do microfone usando sounddevice (+monitor via parecord)."""

from __future__ import annotations

import io
import signal
import subprocess
import tempfile
import threading
import wave
from pathlib import Path

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


class DualRecorder:
    """Grava mic (sounddevice) + monitor/headset (parecord) simultaneamente."""

    def __init__(self, config: AudioConfig | None = None) -> None:
        cfg = config or AudioConfig()
        self._mic_recorder = AudioRecorder(cfg)
        self._sample_rate = cfg.sample_rate
        self._monitor_proc: subprocess.Popen | None = None
        self._monitor_tmpfile: str = ""
        self._recording = False

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self, monitor_source: str = "") -> None:
        """Inicia gravação dual: mic via sounddevice, monitor via parecord."""
        if self._recording:
            return

        # Detecta monitor source se não especificado
        if not monitor_source:
            from visionflow.meeting import detect_sources
            sources = detect_sources()
            monitor_source = sources.get("monitor", "")

        # Inicia mic
        self._mic_recorder.start()

        # Inicia monitor (parecord) se disponível
        if monitor_source:
            self._monitor_tmpfile = tempfile.mktemp(suffix=".wav", prefix="vf_monitor_")
            try:
                self._monitor_proc = subprocess.Popen(
                    [
                        "parecord",
                        "--device", monitor_source,
                        "--file-format=wav",
                        self._monitor_tmpfile,
                    ],
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.PIPE,
                )
                print(f"[visionflow] Monitor source: {monitor_source}")
            except Exception as e:
                print(f"[visionflow] AVISO: falha ao iniciar parecord: {e}")
                self._monitor_proc = None
        else:
            print("[visionflow] AVISO: nenhum monitor source detectado, capturando só mic")

        self._recording = True

    def stop(self) -> tuple[bytes, bytes]:
        """Para gravação e retorna (mic_wav_bytes, monitor_wav_bytes)."""
        if not self._recording:
            return b"", b""

        self._recording = False

        # Para mic
        mic_bytes = self._mic_recorder.stop()

        # Para monitor
        monitor_bytes = b""
        if self._monitor_proc and self._monitor_proc.poll() is None:
            try:
                self._monitor_proc.send_signal(signal.SIGINT)
                self._monitor_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._monitor_proc.terminate()
                try:
                    self._monitor_proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    self._monitor_proc.kill()
            except Exception as e:
                print(f"[visionflow] AVISO: erro ao parar monitor: {e}")

        self._monitor_proc = None

        # Lê e normaliza o WAV do monitor para mono 16kHz
        if self._monitor_tmpfile:
            monitor_path = Path(self._monitor_tmpfile)
            if monitor_path.exists() and monitor_path.stat().st_size > 100:
                monitor_bytes = self._read_and_normalize(monitor_path)
                print(f"[visionflow] Monitor: {len(monitor_bytes)} bytes")
            monitor_path.unlink(missing_ok=True)
            self._monitor_tmpfile = ""

        return mic_bytes, monitor_bytes

    def _read_and_normalize(self, path: Path) -> bytes:
        """Lê WAV do parecord, converte para mono 16kHz e retorna WAV bytes."""
        try:
            with wave.open(str(path), "rb") as wf:
                n_channels = wf.getnchannels()
                sample_rate = wf.getframerate()
                sample_width = wf.getsampwidth()
                n_frames = wf.getnframes()
                raw = wf.readframes(n_frames)

            # Converte para int16
            if sample_width == 4:
                data = np.frombuffer(raw, dtype=np.int32)
                data = (data >> 16).astype(np.int16)
            elif sample_width == 2:
                data = np.frombuffer(raw, dtype=np.int16)
            else:
                return b""

            # Mono
            if n_channels > 1:
                data = data.reshape(-1, n_channels).mean(axis=1).astype(np.int16)

            # Resample para 16kHz
            if sample_rate != self._sample_rate:
                duration = len(data) / sample_rate
                target_len = int(duration * self._sample_rate)
                indices = np.linspace(0, len(data) - 1, target_len)
                data = np.interp(indices, np.arange(len(data)), data.astype(np.float64)).astype(np.int16)

            # Exporta como WAV em memória
            buf = io.BytesIO()
            with wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self._sample_rate)
                wf.writeframes(data.tobytes())
            return buf.getvalue()

        except Exception as e:
            print(f"[visionflow] AVISO: erro ao normalizar monitor WAV: {e}")
            return b""
