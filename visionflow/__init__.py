"""VisionFlow: Ditado por voz multimodal com IA para Linux."""

from __future__ import annotations

import ctypes
import importlib.util
import os
from pathlib import Path

__version__ = "0.1.0"


def _preload_cuda_libs() -> None:
    """Pré-carrega libs NVIDIA do pip (cublas/cudnn) antes do ctranslate2."""
    lib_dirs: list[str] = []
    for pkg in ("nvidia.cublas.lib", "nvidia.cudnn.lib"):
        spec = importlib.util.find_spec(pkg)
        if spec and spec.submodule_search_locations:
            for p in spec.submodule_search_locations:
                if p not in lib_dirs:
                    lib_dirs.append(p)

    if not lib_dirs:
        return

    # Carrega as .so necessárias via ctypes (ordem importa: cublas antes de cudnn)
    libs_to_load = [
        "libcublas.so.12",
        "libcublasLt.so.12",
        "libcudnn.so.9",
    ]

    for lib_dir in lib_dirs:
        for lib_name in libs_to_load:
            lib_path = Path(lib_dir) / lib_name
            if lib_path.exists():
                try:
                    ctypes.cdll.LoadLibrary(str(lib_path))
                except OSError:
                    pass

    # Também atualiza LD_LIBRARY_PATH para subprocessos futuros
    existing = os.environ.get("LD_LIBRARY_PATH", "")
    new_paths = ":".join(lib_dirs)
    if existing:
        os.environ["LD_LIBRARY_PATH"] = f"{new_paths}:{existing}"
    else:
        os.environ["LD_LIBRARY_PATH"] = new_paths


_preload_cuda_libs()
