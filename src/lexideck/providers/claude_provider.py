"""Implementação do provedor Anthropic Claude utilizando o SDK oficial anthropic."""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import BaseModel

try:
    from anthropic import (
        Anthropic,
        APIConnectionError,
        APIStatusError,
        AuthenticationError,
        RateLimitError,
    )
except ImportError:  # pragma: no cover
    Anthropic = None
    AuthenticationError = Exception
    RateLimitError = Exception
    APIStatusError = Exception
    APIConnectionError = Exception

from lexideck.models import WordCardBatch
from lexideck.providers.base import (
    LLMProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
)

logger = logging.getLogger(__name__)


class ClaudeProvider(LLMProvider):
    """Provedor para modelos Anthropic Claude (ex: claude-3-5-haiku-20241022) via SDK anthropic."""

    def __init__(
        self,
        model: str = "claude-3-5-haiku-20241022",
        api_key: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if resolved_key:
            resolved_key = resolved_key.strip("'\" \t\r\n")
        super().__init__(
            model=model,
            api_key=resolved_key,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._client: Anthropic | None = None

    @property
    def name(self) -> str:
        return "claude"

    def _get_client(self) -> Anthropic:
        """Inicializa e retorna o cliente Anthropic com validação de credencial."""
        if self._client is None:
            if not self.api_key:
                raise ProviderAuthError(
                    "Chave ANTHROPIC_API_KEY não encontrada. "
                    "Configure-a no arquivo .env ou defina a variável de ambiente."
                )
            if Anthropic is None:
                raise ProviderError(
                    "Pacote 'anthropic' não está instalado no ambiente."
                )
            self._client = Anthropic(api_key=self.api_key, timeout=self.timeout)
        return self._client

    def generate(
        self, prompt: str, schema: type[BaseModel] | None = None
    ) -> dict[str, Any] | list[Any] | str:
        """Executa a requisição ao Claude utilizando Tool Use garantindo schema estruturado."""
        client = self._get_client()
        target_schema = schema or WordCardBatch

        tool_name = "export_anki_cards"
        tools = [
            {
                "name": tool_name,
                "description": (
                    "Exporta a lista estruturada de cartões de vocabulário e palavras funcionais "
                    "analisadas para o baralho Anki."
                ),
                "input_schema": target_schema.model_json_schema(),
            }
        ]

        logger.debug(
            "[%s] Enviando requisição para modelo %s via tool_use (%s)",
            self.name,
            self.model,
            tool_name,
        )

        try:
            response = client.messages.create(
                model=self.model,
                max_tokens=4096,
                temperature=0.2,
                tools=tools,
                tool_choice={"type": "tool", "name": tool_name},
                messages=[{"role": "user", "content": prompt}],
            )

            # Extrai os dados estruturados do bloco tool_use
            for block in response.content:
                if block.type == "tool_use" and block.name == tool_name:
                    return block.input
                if hasattr(block, "text") and block.text:
                    return block.text

            raise ProviderError(
                "Nenhum bloco de dados utilizável retornado pelo Claude."
            )

        except AuthenticationError as auth_err:
            raise ProviderAuthError(
                f"Erro de autenticação na API da Anthropic: {auth_err}"
            ) from auth_err
        except RateLimitError as rate_err:
            raise ProviderRateLimitError(
                f"Limite de requisições (429) no Claude atingido: {rate_err}"
            ) from rate_err
        except (APIStatusError, APIConnectionError) as api_err:
            raise ProviderError(
                f"Erro de comunicação com a API da Anthropic: {api_err}"
            ) from api_err
        except Exception as exc:
            raise ProviderError(f"Erro inesperado no ClaudeProvider: {exc}") from exc
