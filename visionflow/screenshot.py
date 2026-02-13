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
    from visionflow.config import OllamaConfig


def _capture_screenshot() -> bytes | None:
    """Captura screenshot da tela. Tenta múltiplos métodos em ordem."""
    import time, json
    LOG_PATH = "/home/morcegod/Documents/lab/ai-meeting-notes/.cursor/debug.log"
    def _dbg(msg, data=None, hyp=""):
        try:
            entry = json.dumps({"timestamp": int(time.time()*1000), "location": "screenshot.py:_capture", "message": msg, "data": data or {}, "hypothesisId": hyp, "runId": "run1"})
            with open(LOG_PATH, "a") as f: f.write(entry + "\n")
        except: pass

    # #region agent log
    _dbg("capture_start", {"has_ydotool": bool(shutil.which("ydotool")), "has_wlpaste": bool(shutil.which("wl-paste")), "has_gnome_screenshot": bool(shutil.which("gnome-screenshot")), "has_grim": bool(shutil.which("grim"))}, "H1")
    # #endregion

    # Método 1: Simula PrintScreen via ydotool e pega do clipboard (GNOME Wayland)
    if shutil.which("ydotool") and shutil.which("wl-paste"):
        img = _screenshot_via_printscreen()
        # #region agent log
        _dbg("method1_result", {"img_len": len(img) if img else 0}, "H1")
        # #endregion
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

    print("[visionflow] ERRO: Nenhum método de screenshot funcionou.")
    print("[visionflow] No GNOME 49+, o VisionFlow usa PrintScreen + clipboard.")
    return None


def _screenshot_via_printscreen() -> bytes | None:
    """Simula Shift+PrintScreen, GNOME captura tela direta para o clipboard."""
    import time
    import json

    LOG_PATH = "/home/morcegod/Documents/lab/ai-meeting-notes/.cursor/debug.log"

    def _dbg(msg, data=None, hyp=""):
        try:
            import os; entry = json.dumps({"timestamp": int(time.time()*1000), "location": "screenshot.py", "message": msg, "data": data or {}, "hypothesisId": hyp, "runId": "run1"})
            with open(LOG_PATH, "a") as f: f.write(entry + "\n")
        except: pass

    try:
        # #region agent log
        _dbg("screenshot_start", {"method": "Shift+PrintScreen"}, "H1")
        # #endregion

        # Simula Shift+PrintScreen (Shift=42, PrintScreen=99)
        # GNOME mapeia Shift+Print para captura direta da tela inteira
        ydotool_result = subprocess.run(
            ["ydotool", "key", "42:1", "99:1", "99:0", "42:0"],
            timeout=2,
            capture_output=True,
        )

        # #region agent log
        _dbg("ydotool_result", {"rc": ydotool_result.returncode, "stderr": ydotool_result.stderr.decode()[:200]}, "H2")
        # #endregion

        # Espera o GNOME processar e copiar ao clipboard
        time.sleep(2.0)

        # #region agent log
        _dbg("clipboard_check_start", {}, "H3")
        # #endregion

        # Pega a imagem do clipboard
        result = subprocess.run(
            ["wl-paste", "--type", "image/png", "--no-newline"],
            capture_output=True,
            timeout=3,
        )

        # #region agent log
        _dbg("clipboard_result", {"rc": result.returncode, "stdout_len": len(result.stdout), "stderr": result.stderr.decode()[:200]}, "H3")
        # #endregion

        if result.returncode == 0 and len(result.stdout) > 100:
            # #region agent log
            _dbg("screenshot_success", {"bytes": len(result.stdout)}, "H2")
            # #endregion
            print(f"[visionflow] Screenshot via Shift+PrintScreen+clipboard ({len(result.stdout)} bytes)")
            return result.stdout

        # #region agent log
        _dbg("screenshot_failed_clipboard_empty", {"rc": result.returncode, "stdout_len": len(result.stdout)}, "H1")
        # #endregion
        return None

    except Exception as e:
        # #region agent log
        _dbg("screenshot_exception", {"error": str(e)}, "H1")
        # #endregion
        print(f"[visionflow] AVISO: screenshot via PrintScreen falhou: {e}")
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
        from visionflow.config import OllamaConfig as OC

        cfg = config or OC()
        self._base_url = cfg.base_url.rstrip("/")
        self._model = cfg.vision_model

    def execute(self, voice_command: str) -> str:
        """Captura screenshot, combina com o comando de voz e envia ao LLM multimodal."""
        import time as _time, json as _json
        _LOG_PATH = "/home/morcegod/Documents/lab/ai-meeting-notes/.cursor/debug.log"
        def _dbg(msg, data=None, hyp=""):
            try:
                entry = _json.dumps({"timestamp": int(_time.time()*1000), "location": "screenshot.py:execute", "message": msg, "data": data or {}, "hypothesisId": hyp, "runId": "run1"})
                with open(_LOG_PATH, "a") as f: f.write(entry + "\n")
            except: pass

        if not voice_command.strip():
            return ""

        # #region agent log
        _dbg("execute_start", {"voice_cmd": voice_command[:80], "model": self._model, "base_url": self._base_url}, "H4")
        # #endregion

        # Captura screenshot
        screenshot_bytes = _capture_screenshot()

        # #region agent log
        _dbg("execute_screenshot_result", {"has_screenshot": screenshot_bytes is not None, "bytes": len(screenshot_bytes) if screenshot_bytes else 0}, "H1")
        # #endregion

        if screenshot_bytes is None:
            print("[visionflow] Executando comando sem screenshot...")
            return self._text_only_command(voice_command)

        # Codifica em base64 para a API do Ollama
        screenshot_b64 = base64.b64encode(screenshot_bytes).decode("utf-8")

        # #region agent log
        _dbg("execute_sending_to_ollama", {"b64_len": len(screenshot_b64), "model": self._model}, "H4")
        # #endregion

        print(f"[visionflow] Screenshot capturado ({len(screenshot_bytes)} bytes)")
        print(f"[visionflow] Comando de voz: {voice_command[:80]}...")

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
                print(f"[visionflow] Resposta da IA: {result[:100]}...")
            return result

        except httpx.ConnectError:
            print("[visionflow] ERRO: Não foi possível conectar ao Ollama.")
            return f"[ERRO: Ollama não está acessível em {self._base_url}]"
        except Exception as e:
            print(f"[visionflow] ERRO no comando com screenshot: {e}")
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
            print(f"[visionflow] ERRO no comando de texto: {e}")
            return f"[ERRO: {e}]"
