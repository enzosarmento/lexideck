"""Implementação do provedor Ollama para execução local de modelos abertos (Llama, Mistral, etc.)."""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.request
from typing import Any

from pydantic import BaseModel

from lexideck.providers.base import LLMProvider, ProviderError

logger = logging.getLogger(__name__)


class OllamaProvider(LLMProvider):
    """Provedor para modelos locais executados via Ollama (ex: llama3.2, mistral)."""

    def __init__(
        self,
        model: str = "llama3.2",
        base_url: str = "http://localhost:11434",
        api_key: str | None = None,
        timeout: int = 60,
        max_retries: int = 2,
    ) -> None:
        resolved_base = (
            os.getenv("OLLAMA_BASE_URL") or base_url or "http://localhost:11434"
        ).rstrip("/")
        super().__init__(
            model=model,
            api_key=api_key or "local-ollama",
            timeout=timeout,
            max_retries=max_retries,
        )
        self.base_url = resolved_base

    @property
    def name(self) -> str:
        return "ollama"

    def generate(
        self, prompt: str, schema: type[BaseModel] | None = None
    ) -> dict[str, Any] | list[Any] | str:
        """Envia requisição para a API local do Ollama com modo JSON ativado."""
        _ = schema
        url = f"{self.base_url}/api/generate"

        payload = {
            "model": self.model,
            "prompt": prompt,
            "format": "json",
            "stream": False,
            "options": {
                "temperature": 0.2,
            },
        }

        data_bytes = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data_bytes,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        logger.debug(
            "[%s] Enviando requisição para %s (modelo: %s)",
            self.name,
            url,
            self.model,
        )

        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                if response.status != 200:
                    raise ProviderError(
                        f"Servidor Ollama retornou status HTTP {response.status}."
                    )
                raw_body = response.read().decode("utf-8")
                parsed = json.loads(raw_body)
                response_text = parsed.get("response", "")
                if not response_text:
                    raise ProviderError("Resposta vazia retornada pelo Ollama.")
                return response_text

        except urllib.error.URLError as url_err:
            raise ProviderError(
                f"Não foi possível conectar ao servidor Ollama em '{self.base_url}'. "
                f"Certifique-se de que o Ollama está rodando localmente (ollama serve). Detalhes: {url_err}"
            ) from url_err
        except Exception as exc:
            raise ProviderError(f"Erro inesperado no OllamaProvider: {exc}") from exc
