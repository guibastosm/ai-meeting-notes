"""LocalWhispr entry point."""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys


def cmd_serve(args: argparse.Namespace) -> None:
    """Start the LocalWhispr daemon."""
    from localwhispr.config import load_config
    from localwhispr.recorder import AudioRecorder
    from localwhispr.transcriber import Transcriber
    from localwhispr.ai_cleanup import AICleanup
    from localwhispr.screenshot import ScreenshotCommand
    from localwhispr.typer import Typer
    from localwhispr.server import LocalWhisprApp, LocalWhisprDaemon

    print("=" * 60)
    print("  LocalWhispr v0.2.0")
    print("  Multimodal voice dictation with AI for Linux")
    print("=" * 60)

    config = load_config(args.config)

    # Initialize components
    recorder = AudioRecorder(config.audio)
    transcriber = Transcriber(config.whisper)
    cleanup = AICleanup(config.ollama)
    screenshot_cmd = ScreenshotCommand(config.ollama)
    typer = Typer(config.typing)

    # Pre-load model if requested
    if args.preload_model:
        print("[localwhispr] Pre-loading Whisper model...")
        transcriber._ensure_model()

    # Create app and daemon
    app = LocalWhisprApp(
        recorder=recorder,
        transcriber=transcriber,
        cleanup=cleanup,
        screenshot_cmd=screenshot_cmd,
        typer=typer,
        notif_config=config.notifications,
        meeting_config=config.meeting,
        whisper_config=config.whisper,
        ollama_config=config.ollama,
        capture_monitor=config.dictate.capture_monitor,
    )
    daemon = LocalWhisprDaemon(app)

    # Event loop
    loop = asyncio.new_event_loop()

    def shutdown(sig: int, _: object) -> None:
        print(f"\n[localwhispr] Received signal {sig}, shutting down...")
        loop.call_soon_threadsafe(loop.stop)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        loop.run_until_complete(daemon.start())
    except KeyboardInterrupt:
        print("\n[localwhispr] Stopped by user.")
    finally:
        loop.run_until_complete(daemon.cleanup())
        loop.close()


def cmd_ctl(args: argparse.Namespace) -> None:
    """Send command to the daemon."""
    from localwhispr.ctl import ctl_main
    ctl_main(args.command)


def cmd_overlay(args: argparse.Namespace) -> None:
    """Launch the recording overlay manually."""
    from localwhispr.overlay import run_overlay
    run_overlay(args.mic_wav, args.system_wav, args.start_time)


def cmd_setup_shortcuts(args: argparse.Namespace) -> None:
    """Register keyboard shortcuts in GNOME, using config.yaml as source."""
    from localwhispr.config import load_config
    from localwhispr.shortcuts import setup_gnome_shortcuts

    config = load_config(args.config if hasattr(args, "config") else None)

    # CLI flags override config.yaml, which overrides defaults
    toggle_service = args.toggle_service if args.toggle_service != "_FROM_CONFIG" else config.shortcuts.toggle_service
    dictate = args.dictate if args.dictate != "_FROM_CONFIG" else config.shortcuts.dictate
    screenshot = args.screenshot if args.screenshot != "_FROM_CONFIG" else config.shortcuts.screenshot
    meeting = args.meeting if args.meeting != "_FROM_CONFIG" else config.shortcuts.meeting

    setup_gnome_shortcuts(
        toggle_service_binding=toggle_service,
        dictate_binding=dictate,
        screenshot_binding=screenshot,
        meeting_binding=meeting,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="localwhispr",
        description="LocalWhispr: Multimodal voice dictation with AI for Linux",
    )
    subparsers = parser.add_subparsers(dest="subcmd")

    # --- serve ---
    p_serve = subparsers.add_parser(
        "serve",
        help="Start the LocalWhispr daemon (command server)",
    )
    p_serve.add_argument("-c", "--config", help="Path to config.yaml", default=None)
    p_serve.add_argument(
        "--preload-model", action="store_true",
        help="Pre-load Whisper model before accepting commands",
    )
    p_serve.set_defaults(func=cmd_serve)

    # --- ctl ---
    p_ctl = subparsers.add_parser(
        "ctl",
        help="Send command to daemon (dictate, screenshot, meeting, status, stop, ping, quit)",
    )
    p_ctl.add_argument("command", nargs="*", help="Command to send")
    p_ctl.set_defaults(func=cmd_ctl)

    # --- overlay ---
    p_overlay = subparsers.add_parser(
        "overlay",
        help="Launch the recording overlay (for debugging / manual use)",
    )
    p_overlay.add_argument("--mic-wav", required=True, help="Path to the mic WAV file being recorded")
    p_overlay.add_argument("--system-wav", required=True, help="Path to the system WAV file being recorded")
    p_overlay.add_argument("--start-time", default=None, help="Recording start time (ISO format)")
    p_overlay.set_defaults(func=cmd_overlay)

    # --- setup-shortcuts ---
    p_shortcuts = subparsers.add_parser(
        "setup-shortcuts",
        help="Configure GNOME keyboard shortcuts",
    )
    p_shortcuts.add_argument("-c", "--config", help="Path to config.yaml", default=None)
    p_shortcuts.add_argument(
        "--toggle-service", default="_FROM_CONFIG",
        help="Shortcut to toggle service on/off (default: reads from config.yaml)",
    )
    p_shortcuts.add_argument(
        "--dictate", default="_FROM_CONFIG",
        help="Shortcut for toggle dictation (default: reads from config.yaml)",
    )
    p_shortcuts.add_argument(
        "--screenshot", default="_FROM_CONFIG",
        help="Shortcut for toggle screenshot+AI (default: reads from config.yaml)",
    )
    p_shortcuts.add_argument(
        "--meeting", default="_FROM_CONFIG",
        help="Shortcut for toggle meeting (default: reads from config.yaml)",
    )
    p_shortcuts.set_defaults(func=cmd_setup_shortcuts)

    args = parser.parse_args()

    if not args.subcmd:
        parser.print_help()
        print()
        print("Quick start:")
        print("  1. localwhispr serve --preload-model    # start the daemon")
        print("  2. localwhispr setup-shortcuts           # configure GNOME shortcuts")
        print("  3. Use Ctrl+Super+D to dictate, Ctrl+Shift+S for screenshot+AI, Ctrl+Super+M for meeting")
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
