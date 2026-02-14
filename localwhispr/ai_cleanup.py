"""Text polishing via Ollama LLM."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from localwhispr.config import OllamaConfig


class AICleanup:
    """Uses Ollama to clean and polish transcribed text."""

    def __init__(self, config: OllamaConfig | None = None) -> None:
        from localwhispr.config import OllamaConfig as OC

        cfg = config or OC()
        self._base_url = cfg.base_url.rstrip("/")
        self._model = cfg.cleanup_model
        self._prompt = cfg.cleanup_prompt

    def cleanup(self, raw_text: str) -> str:
        """Send raw text to Ollama and return polished text."""
        if not raw_text.strip():
            return ""

        try:
            response = httpx.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": f"{self._prompt}\n\nTranscribed text:\n{raw_text}",
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
                print(f"[localwhispr] AI cleanup: {cleaned[:100]}...")
                return cleaned

            # Fallback: return original text if AI returns empty
            return raw_text

        except httpx.ConnectError:
            print("[localwhispr] ERROR: Could not connect to Ollama. Is it running?")
            print(f"[localwhispr] URL: {self._base_url}")
            return raw_text
        except Exception as e:
            print(f"[localwhispr] ERROR in AI cleanup: {e}")
            return raw_text

