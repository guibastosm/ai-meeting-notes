"""Transcrição de áudio usando faster-whisper com CUDA."""

from __future__ import annotations

import io
import time
from typing import TYPE_CHECKING

from faster_whisper import WhisperModel

if TYPE_CHECKING:
    from localwhispr.config import WhisperConfig


class Transcriber:
    """Wrapper sobre faster-whisper com suporte a CUDA."""

    def __init__(self, config: WhisperConfig | None = None) -> None:
        from localwhispr.config import WhisperConfig as WC

        cfg = config or WC()
        self._language = cfg.language
        self._model: WhisperModel | None = None
        self._model_name = cfg.model
        self._device = cfg.device
        self._compute_type = cfg.compute_type

    def _ensure_model(self) -> WhisperModel:
        if self._model is None:
            print(
                f"[localwhispr] Carregando modelo Whisper '{self._model_name}' "
                f"(device={self._device}, compute={self._compute_type})..."
            )
            t0 = time.time()
            self._model = WhisperModel(
                self._model_name,
                device=self._device,
                compute_type=self._compute_type,
            )
            print(f"[localwhispr] Modelo carregado em {time.time() - t0:.1f}s")
        return self._model

    def transcribe(self, wav_bytes: bytes) -> str:
        """Transcreve bytes WAV e retorna o texto."""
        if not wav_bytes:
            return ""

        model = self._ensure_model()
        audio_file = io.BytesIO(wav_bytes)

        segments, info = model.transcribe(
            audio_file,
            language=self._language if self._language else None,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=300,
            ),
        )

        text_parts: list[str] = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        result = " ".join(text_parts).strip()
        if result:
            print(f"[localwhispr] Transcrição: {result[:100]}...")
        return result

    def transcribe_with_timestamps(self, wav_bytes: bytes) -> list[tuple[float, float, str]]:
        """Transcreve bytes WAV e retorna segmentos com timestamps: [(start, end, text), ...]."""
        if not wav_bytes:
            return []

        model = self._ensure_model()
        audio_file = io.BytesIO(wav_bytes)

        segments, info = model.transcribe(
            audio_file,
            language=self._language if self._language else None,
            beam_size=5,
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=300,
            ),
        )

        result: list[tuple[float, float, str]] = []
        for segment in segments:
            text = segment.text.strip()
            if text:
                result.append((segment.start, segment.end, text))

        if result:
            total_text = " ".join(t for _, _, t in result)
            print(f"[localwhispr] Transcrição ({len(result)} segs): {total_text[:100]}...")
        return result
