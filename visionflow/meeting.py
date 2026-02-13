"""Gravação de reuniões com captura dual (mic + monitor) via PipeWire."""

from __future__ import annotations

import signal
import subprocess
import time
import wave
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from visionflow.config import MeetingConfig


@dataclass
class MeetingFiles:
    """Paths dos arquivos gerados por uma gravação de reunião."""
    output_dir: Path
    mic_wav: Path
    system_wav: Path
    combined_wav: Path
    started_at: datetime
    duration_seconds: float


def detect_sources() -> dict[str, str]:
    """Detecta automaticamente mic e monitor sources via pactl.

    Prioriza dispositivos USB (headsets) sobre HDMI/built-in.
    """
    sources: dict[str, str] = {"mic": "", "monitor": ""}

    try:
        result = subprocess.run(
            ["pactl", "list", "short", "sources"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            return sources

        monitors: list[str] = []
        mics: list[str] = []

        for line in result.stdout.strip().splitlines():
            parts = line.split("\t")
            if len(parts) < 2:
                continue
            name = parts[1]

            if name.endswith(".monitor"):
                monitors.append(name)
            elif "input" in name and not name.endswith(".monitor"):
                mics.append(name)

        # Prioriza USB (headsets) sobre HDMI/PCI (built-in/placa de video)
        def _is_usb(name: str) -> bool:
            return ".usb-" in name or ".usb_" in name

        # Monitor: prefere USB, senão pega o primeiro
        usb_monitors = [m for m in monitors if _is_usb(m)]
        sources["monitor"] = usb_monitors[0] if usb_monitors else (monitors[0] if monitors else "")

        # Mic: prefere USB, senão pega o primeiro
        usb_mics = [m for m in mics if _is_usb(m)]
        sources["mic"] = usb_mics[0] if usb_mics else (mics[0] if mics else "")

        if monitors:
            print(f"[visionflow] Monitors disponíveis: {monitors}")
            print(f"[visionflow] Monitor selecionado: {sources['monitor']}")
        if mics:
            print(f"[visionflow] Mics disponíveis: {mics}")
            print(f"[visionflow] Mic selecionado: {sources['mic']}")

    except Exception as e:
        print(f"[visionflow] AVISO: falha ao detectar sources: {e}")

    return sources


class MeetingRecorder:
    """Grava reunião capturando mic + monitor via pw-record (PipeWire)."""

    def __init__(self, config: MeetingConfig | None = None) -> None:
        from visionflow.config import MeetingConfig as MC

        cfg = config or MC()
        self._output_base = Path(cfg.output_dir).expanduser()
        self._sample_rate = cfg.sample_rate
        self._mic_source = cfg.mic_source
        self._monitor_source = cfg.monitor_source

        self._mic_proc: subprocess.Popen | None = None
        self._monitor_proc: subprocess.Popen | None = None
        self._output_dir: Path | None = None
        self._mic_path: Path | None = None
        self._monitor_path: Path | None = None
        self._started_at: datetime | None = None
        self._recording = False

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> Path:
        """Inicia gravação dual. Retorna o diretório de saída."""
        if self._recording:
            raise RuntimeError("Já está gravando")

        # Resolve sources
        mic_src = self._mic_source
        monitor_src = self._monitor_source

        if mic_src == "auto" or monitor_src == "auto":
            detected = detect_sources()
            if mic_src == "auto":
                mic_src = detected["mic"]
            if monitor_src == "auto":
                monitor_src = detected["monitor"]

        if not mic_src:
            raise RuntimeError(
                "Nenhum microfone detectado. Configure 'mic_source' no config.yaml"
            )
        if not monitor_src:
            raise RuntimeError(
                "Nenhum monitor source detectado. Configure 'monitor_source' no config.yaml"
            )

        print(f"[visionflow] Mic source:     {mic_src}")
        print(f"[visionflow] Monitor source: {monitor_src}")

        # Cria diretório de saída
        self._started_at = datetime.now()
        ts = self._started_at.strftime("%Y-%m-%d_%H-%M")
        self._output_dir = self._output_base / ts
        self._output_dir.mkdir(parents=True, exist_ok=True)

        self._mic_path = self._output_dir / "mic.wav"
        self._monitor_path = self._output_dir / "system.wav"

        # Inicia pw-record para mic (sample rate nativa, converte depois)
        self._mic_proc = subprocess.Popen(
            [
                "pw-record",
                "--target", mic_src,
                str(self._mic_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        # Inicia parecord para monitor (pw-record --target não conecta a monitors)
        self._monitor_proc = subprocess.Popen(
            [
                "parecord",
                "--device", monitor_src,
                "--file-format=wav",
                str(self._monitor_path),
            ],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        self._recording = True
        print(f"[visionflow] Gravando reunião em: {self._output_dir}")
        return self._output_dir

    def stop(self) -> MeetingFiles | None:
        """Para gravação e retorna os arquivos gerados."""
        if not self._recording:
            return None

        self._recording = False
        duration = (datetime.now() - self._started_at).total_seconds() if self._started_at else 0

        # Para os processos pw-record com SIGINT (para fechar o WAV corretamente)
        for name, proc in [("mic", self._mic_proc), ("monitor", self._monitor_proc)]:
            if proc and proc.poll() is None:
                try:
                    proc.send_signal(signal.SIGINT)
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.terminate()
                    try:
                        proc.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                except Exception as e:
                    print(f"[visionflow] AVISO: erro ao parar {name}: {e}")

        self._mic_proc = None
        self._monitor_proc = None

        # Verifica se os arquivos existem e tem conteúdo
        if not self._mic_path or not self._monitor_path:
            return None

        for p in [self._mic_path, self._monitor_path]:
            if not p.exists():
                print(f"[visionflow] AVISO: arquivo não encontrado: {p}")
            else:
                size_kb = p.stat().st_size / 1024
                print(f"[visionflow] {p.name}: {size_kb:.1f} KB")

        # Mix dos dois canais
        combined_path = self._output_dir / "combined.wav"
        self._mix_audio(self._mic_path, self._monitor_path, combined_path)

        print(f"[visionflow] Gravação finalizada ({duration:.0f}s)")

        return MeetingFiles(
            output_dir=self._output_dir,
            mic_wav=self._mic_path,
            system_wav=self._monitor_path,
            combined_wav=combined_path,
            started_at=self._started_at,
            duration_seconds=duration,
        )

    def _mix_audio(self, mic_path: Path, monitor_path: Path, output_path: Path) -> None:
        """Combina mic + monitor num único WAV mono 16kHz."""
        try:
            mic_data = self._read_wav_as_mono_16k(mic_path)
            monitor_data = self._read_wav_as_mono_16k(monitor_path)

            if mic_data is None and monitor_data is None:
                print("[visionflow] AVISO: nenhum áudio para mixar")
                return

            # Se só tem um dos dois, usa ele
            if mic_data is None:
                combined = monitor_data
            elif monitor_data is None:
                combined = mic_data
            else:
                # Iguala tamanhos (preenche o menor com silêncio)
                max_len = max(len(mic_data), len(monitor_data))
                mic_padded = np.pad(mic_data, (0, max_len - len(mic_data)))
                mon_padded = np.pad(monitor_data, (0, max_len - len(monitor_data)))

                # Mix: média dos dois canais (evita clipping)
                combined = ((mic_padded.astype(np.int32) + mon_padded.astype(np.int32)) // 2).astype(np.int16)

            # Salva WAV combinado (mono, 16kHz, s16)
            with wave.open(str(output_path), "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(self._sample_rate)
                wf.writeframes(combined.tobytes())

            size_kb = output_path.stat().st_size / 1024
            print(f"[visionflow] combined.wav: {size_kb:.1f} KB ({len(combined)/self._sample_rate:.0f}s)")

        except Exception as e:
            print(f"[visionflow] ERRO ao mixar áudio: {e}")

    def _read_wav_as_mono_16k(self, path: Path) -> np.ndarray | None:
        """Lê WAV, converte para mono 16kHz int16."""
        if not path.exists() or path.stat().st_size < 100:
            return None
        try:
            with wave.open(str(path), "rb") as wf:
                n_channels = wf.getnchannels()
                sample_rate = wf.getframerate()
                sample_width = wf.getsampwidth()
                n_frames = wf.getnframes()
                raw = wf.readframes(n_frames)

            print(f"[visionflow] {path.name}: {n_channels}ch {sample_rate}Hz {sample_width*8}bit {n_frames} frames")

            # Converte para int16 (se for s32, reduz)
            if sample_width == 4:
                data = np.frombuffer(raw, dtype=np.int32)
                data = (data >> 16).astype(np.int16)
            elif sample_width == 2:
                data = np.frombuffer(raw, dtype=np.int16)
            else:
                print(f"[visionflow] AVISO: sample_width={sample_width} não suportado")
                return None

            # Converte para mono (média dos canais)
            if n_channels > 1:
                data = data.reshape(-1, n_channels).mean(axis=1).astype(np.int16)

            # Resample para 16kHz se necessário
            if sample_rate != self._sample_rate:
                # Resampling simples via interpolação linear
                duration = len(data) / sample_rate
                target_len = int(duration * self._sample_rate)
                indices = np.linspace(0, len(data) - 1, target_len)
                data = np.interp(indices, np.arange(len(data)), data.astype(np.float64)).astype(np.int16)

            rms = np.sqrt(np.mean(data.astype(np.float64)**2))
            print(f"[visionflow] {path.name} → mono 16kHz: {len(data)} samples, RMS={rms:.1f}")
            return data

        except Exception as e:
            print(f"[visionflow] AVISO: erro ao ler {path.name}: {e}")
            return None
