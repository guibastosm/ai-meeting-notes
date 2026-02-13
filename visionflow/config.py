"""Carrega e valida a configuração do VisionFlow."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class ShortcutConfig:
    dictate: str = "<Ctrl><Shift>d"
    screenshot: str = "<Ctrl><Shift>s"
    meeting: str = "<Ctrl><Shift>m"


@dataclass
class WhisperConfig:
    model: str = "large-v3"
    language: str = "pt"
    device: str = "cuda"
    compute_type: str = "float16"


@dataclass
class OllamaConfig:
    base_url: str = "http://localhost:11434"
    cleanup_model: str = "llama3.2"
    vision_model: str = "gemma3:12b"
    cleanup_prompt: str = (
        "Você é um assistente de polimento de texto.\n"
        "Receba texto transcrito de voz e retorne APENAS o texto limpo:\n"
        "- Remova hesitações (uh, hmm, eh, tipo, né, então, assim)\n"
        "- Adicione pontuação correta\n"
        "- Corrija erros óbvios de transcrição\n"
        "- Mantenha o significado original intacto\n"
        "- Responda SOMENTE com o texto limpo, sem explicações ou prefácios."
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
    output_dir: str = "~/VisionFlow/meetings"
    mic_source: str = "auto"
    monitor_source: str = "auto"
    sample_rate: int = 16000
    summary_model: str = "llama3.2"
    summary_prompt: str = (
        "Você é um assistente de atas de reunião.\n"
        "Receba a transcrição de uma reunião e gere:\n"
        "1. RESUMO: parágrafos curtos com os pontos principais\n"
        "2. DECISÕES: lista de decisões tomadas\n"
        "3. ACTION ITEMS: lista de tarefas com responsáveis (se mencionados)\n"
        "4. TÓPICOS: lista dos assuntos discutidos\n"
        "Formato: Markdown limpo e organizado."
    )


@dataclass
class VisionFlowConfig:
    shortcuts: ShortcutConfig = field(default_factory=ShortcutConfig)
    whisper: WhisperConfig = field(default_factory=WhisperConfig)
    ollama: OllamaConfig = field(default_factory=OllamaConfig)
    typing: TypingConfig = field(default_factory=TypingConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    dictate: DictateConfig = field(default_factory=DictateConfig)
    notifications: NotificationConfig = field(default_factory=NotificationConfig)
    meeting: MeetingConfig = field(default_factory=MeetingConfig)


def _apply_dict(dc: Any, data: dict) -> None:
    """Aplica um dicionário sobre um dataclass existente."""
    for key, value in data.items():
        if hasattr(dc, key):
            setattr(dc, key, value)


def load_config(path: str | Path | None = None) -> VisionFlowConfig:
    """Carrega configuração do YAML. Procura em ordem:
    1. Caminho explícito
    2. ./config.yaml
    3. ~/.config/visionflow/config.yaml
    """
    search_paths: list[Path] = []

    if path:
        search_paths.append(Path(path))

    search_paths.extend([
        Path.cwd() / "config.yaml",
        Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "visionflow" / "config.yaml",
    ])

    config = VisionFlowConfig()

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

            print(f"[visionflow] Config carregado de: {p}")
            return config

    print("[visionflow] Nenhum config.yaml encontrado, usando padrões.")
    return config
