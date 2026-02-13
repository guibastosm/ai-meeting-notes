"""Injeção de texto no app focado via ydotool ou wtype (Wayland)."""

from __future__ import annotations

import shutil
import subprocess
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from visionflow.config import TypingConfig


def _has_command(cmd: str) -> bool:
    return shutil.which(cmd) is not None


class Typer:
    """Digita texto no app atualmente focado usando ferramentas do Wayland."""

    def __init__(self, config: TypingConfig | None = None) -> None:
        from visionflow.config import TypingConfig as TC

        cfg = config or TC()
        self._method = cfg.method
        self._delay_ms = cfg.delay_ms
        self._validated = False

    def _validate(self) -> None:
        if self._validated:
            return

        if self._method == "ydotool" and not _has_command("ydotool"):
            print("[visionflow] AVISO: ydotool não encontrado, tentando wtype...")
            if _has_command("wtype"):
                self._method = "wtype"
            else:
                raise RuntimeError(
                    "Nenhuma ferramenta de digitação encontrada. "
                    "Instale ydotool ou wtype: sudo pacman -S ydotool wtype"
                )
        elif self._method == "wtype" and not _has_command("wtype"):
            print("[visionflow] AVISO: wtype não encontrado, tentando ydotool...")
            if _has_command("ydotool"):
                self._method = "ydotool"
            else:
                raise RuntimeError(
                    "Nenhuma ferramenta de digitação encontrada. "
                    "Instale ydotool ou wtype: sudo pacman -S ydotool wtype"
                )

        self._validated = True

    def type_text(self, text: str) -> None:
        """Digita o texto no app focado."""
        if not text:
            return

        self._validate()

        # Sempre usa clipboard para texto com caracteres Unicode/acentos
        # ydotool type não lida bem com ã, í, ç, õ, etc.
        self._type_clipboard(text)

    def _type_ydotool(self, text: str) -> None:
        """Digita usando ydotool (funciona na maioria dos compositors Wayland)."""
        try:
            result = subprocess.run(
                ["ydotool", "type", "--key-delay", str(self._delay_ms), "--", text],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                stderr = result.stderr.decode().strip()
                if "failed to connect" in stderr.lower() or "socket" in stderr.lower():
                    print("[visionflow] ERRO: ydotoold não está rodando.")
                    print("[visionflow] Execute: systemctl --user enable --now ydotool")
                    # Fallback para clipboard
                    self._type_clipboard(text)
                else:
                    print(f"[visionflow] ERRO ydotool: {stderr}")
                    self._type_clipboard(text)
        except FileNotFoundError:
            print("[visionflow] ERRO: ydotool não encontrado.")
            self._type_clipboard(text)
        except subprocess.TimeoutExpired:
            print("[visionflow] ERRO: ydotool timeout.")
        except Exception as e:
            print(f"[visionflow] ERRO ydotool: {e}")
            self._type_clipboard(text)

    def _type_wtype(self, text: str) -> None:
        """Digita usando wtype (requer suporte a virtual-keyboard protocol)."""
        try:
            result = subprocess.run(
                ["wtype", "--delay", str(self._delay_ms), "--", text],
                capture_output=True,
                timeout=30,
            )
            if result.returncode != 0:
                print(f"[visionflow] ERRO wtype: {result.stderr.decode().strip()}")
                self._type_clipboard(text)
        except Exception as e:
            print(f"[visionflow] ERRO wtype: {e}")
            self._type_clipboard(text)

    def _type_clipboard(self, text: str) -> None:
        """Copia para clipboard via wl-copy e simula Ctrl+V.
        
        O wl-copy fica vivo para manter o texto no clipboard,
        permitindo que o usuário cole novamente com Ctrl+V.
        """
        print("[visionflow] Digitando via clipboard + Ctrl+V")
        try:
            if not _has_command("wl-copy"):
                print("[visionflow] ERRO: wl-copy não encontrado. Instale: sudo pacman -S wl-clipboard")
                return

            # Mata o wl-copy anterior (se existir) antes de iniciar novo
            self._kill_prev_wl_copy()

            # wl-copy no Wayland é um "clipboard owner" -- precisa ficar vivo
            # para manter o conteúdo no clipboard. Mantemos vivo até o próximo uso.
            self._wl_copy_proc = subprocess.Popen(
                ["wl-copy", "--", text],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )

            # Espera breve para o clipboard registrar
            time.sleep(0.15)

            # Simula Ctrl+V para colar
            paste_ok = False
            if _has_command("ydotool"):
                result = subprocess.run(
                    ["ydotool", "key", "29:1", "47:1", "47:0", "29:0"],
                    capture_output=True,
                    timeout=10,
                )
                paste_ok = result.returncode == 0
            elif _has_command("wtype"):
                result = subprocess.run(
                    ["wtype", "-M", "ctrl", "-k", "v"],
                    capture_output=True,
                    timeout=10,
                )
                paste_ok = result.returncode == 0

            if not paste_ok:
                print("[visionflow] AVISO: falha ao simular Ctrl+V. Texto está no clipboard, cole manualmente.")

            # NÃO mata o wl-copy — ele fica vivo para o clipboard persistir.
            # Será morto apenas quando um novo texto for copiado.

        except Exception as e:
            print(f"[visionflow] ERRO no clipboard: {e}")

    def _kill_prev_wl_copy(self) -> None:
        """Mata o processo wl-copy anterior, se existir."""
        proc = getattr(self, "_wl_copy_proc", None)
        if proc and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
