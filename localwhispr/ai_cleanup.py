"""Polimento de texto via Ollama LLM."""

from __future__ import annotations

from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from localwhispr.config import OllamaConfig


class AICleanup:
    """Usa Ollama para limpar e polir texto transcrito."""

    def __init__(self, config: OllamaConfig | None = None) -> None:
        from localwhispr.config import OllamaConfig as OC

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
                print(f"[localwhispr] IA cleanup: {cleaned[:100]}...")
                return cleaned

            # Fallback: retorna texto original se IA retornar vazio
            return raw_text

        except httpx.ConnectError:
            print("[localwhispr] ERRO: Não foi possível conectar ao Ollama. Está rodando?")
            print(f"[localwhispr] URL: {self._base_url}")
            return raw_text
        except Exception as e:
            print(f"[localwhispr] ERRO no cleanup com IA: {e}")
            return raw_text

    _CONVERSATION_PROMPT = (
        "Você é um assistente de polimento de transcrições de conversa.\n"
        "O texto contém labels [Eu] e [Outro] indicando quem falou.\n"
        "Regras:\n"
        "- MANTENHA os labels [Eu] e [Outro] exatamente como estão\n"
        "- Remova hesitações (uh, hmm, eh, tipo, né, então, assim)\n"
        "- Adicione pontuação correta\n"
        "- Corrija erros óbvios de transcrição\n"
        "- Mantenha o significado original intacto\n"
        "- Responda SOMENTE com o texto limpo, sem explicações ou prefácios."
    )

    def cleanup_conversation(self, labeled_text: str) -> str:
        """Polir conversa com labels [Eu]/[Outro], mantendo os labels."""
        if not labeled_text.strip():
            return ""

        try:
            response = httpx.post(
                f"{self._base_url}/api/generate",
                json={
                    "model": self._model,
                    "prompt": f"{self._CONVERSATION_PROMPT}\n\nTranscrição:\n{labeled_text}",
                    "stream": False,
                    "options": {
                        "temperature": 0.1,
                        "num_predict": 4096,
                    },
                },
                timeout=45.0,
            )
            response.raise_for_status()
            data = response.json()
            cleaned = data.get("response", "").strip()

            if cleaned:
                print(f"[localwhispr] IA cleanup conversa: {cleaned[:100]}...")
                return cleaned

            return labeled_text

        except httpx.ConnectError:
            print("[localwhispr] ERRO: Não foi possível conectar ao Ollama.")
            return labeled_text
        except Exception as e:
            print(f"[localwhispr] ERRO no cleanup conversa: {e}")
            return labeled_text
