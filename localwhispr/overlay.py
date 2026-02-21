"""Minimal floating pill overlay — pulsing emoji icons for audio feedback."""

from __future__ import annotations

import argparse
import signal
from datetime import datetime
from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from localwhispr.audio_monitor import WavTailMonitor  # noqa: E402

_CSS = """
window.whispr-pill {
    background-color: rgba(24, 24, 27, 0.92);
    border-radius: 16px;
}

.pill-box {
    padding: 5px 10px;
}

.icon-on {
    font-size: 16px;
    opacity: 1.0;
    transition: opacity 100ms ease;
}

.icon-off {
    font-size: 16px;
    opacity: 0.20;
    transition: opacity 100ms ease;
}

.rec-dot {
    color: #ef4444;
    font-size: 8px;
}

.timer {
    color: rgba(255, 255, 255, 0.45);
    font-size: 10px;
    font-variant-numeric: tabular-nums;
}
"""

_ACTIVE_THRESHOLD = 0.003


def _format_duration(seconds: float) -> str:
    h, remainder = divmod(int(seconds), 3600)
    m, s = divmod(remainder, 60)
    if h:
        return f"{h:02d}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


class RecordingOverlay(Gtk.Application):

    def __init__(self, mic_wav: Path, system_wav: Path,
                 start_time: datetime | None = None) -> None:
        super().__init__(application_id="dev.localwhispr.overlay")
        self._start_time = start_time or datetime.now()
        self._mic_mon = WavTailMonitor(mic_wav)
        self._sys_mon = WavTailMonitor(system_wav)
        self._mic_icon: Gtk.Label | None = None
        self._sys_icon: Gtk.Label | None = None
        self._timer: Gtk.Label | None = None

    def do_activate(self) -> None:
        css = Gtk.CssProvider()
        css.load_from_string(_CSS)
        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(), css,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

        win = Gtk.Window(application=self)
        win.set_title("REC")
        win.set_default_size(1, 1)
        win.set_resizable(False)
        win.add_css_class("whispr-pill")

        headerbar = Gtk.HeaderBar()
        headerbar.set_show_title_buttons(False)
        headerbar.set_visible(False)
        win.set_titlebar(headerbar)

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.add_css_class("pill-box")

        dot = Gtk.Label(label="●")
        dot.add_css_class("rec-dot")
        box.append(dot)

        self._mic_icon = Gtk.Label(label="🎤")
        self._mic_icon.add_css_class("icon-off")
        box.append(self._mic_icon)

        self._sys_icon = Gtk.Label(label="🎧")
        self._sys_icon.add_css_class("icon-off")
        box.append(self._sys_icon)

        self._timer = Gtk.Label(label="00:00")
        self._timer.add_css_class("timer")
        box.append(self._timer)

        handle = Gtk.WindowHandle()
        handle.set_child(box)
        win.set_child(handle)
        win.present()

        GLib.timeout_add(150, self._tick)

    def _tick(self) -> bool:
        mic_rms = self._mic_mon.update_raw()
        sys_rms = self._sys_mon.update_raw()

        self._toggle(self._mic_icon, mic_rms > _ACTIVE_THRESHOLD)
        self._toggle(self._sys_icon, sys_rms > _ACTIVE_THRESHOLD)

        elapsed = (datetime.now() - self._start_time).total_seconds()
        if self._timer:
            self._timer.set_text(_format_duration(elapsed))

        return True

    @staticmethod
    def _toggle(label: Gtk.Label | None, active: bool) -> None:
        if not label:
            return
        if active:
            label.remove_css_class("icon-off")
            label.add_css_class("icon-on")
        else:
            label.remove_css_class("icon-on")
            label.add_css_class("icon-off")


def run_overlay(mic_wav: str, system_wav: str,
                start_time: str | None = None) -> None:
    st = datetime.fromisoformat(start_time) if start_time else datetime.now()
    app = RecordingOverlay(Path(mic_wav), Path(system_wav), st)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM,
                         lambda: app.quit() or True)
    GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGINT,
                         lambda: app.quit() or True)
    app.run([])


def main() -> None:
    parser = argparse.ArgumentParser(description="LocalWhispr recording overlay")
    parser.add_argument("--mic-wav", required=True)
    parser.add_argument("--system-wav", required=True)
    parser.add_argument("--start-time", default=None)
    args = parser.parse_args()
    run_overlay(args.mic_wav, args.system_wav, args.start_time)


if __name__ == "__main__":
    main()
