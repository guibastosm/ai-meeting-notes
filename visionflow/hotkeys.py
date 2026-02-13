"""Hotkeys globais via evdev para Wayland."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from typing import Callable

import evdev
from evdev import InputDevice, ecodes

from visionflow.config import HotkeyConfig


def _find_keyboard_devices() -> list[InputDevice]:
    """Encontra todos os dispositivos de teclado disponíveis."""
    devices = []
    for path in sorted(Path("/dev/input/").glob("event*")):
        try:
            dev = InputDevice(str(path))
            caps = dev.capabilities(verbose=False)
            # Verifica se o dispositivo tem teclas de teclado (EV_KEY)
            if ecodes.EV_KEY in caps:
                key_caps = caps[ecodes.EV_KEY]
                # Verifica se tem teclas comuns de teclado (A-Z)
                if ecodes.KEY_A in key_caps and ecodes.KEY_Z in key_caps:
                    devices.append(dev)
                else:
                    dev.close()
            else:
                dev.close()
        except (PermissionError, OSError):
            continue
    return devices


def _key_name_to_code(name: str) -> int:
    """Converte nome de tecla evdev (ex: 'KEY_LEFTCTRL') para código numérico."""
    code = getattr(ecodes, name, None)
    if code is None:
        raise ValueError(f"Tecla desconhecida: {name}. Use nomes evdev como KEY_LEFTCTRL, KEY_A, etc.")
    return code


class HotkeyListener:
    """Escuta hotkeys globais via evdev e dispara callbacks."""

    def __init__(
        self,
        config: HotkeyConfig,
        on_dictation_start: Callable[[], None],
        on_dictation_stop: Callable[[], None],
        on_screenshot_start: Callable[[], None],
        on_screenshot_stop: Callable[[], None],
    ) -> None:
        self._config = config

        # Callbacks
        self._on_dictation_start = on_dictation_start
        self._on_dictation_stop = on_dictation_stop
        self._on_screenshot_start = on_screenshot_start
        self._on_screenshot_stop = on_screenshot_stop

        # Converte nomes para códigos
        self._dictation_keys = {_key_name_to_code(k) for k in config.dictation}
        self._screenshot_keys = {_key_name_to_code(k) for k in config.screenshot_command}

        # Estado
        self._pressed_keys: set[int] = set()
        self._dictation_active = False
        self._screenshot_active = False
        self._dictation_press_time: float = 0
        self._mode = config.mode
        self._hold_threshold = config.hold_threshold_ms / 1000.0

    async def run(self) -> None:
        """Loop principal de escuta de hotkeys."""
        devices = _find_keyboard_devices()
        if not devices:
            print("[visionflow] ERRO: Nenhum teclado encontrado.")
            print("[visionflow] Verifique se seu usuário está no grupo 'input':")
            print("[visionflow]   sudo usermod -aG input $USER")
            print("[visionflow]   (requer logout/login)")
            return

        print(f"[visionflow] Escutando {len(devices)} dispositivo(s) de teclado")
        for dev in devices:
            print(f"[visionflow]   - {dev.name} ({dev.path})")

        dict_names = " + ".join(self._config.dictation)
        screenshot_names = " + ".join(self._config.screenshot_command)
        print(f"[visionflow] Hotkeys: ditado={dict_names}, screenshot={screenshot_names}")
        print(f"[visionflow] Modo: {self._mode}")

        tasks = [asyncio.create_task(self._listen_device(dev)) for dev in devices]
        await asyncio.gather(*tasks)

    async def _listen_device(self, device: InputDevice) -> None:
        """Escuta eventos de um dispositivo específico."""
        try:
            async for event in device.async_read_loop():
                if event.type != ecodes.EV_KEY:
                    continue

                key_event = evdev.categorize(event)
                code = key_event.scancode

                if key_event.keystate == evdev.KeyEvent.key_down:
                    self._pressed_keys.add(code)
                    self._handle_key_down()
                elif key_event.keystate == evdev.KeyEvent.key_up:
                    self._handle_key_up(code)
                    self._pressed_keys.discard(code)

        except (OSError, IOError) as e:
            print(f"[visionflow] Dispositivo desconectado: {device.name} ({e})")

    def _handle_key_down(self) -> None:
        """Processa tecla pressionada."""
        # Verifica combo de ditado
        if self._dictation_keys.issubset(self._pressed_keys):
            if not self._dictation_active and not self._screenshot_active:
                self._dictation_press_time = time.monotonic()

                if self._mode == "hold":
                    self._dictation_active = True
                    self._on_dictation_start()
                elif self._mode == "toggle":
                    # Toggle: start/stop no key_down
                    pass  # Tratado no _handle_dictation_toggle
                elif self._mode == "both":
                    # No modo "both", começa a gravar imediatamente
                    # Se soltar rápido (< threshold), trata como toggle
                    self._dictation_active = True
                    self._on_dictation_start()

        # Verifica combo de screenshot
        if self._screenshot_keys.issubset(self._pressed_keys):
            if not self._screenshot_active and not self._dictation_active:
                self._screenshot_active = True
                self._on_screenshot_start()

    def _handle_key_up(self, released_code: int) -> None:
        """Processa tecla solta."""
        # Screenshot: solta qualquer tecla do combo → para
        if self._screenshot_active and released_code in self._screenshot_keys:
            self._screenshot_active = False
            self._on_screenshot_stop()
            return

        # Ditado: lógica depende do modo
        if released_code in self._dictation_keys:
            if self._mode == "hold" and self._dictation_active:
                self._dictation_active = False
                self._on_dictation_stop()

            elif self._mode == "toggle":
                if not self._dictation_active:
                    self._dictation_active = True
                    self._on_dictation_start()
                else:
                    self._dictation_active = False
                    self._on_dictation_stop()

            elif self._mode == "both" and self._dictation_active:
                elapsed = time.monotonic() - self._dictation_press_time
                if elapsed < self._hold_threshold:
                    # Press curto: modo toggle — mantém gravando, para no próximo press
                    pass  # Continua gravando, será parado no próximo key_down
                else:
                    # Press longo: modo hold — para de gravar
                    self._dictation_active = False
                    self._on_dictation_stop()

    def stop_if_active(self) -> None:
        """Para gravação se estiver ativa (para uso externo no modo toggle)."""
        if self._dictation_active:
            self._dictation_active = False
            self._on_dictation_stop()
