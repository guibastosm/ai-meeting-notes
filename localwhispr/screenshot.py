"""Captura de tela + comando de voz via Ollama multimodal."""

from __future__ import annotations

import base64
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from localwhispr.config import OllamaConfig


def _capture_screenshot() -> bytes | None:
    """Captura screenshot da tela. Tenta múltiplos métodos em ordem."""
    # Método 1: Simula PrintScreen via ydotool e pega do clipboard (GNOME Wayland)
    if shutil.which("ydotool") and shutil.which("wl-paste"):
        img = _screenshot_via_printscreen()
        if img:
            return img

    # Método 2: gnome-screenshot direto em arquivo
    if shutil.which("gnome-screenshot"):
        img = _screenshot_via_tool(["gnome-screenshot", "-f"])
        if img:
            return img

    # Método 3: grim (sway, outros compositors Wayland)
    if shutil.which("grim"):
        img = _screenshot_via_tool(["grim"])
        if img:
            return img

    print("[localwhispr] ERRO: Nenhum método de screenshot funcionou.")
    print("[localwhispr] No GNOME 49+, o LocalWhispr usa PrintScreen + clipboard.")
    return None


def _screenshot_via_printscreen() -> bytes | None:
    """Simula Shift+PrintScreen, GNOME captura tela direta para o clipboard."""
    import time

    try:
        # Simula Shift+PrintScreen (Shift=42, PrintScreen=99)
        # GNOME mapeia Shift+Print para captura direta da tela inteira
        subprocess.run(
            ["ydotool", "key", "42:1", "99:1", "99:0", "42:0"],
            timeout=2,
            capture_output=True,
        )

        # Espera o GNOME processar e copiar ao clipboard
        time.sleep(2.0)

        # Pega a imagem do clipboard
        result = subprocess.run(
            ["wl-paste", "--type", "image/png", "--no-newline"],
            capture_output=True,
            timeout=3,
        )

        if result.returncode == 0 and len(result.stdout) > 100:
            print(f"[localwhispr] Screenshot via Shift+PrintScreen+clipboard ({len(result.stdout)} bytes)")
            return result.stdout

        return None

    except Exception as e:
        print(f"[localwhispr] AVISO: screenshot via PrintScreen falhou: {e}")
        return None


def _screenshot_via_tool(cmd_prefix: list[str]) -> bytes | None:
    """Captura screenshot via ferramenta CLI que salva em arquivo."""
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        result = subprocess.run(
            [*cmd_prefix, tmp_path],
            capture_output=True,
            timeout=5,
        )

        if result.returncode != 0:
            return None

        screenshot_path = Path(tmp_path)
        if screenshot_path.exists() and screenshot_path.stat().st_size > 0:
            return screenshot_path.read_bytes()
        return None

    except Exception:
        return None
    finally:
        Path(tmp_path).unlink(missing_ok=True)


class ScreenshotCommand:
    """Processa comandos de voz com contexto visual (screenshot)."""

    def __init__(self, config: OllamaConfig | None = None) -> None:
        from localwhispr.config import OllamaConfig as OC

        cfg = config or OC()
        self._base_url = cfg.base_url.rstrip("/")
        self._model = cfg.vision_model

    def execute(self, voice_command: str) -> str:
        """Captura screenshot, combina com o comando de voz e envia ao LLM multimodal."""
        if not voice_command.strip():
            return ""

        # Captura screenshot
        screenshot_bytes = _capture_screenshot()

        if screenshot_bytes is None:
            print("[localwhispr] Executando comando sem screenshot...")
            return self._text_only_command(voice_command)

        # Codifica em base64 para a API do Ollama
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        print(f"[localwhispr] Screenshot capturado ({len(screenshot_bytes)} bytes)")
        print(f"[localwhispr] Comando de voz: {voice_command[:80]}...")

        try:
            response = httpx.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": (
                        "Você está vendo a tela do computador do usuário. "
                        "O usuário fez o seguinte pedido por voz:\n\n"
                        f'"{voice_command}"\n\n'
                        "Responda de forma direta e útil baseado no que você vê na tela "
                        "e no pedido do usuário. Responda APENAS com o conteúdo solicitado, "
                        "sem explicações extras."
                    ),
                    "images": [screenshot_b64],
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 4096,
                    },
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            result = data.get("response", "").strip()

            if result:
                print(f"[localwhispr] Resposta da IA: {result[:100]}...")
            return result

        except httpx.ConnectError:
            print("[localwhispr] ERRO: Não foi possível conectar ao Ollama.")
            return f"[ERRO: Ollama não está acessível em {self._base_url}]"
        except Exception as e:
            print(f"[localwhispr] ERRO no comando com screenshot: {e}")
            return f"[ERRO: {e}]"

    def _text_only_command(self, voice_command: str) -> str:
        """Fallback: executa comando sem screenshot."""
        try:
            response = httpx.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": voice_command,
                    "stream": False,
                    "options": {
                        "temperature": 0.3,
                        "num_predict": 4096,
                    },
                },
                timeout=60.0,
            )
            response.raise_for_status()
            data = response.json()
            return data.get("response", "").strip()
        except Exception as e:
            print(f"[localwhispr] ERRO no comando de texto: {e}")
            return f"[ERRO: {e}]"
