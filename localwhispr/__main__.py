"""Entry point do LocalWhispr."""

from __future__ import annotations

import argparse
import asyncio
import signal
import sys


def cmd_serve(args: argparse.Namespace) -> None:
    """Inicia o daemon LocalWhispr."""
    from localwhispr.config import load_config
    from localwhispr.recorder import AudioRecorder
    from localwhispr.transcriber import Transcriber
    from localwhispr.ai_cleanup import AICleanup
    from localwhispr.screenshot import ScreenshotCommand
    from localwhispr.typer import Typer
    from localwhispr.server import LocalWhisprApp, LocalWhisprDaemon

    print("=" * 60)
    print("  LocalWhispr v0.1.0")
    print("  Ditado por voz multimodal com IA para Linux")
    print("=" * 60)

    config = load_config(args.config)

    # Inicializa componentes
    recorder = AudioRecorder(config.audio)
    transcriber = Transcriber(config.whisper)
    cleanup = AICleanup(config.ollama)
    screenshot_cmd = ScreenshotCommand(config.ollama)
    typer = Typer(config.typing)

    # Pré-carrega modelo se solicitado
    if args.preload_model:
        print("[localwhispr] Pré-carregando modelo Whisper...")
        transcriber._ensure_model()

    # Cria app e daemon
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
        print(f"\n[localwhispr] Recebido sinal {sig}, encerrando...")
        loop.call_soon_threadsafe(loop.stop)

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    try:
        loop.run_until_complete(daemon.start())
    except KeyboardInterrupt:
        print("\n[localwhispr] Encerrado pelo usuário.")
    finally:
        loop.run_until_complete(daemon.cleanup())
        loop.close()


def cmd_ctl(args: argparse.Namespace) -> None:
    """Envia comando ao daemon."""
    from localwhispr.ctl import ctl_main
    ctl_main(args.command)


def cmd_setup_shortcuts(args: argparse.Namespace) -> None:
    """Registra atalhos no GNOME, usando config.yaml como fonte dos bindings."""
    from localwhispr.config import load_config
    from localwhispr.shortcuts import setup_gnome_shortcuts

    config = load_config(args.config if hasattr(args, "config") else None)

    # CLI flags sobrescrevem config.yaml, que sobrescreve defaults
    dictate = args.dictate if args.dictate != "_FROM_CONFIG" else config.shortcuts.dictate
    screenshot = args.screenshot if args.screenshot != "_FROM_CONFIG" else config.shortcuts.screenshot
    meeting = args.meeting if args.meeting != "_FROM_CONFIG" else config.shortcuts.meeting

    setup_gnome_shortcuts(
        dictate_binding=dictate,
        screenshot_binding=screenshot,
        meeting_binding=meeting,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="localwhispr",
        description="LocalWhispr: Ditado por voz multimodal com IA para Linux",
    )
    subparsers = parser.add_subparsers(dest="subcmd")

    # --- serve ---
    p_serve = subparsers.add_parser(
        "serve",
        help="Inicia o daemon LocalWhispr (servidor de comandos)",
    )
    p_serve.add_argument("-c", "--config", help="Caminho para config.yaml", default=None)
    p_serve.add_argument(
        "--preload-model", action="store_true",
        help="Pré-carrega o modelo Whisper antes de aceitar comandos",
    )
    p_serve.set_defaults(func=cmd_serve)

    # --- ctl ---
    p_ctl = subparsers.add_parser(
        "ctl",
        help="Envia comando ao daemon (dictate, screenshot, meeting, status, stop, ping, quit)",
    )
    p_ctl.add_argument("command", nargs="*", help="Comando a enviar")
    p_ctl.set_defaults(func=cmd_ctl)

    # --- setup-shortcuts ---
    p_shortcuts = subparsers.add_parser(
        "setup-shortcuts",
        help="Configura atalhos de teclado do GNOME",
    )
    p_shortcuts.add_argument("-c", "--config", help="Caminho para config.yaml", default=None)
    p_shortcuts.add_argument(
        "--dictate", default="_FROM_CONFIG",
        help="Atalho para toggle ditado (padrão: lê do config.yaml)",
    )
    p_shortcuts.add_argument(
        "--screenshot", default="_FROM_CONFIG",
        help="Atalho para toggle screenshot+IA (padrão: lê do config.yaml)",
    )
    p_shortcuts.add_argument(
        "--meeting", default="_FROM_CONFIG",
        help="Atalho para toggle reunião (padrão: lê do config.yaml)",
    )
    p_shortcuts.set_defaults(func=cmd_setup_shortcuts)

    args = parser.parse_args()

    if not args.subcmd:
        # Sem subcomando: mostra ajuda
        parser.print_help()
        print()
        print("Início rápido:")
        print("  1. localwhispr serve --preload-model    # inicia o daemon")
        print("  2. localwhispr setup-shortcuts           # configura atalhos GNOME")
        print("  3. Use Ctrl+Shift+D para ditar, Ctrl+Shift+S para screenshot+IA, Ctrl+Shift+M para reunião")
        sys.exit(0)

    args.func(args)


if __name__ == "__main__":
    main()
