"""Notificações de status do VisionFlow via libnotify e sons."""

from __future__ import annotations

import subprocess
import shutil

from visionflow.config import NotificationConfig


def _has_command(cmd: str) -> bool:
    return shutil.which(cmd) is not None


def notify(title: str, body: str = "", config: NotificationConfig | None = None) -> None:
    """Envia uma notificação via notify-send."""
    if config and not config.enabled:
        return

    if not _has_command("notify-send"):
        return

    try:
        cmd = [
            "notify-send",
            "--app-name=VisionFlow",
            "--transient",
            "--urgency=low",
            title,
        ]
        if body:
            cmd.append(body)
        subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        pass


def play_sound(sound_name: str = "message", config: NotificationConfig | None = None) -> None:
    """Toca um som de feedback usando canberra-gtk-play ou paplay."""
    if config and not config.sound:
        return

    if _has_command("canberra-gtk-play"):
        try:
            subprocess.Popen(
                ["canberra-gtk-play", "-i", sound_name],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except Exception:
            pass


def notify_recording_start(config: NotificationConfig | None = None) -> None:
    # Apenas som — sem notificação visual para não flodar o painel
    play_sound("dialog-information", config)


def notify_recording_stop(config: NotificationConfig | None = None) -> None:
    # Apenas som — sem notificação visual para não flodar o painel
    play_sound("message-sent-instant", config)


def notify_done(text: str, config: NotificationConfig | None = None) -> None:
    # Som apenas — o texto já foi colado na app focada
    play_sound("message", config)


def notify_error(error: str, config: NotificationConfig | None = None) -> None:
    # Erro sim merece notificação visual + som
    notify("VisionFlow - Erro", error, config)
    play_sound("dialog-error", config)
