"""Cliente CLI para enviar comandos ao daemon VisionFlow via Unix socket."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

SOCKET_PATH = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")) / "visionflow.sock"


async def send_command(command: str) -> str:
    """Envia um comando ao daemon e retorna a resposta."""
    if not SOCKET_PATH.exists():
        print("[visionflow] Daemon não está rodando.")
        print("[visionflow] Inicie com: visionflow serve")
        sys.exit(1)

    try:
        reader, writer = await asyncio.open_unix_connection(str(SOCKET_PATH))
        writer.write(command.encode())
        await writer.drain()

        response = await asyncio.wait_for(reader.read(4096), timeout=5.0)
        writer.close()
        await writer.wait_closed()
        return response.decode().strip()

    except ConnectionRefusedError:
        print("[visionflow] Daemon não está respondendo.")
        print("[visionflow] Reinicie com: visionflow serve")
        sys.exit(1)
    except asyncio.TimeoutError:
        print("[visionflow] Timeout aguardando resposta do daemon.")
        sys.exit(1)


def ctl_main(args: list[str]) -> None:
    """Entry point para o subcomando 'ctl'."""
    if not args:
        print("Uso: visionflow ctl <comando>")
        print()
        print("Comandos disponíveis:")
        print("  dictate      Toggle gravação de ditado (iniciar/parar)")
        print("  screenshot   Toggle gravação screenshot + IA multimodal")
        print("  meeting      Toggle gravação de reunião (mic + sistema)")
        print("  status       Verifica status atual do daemon")
        print("  stop         Cancela gravação em andamento")
        print("  ping         Verifica se o daemon está vivo")
        print("  quit         Encerra o daemon")
        sys.exit(0)

    command = args[0]
    valid_commands = {"dictate", "screenshot", "meeting", "status", "stop", "ping", "quit"}

    if command not in valid_commands:
        print(f"[visionflow] Comando desconhecido: {command}")
        print(f"[visionflow] Comandos válidos: {', '.join(sorted(valid_commands))}")
        sys.exit(1)

    response = asyncio.run(send_command(command))
    print(response)
