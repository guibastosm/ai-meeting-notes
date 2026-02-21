"""Monitor audio levels from growing WAV files written by pw-record/parecord."""

from __future__ import annotations

import math
import struct
import time
from pathlib import Path

import numpy as np


class WavTailMonitor:
    """Reads the tail of a WAV file being written to compute RMS audio levels.

    Designed for files actively written by pw-record or parecord.  Parses the
    WAV header once and then periodically reads the last chunk of raw PCM to
    calculate a normalised RMS level (0.0 – 1.0).

    The returned level uses a dB-based perceptual scale with auto-peak
    normalisation so that typical speech/audio fills most of the 0–1 range.
    """

    SILENCE_THRESHOLD = 0.005
    SILENCE_TIMEOUT_S = 5.0
    CHUNK_BYTES = 8192

    _DB_FLOOR = -45.0
    _DB_CEIL = -5.0

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._n_channels: int = 0
        self._sample_width: int = 0
        self._sample_rate: int = 0
        self._data_offset: int = 0
        self._header_parsed = False

        self._last_file_size: int = 0
        self._level: float = 0.0
        self._raw_rms: float = 0.0
        self._last_nonsilent: float = time.monotonic()
        self._growing = False

    # -- public API ----------------------------------------------------------

    @property
    def level(self) -> float:
        """Most recent RMS level in 0.0 – 1.0 range."""
        return self._level

    @property
    def is_silent(self) -> bool:
        """True when the signal has been near-zero for longer than the timeout."""
        return (time.monotonic() - self._last_nonsilent) > self.SILENCE_TIMEOUT_S

    @property
    def is_growing(self) -> bool:
        """True when the file grew since the previous update."""
        return self._growing

    def _refresh(self) -> None:
        """Re-read the file tail and recompute raw RMS."""
        if not self._path.exists():
            self._raw_rms = 0.0
            self._level = 0.0
            self._growing = False
            return

        try:
            file_size = self._path.stat().st_size
        except OSError:
            self._raw_rms = 0.0
            self._level = 0.0
            self._growing = False
            return

        self._growing = file_size > self._last_file_size
        self._last_file_size = file_size

        if not self._header_parsed:
            if not self._parse_header():
                return

        if file_size <= self._data_offset:
            self._raw_rms = 0.0
            self._level = 0.0
            return

        self._raw_rms = self._compute_rms(file_size)

        if self._raw_rms > self.SILENCE_THRESHOLD:
            self._last_nonsilent = time.monotonic()

        self._level = self._to_perceptual(self._raw_rms)

    def update(self) -> float:
        """Read the file tail and return the perceptual level (0.0–1.0)."""
        self._refresh()
        return self._level

    def update_raw(self) -> float:
        """Read the file tail and return the raw linear RMS (0.0–1.0)."""
        self._refresh()
        return self._raw_rms

    def _to_perceptual(self, rms: float) -> float:
        """Map linear RMS to a 0–1 perceptual scale via dB."""
        if rms < 1e-7:
            return 0.0
        db = 20.0 * math.log10(rms)
        normalised = (db - self._DB_FLOOR) / (self._DB_CEIL - self._DB_FLOOR)
        return max(0.0, min(1.0, normalised))

    # -- internals -----------------------------------------------------------

    def _parse_header(self) -> bool:
        """Parse the WAV/RIFF header to discover PCM layout and data offset."""
        try:
            with open(self._path, "rb") as f:
                header = f.read(128)
        except OSError:
            return False

        if len(header) < 44 or header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            return False

        pos = 12
        while pos + 8 <= len(header):
            chunk_id = header[pos : pos + 4]
            chunk_size = struct.unpack_from("<I", header, pos + 4)[0]

            if chunk_id == b"fmt ":
                if pos + 8 + 16 > len(header):
                    return False
                fmt = struct.unpack_from("<HHIIHH", header, pos + 8)
                self._n_channels = fmt[1]
                self._sample_rate = fmt[2]
                self._sample_width = fmt[5] // 8

            elif chunk_id == b"data":
                self._data_offset = pos + 8
                if self._n_channels and self._sample_width:
                    self._header_parsed = True
                    return True
                return False

            pos += 8 + chunk_size
            if chunk_size % 2:
                pos += 1  # RIFF chunks are word-aligned

        return False

    def _compute_rms(self, file_size: int) -> float:
        """Read the last chunk of PCM data and return normalised RMS."""
        frame_size = self._n_channels * self._sample_width
        if frame_size == 0:
            return 0.0

        read_bytes = min(self.CHUNK_BYTES, file_size - self._data_offset)
        read_bytes -= read_bytes % frame_size  # align to whole frames
        if read_bytes <= 0:
            return 0.0

        offset = max(self._data_offset, file_size - read_bytes)

        try:
            with open(self._path, "rb") as f:
                f.seek(offset)
                raw = f.read(read_bytes)
        except OSError:
            return 0.0

        if len(raw) < frame_size:
            return 0.0

        if self._sample_width == 2:
            samples = np.frombuffer(raw, dtype=np.int16)
            max_val = 32768.0
        elif self._sample_width == 4:
            samples = (np.frombuffer(raw, dtype=np.int32) >> 16).astype(np.int16)
            max_val = 32768.0
        else:
            return 0.0

        if self._n_channels > 1:
            samples = samples.reshape(-1, self._n_channels).mean(axis=1).astype(np.int16)

        rms = np.sqrt(np.mean(samples.astype(np.float64) ** 2))
        return min(rms / max_val, 1.0)
