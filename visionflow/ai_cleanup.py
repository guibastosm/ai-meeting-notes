"""Polimento de texto via Ollama LLM."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from visionflow.config import OllamaConfig


class AICleanup:
    """Usa Ollama para limpar e polir texto transcrito."""

    def __init__(self, config: OllamaConfig | None = None) -> None:
        from visionflow.config import OllamaConfig as OC

        cfg = config or OC()
        self._base_url = cfg.base_url.rstrip("/")
        self._model = cfg.cleanup_model
        self._prompt = cfg.cleanup_prompt

    def cleanup(self, raw_text: str) -> str:
        """Envia texto bruto ao Ollama e retorna texto polido."""
        if not raw_text.strip():
            return ""

        try:
            response = httpx.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": f"{self._prompt}\n\nTexto transcrito:\n{raw_text}",
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 2048,
                    },
                },
                timeout=30.0,
            )
            response.raise_for_status()
            data = response.json()
            cleaned = data.get("response", "").strip()

            if cleaned:
                print(f"[visionflow] IA cleanup: {cleaned[:100]}...")
                return cleaned

            # Fallback: retorna texto original se IA retornar vazio
            return raw_text

        except httpx.ConnectError:
            print("[visionflow] ERRO: Não foi possível conectar ao Ollama. Está rodando?")
            print(f"[visionflow] URL: {self._base_url}")
            return raw_text
        except Exception as e:
            print(f"[visionflow] ERRO no cleanup com IA: {e}")
            return raw_text
