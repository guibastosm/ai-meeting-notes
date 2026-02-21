"""Load and validate LocalWhispr configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ShortcutConfig:
    toggle_service: str = "<Ctrl><Super>w"
    dictate: str = "<Ctrl><Shift>d"
    screenshot: str = "<Ctrl><Shift>s"
    meeting: str = "<Ctrl><Shift>m"


@dataclass
class WhisperConfig:
    model: str = "large-v3"
    language: str = ""
    device: str = "cuda"
    compute_type: str = "float16"


@dataclass
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    cleanup_model: str = "llama3.2"
    vision_model: str = "gemma3:12b"
    cleanup_prompt: str = (
        "You are a voice transcription polishing assistant.\n"
        "Receive raw transcribed text and return ONLY the cleaned text:\n"
        "- Remove hesitations (uh, uhm, hmm, eh, like, you know, so, well, tipo, né, então, assim)\n"
        "- Add correct punctuation\n"
        "- Fix obvious transcription errors\n"
        "- Keep the original meaning intact\n"
        "- ALWAYS respond in the SAME LANGUAGE as the input text\n"
        "- Respond ONLY with the cleaned text, no explanations or preambles."
    )


@dataclass
class TypingConfig:
    method: str = "ydotool"  # "ydotool" or "wtype"
    delay_ms: int = 12


@dataclass
class DictateConfig:
    capture_monitor: bool = False


@dataclass
class AudioConfig:
    sample_rate: int = 16000
    channels: int = 1


@dataclass
class NotificationConfig:
    enabled: bool = True
    sound: bool = True


@dataclass
class MeetingConfig:
    output_dir: str = "~/LocalWhispr/meetings"
    mic_source: str = "auto"
    monitor_source: str = "auto"
    sample_rate: int = 16000
    overlay: bool = True
    summary_model: str = "llama3.2"
    summary_prompt: str = (
        "You are a meeting minutes assistant.\n"
        "Receive a meeting transcription and generate:\n"
        "1. SUMMARY: short paragraphs with the main points\n"
        "2. DECISIONS: list of decisions made\n"
        "3. ACTION ITEMS: task list with responsible people (if mentioned)\n"
        "4. TOPICS: list of subjects discussed\n"
        "Format: clean and organized Markdown.\n"
        "IMPORTANT: Respond in the SAME LANGUAGE as the transcription."
    )


@dataclass
class LocalWhisprConfig:
    shortcuts: ShortcutConfig = field(default_factory=ShortcutConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    typing: TypingConfig = field(default_factory=TypingConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    dictate: DictateConfig = field(default_factory=DictateConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    meeting: MeetingConfig = field(default_factory=MeetingConfig)


def _apply_dict(dc: Any, data: dict) -> None:
    """Apply a dictionary onto an existing dataclass."""
    for key, value in data.items():
        if hasattr(dc, key):
            setattr(dc, key, value)


def load_config(path: str | Path | None = None) -> LocalWhisprConfig:
    """Load configuration from YAML. Searches in order:
    1. Explicit path
    2. ./config.yaml
    3. ~/.config/localwhispr/config.yaml
    """
    search_paths: list[Path] = []

    if path:
        search_paths.append(Path(path))

    search_paths.extend([
        Path.cwd() / "config.yaml",
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "localwhispr" / "config.yaml",
    ])

    config = LocalWhisprConfig()

    for p in search_paths:
        if p.is_file():
            with open(p) as f:
                raw = yaml.safe_load(f) or {}

            if "shortcuts" in raw:
                _apply_dict(config.shortcuts, raw["shortcuts"])
            if "whisper" in raw:
                _apply_dict(config.whisper, raw["whisper"])
            if "ollama" in raw:
                _apply_dict(config.ollama, raw["ollama"])
            if "typing" in raw:
                _apply_dict(config.typing, raw["typing"])
            if "audio" in raw:
                _apply_dict(config.audio, raw["audio"])
            if "dictate" in raw:
                _apply_dict(config.dictate, raw["dictate"])
            if "notifications" in raw:
                _apply_dict(config.notifications, raw["notifications"])
            if "meeting" in raw:
                _apply_dict(config.meeting, raw["meeting"])

            print(f"[localwhispr] Config loaded from: {p}")
            return config

    print("[localwhispr] No config.yaml found, using defaults.")
    return config
