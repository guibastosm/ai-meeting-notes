"""Configura atalhos de teclado do GNOME para o LocalWhispr."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys


SCHEMA = "org.gnome.settings-daemon.plugins.media-keys"
KEY = "custom-keybindings"
BASE_PATH = "/org/gnome/settings-daemon/plugins/media-keys/custom-keybindings"

# Encontra o binário localwhispr no PATH
VISIONFLOW_BIN = shutil.which("localwhispr")


def _run_gsettings(*args: str) -> str:
    """Executa gsettings e retorna stdout."""
    result = subprocess.run(
        ["gsettings", *args],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def _run_dconf(*args: str) -> str:
    """Executa dconf e retorna stdout."""
    result = subprocess.run(
        ["dconf", *args],
        capture_output=True, text=True
    )
    return result.stdout.strip()


def _get_existing_custom_keybindings() -> list[str]:
    """Retorna lista de paths de keybindings customizados existentes."""
    raw = _run_gsettings("get", SCHEMA, KEY)
    if raw in ("@as []", "[]", ""):
        return []
    # Parse: ['path1', 'path2', ...]
    try:
        return json.loads(raw.replace("'", '"'))
    except json.JSONDecodeError:
        return []


def _find_localwhispr_slots(existing: list[str]) -> dict[str, str]:
    """Encontra slots já usados pelo LocalWhispr."""
    slots = {}
    for path in existing:
        name = _run_dconf("read", f"{path}name")
        if "LocalWhispr" in name:
            cmd = _run_dconf("read", f"{path}command")
            if "dictate" in cmd:
                slots["dictate"] = path
            elif "screenshot" in cmd:
                slots["screenshot"] = path
            elif "meeting" in cmd:
                slots["meeting"] = path
    return slots


def _next_slot_index(existing: list[str]) -> int:
    """Encontra o próximo índice livre para custom keybinding."""
    used = set()
    for path in existing:
        # path like: /org/.../custom0/
        try:
            idx = int(path.rstrip("/").split("custom")[-1])
            used.add(idx)
        except (ValueError, IndexError):
            continue
    i = 0
    while i in used:
        i += 1
    return i


def _write_keybinding(path: str, name: str, command: str, binding: str) -> None:
    """Escreve uma keybinding customizada via dconf."""
    subprocess.run(["dconf", "write", f"{path}name", f"'{name}'"], check=True)
    subprocess.run(["dconf", "write", f"{path}command", f"'{command}'"], check=True)
    subprocess.run(["dconf", "write", f"{path}binding", f"'{binding}'"], check=True)


def setup_gnome_shortcuts(
    dictate_binding: str = "<Ctrl><Shift>d",
    screenshot_binding: str = "<Ctrl><Shift>s",
    meeting_binding: str = "<Ctrl><Shift>m",
) -> None:
    """Registra (ou atualiza) atalhos do GNOME para LocalWhispr."""
    # Verifica se gsettings/dconf estão disponíveis
    if not shutil.which("gsettings") or not shutil.which("dconf"):
        print("[localwhispr] ERRO: gsettings ou dconf não encontrado.")
        print("[localwhispr] Instale com: sudo pacman -S dconf")
        sys.exit(1)

    # Determina o comando base
    if VISIONFLOW_BIN:
        base_cmd = VISIONFLOW_BIN
    else:
        # Fallback: usa o path do venv atual
        import os
        venv = os.environ.get("VIRTUAL_ENV")
        if venv:
            base_cmd = f"{venv}/bin/localwhispr"
        else:
            base_cmd = "localwhispr"

    dictate_cmd = f"{base_cmd} ctl dictate"
    screenshot_cmd = f"{base_cmd} ctl screenshot"
    meeting_cmd = f"{base_cmd} ctl meeting"

    existing = _get_existing_custom_keybindings()
    vf_slots = _find_localwhispr_slots(existing)

    new_paths = list(existing)

    # --- Atalho de ditado ---
    if "dictate" in vf_slots:
        path = vf_slots["dictate"]
        print(f"[localwhispr] Atualizando atalho de ditado em {path}")
    else:
        idx = _next_slot_index(new_paths)
        path = f"{BASE_PATH}/custom{idx}/"
        new_paths.append(path)
        print(f"[localwhispr] Criando atalho de ditado em {path}")

    _write_keybinding(path, "LocalWhispr Ditado", dictate_cmd, dictate_binding)
    print(f"  → {dictate_binding} → {dictate_cmd}")

    # --- Atalho de screenshot ---
    if "screenshot" in vf_slots:
        path = vf_slots["screenshot"]
        print(f"[localwhispr] Atualizando atalho de screenshot em {path}")
    else:
        idx = _next_slot_index(new_paths)
        path = f"{BASE_PATH}/custom{idx}/"
        new_paths.append(path)
        print(f"[localwhispr] Criando atalho de screenshot em {path}")

    _write_keybinding(path, "LocalWhispr Screenshot", screenshot_cmd, screenshot_binding)
    print(f"  → {screenshot_binding} → {screenshot_cmd}")

    # --- Atalho de meeting ---
    if "meeting" in vf_slots:
        path = vf_slots["meeting"]
        print(f"[localwhispr] Atualizando atalho de meeting em {path}")
    else:
        idx = _next_slot_index(new_paths)
        path = f"{BASE_PATH}/custom{idx}/"
        new_paths.append(path)
        print(f"[localwhispr] Criando atalho de meeting em {path}")

    _write_keybinding(path, "LocalWhispr Meeting", meeting_cmd, meeting_binding)
    print(f"  → {meeting_binding} → {meeting_cmd}")

    # --- Atualiza lista de custom keybindings ---
    paths_str = str(new_paths).replace('"', "'")
    subprocess.run(
        ["gsettings", "set", SCHEMA, KEY, paths_str],
        check=True,
    )

    print()
    print("[localwhispr] Atalhos configurados com sucesso!")
    print("[localwhispr] Você pode verificar em: Configurações > Teclado > Atalhos > Atalhos Personalizados")
    print()
    print("  Ditado (toggle):    " + dictate_binding)
    print("  Screenshot + IA:    " + screenshot_binding)
    print("  Reunião (toggle):   " + meeting_binding)
