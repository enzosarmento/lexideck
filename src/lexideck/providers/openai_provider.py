"""Implementação do provedor OpenAI utilizando o SDK oficial."""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import BaseModel

try:
    from openai import (
        APIConnectionError,
        APIStatusError,
        AuthenticationError,
        OpenAI,
        RateLimitError,
    )
except ImportError:  # pragma: no cover
    OpenAI = None
    AuthenticationError = Exception
    RateLimitError = Exception
    APIStatusError = Exception
    APIConnectionError = Exception

from lexideck.providers.base import (
    LLMProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
)

logger = logging.getLogger(__name__)


class OpenAIProvider(LLMProvider):
    """Provedor para modelos OpenAI (ex: gpt-4o-mini, gpt-4o) via SDK oficial."""

    def __init__(
        self,
        model: str = "gpt-4o-mini",
        api_key: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        resolved_key = api_key or os.getenv("OPENAI_API_KEY")
        super().__init__(
            model=model,
            api_key=resolved_key,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._client: OpenAI | None = None

    @property
    def name(self) -> str:
        return "openai"

    def _get_client(self) -> OpenAI:
        """Inicializa e retorna o cliente OpenAI com validação de credencial."""
        if self._client is None:
            if not self.api_key:
                raise ProviderAuthError(
                    "Chave OPENAI_API_KEY não encontrada. "
                    "Configure-a no arquivo .env ou defina a variável de ambiente."
                )
            if OpenAI is None:
                raise ProviderError("Pacote 'openai' não está instalado no ambiente.")
            self._client = OpenAI(api_key=self.api_key, timeout=self.timeout)
        return self._client

    def generate(
        self, prompt: str, schema: type[BaseModel] | None = None
    ) -> dict[str, Any] | list[Any] | str:
        """Executa a requisição de chat completion no modo JSON da OpenAI."""
        client = self._get_client()
        logger.debug(
            "[%s] Executando chamada para modelo %s com schema %s",
            self.name,
            self.model,
            schema,
        )

        system_instruction = (
            "Você é um especialista em linguística e ensino de inglês para falantes de português do Brasil. "
            "Sua resposta deve ser estritamente em formato JSON válido, de acordo com o schema solicitado, "
            "sem blocos de texto ou explicações fora do JSON."
        )

        try:
            response = client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_instruction},
                    {"role": "user", "content": prompt},
                ],
                response_format={"type": "json_object"},
                temperature=0.2,
            )

            content = response.choices[0].message.content
            if not content:
                raise ProviderError("Resposta vazia retornada pelo modelo da OpenAI.")

            return content
        except AuthenticationError as auth_err:
            raise ProviderAuthError(
                f"Erro de autenticação na OpenAI: chave inválida ou revogada. ({auth_err})"
            ) from auth_err
        except RateLimitError as rate_err:
            raise ProviderRateLimitError(
                f"Limite de requisições (Rate Limit 429) na OpenAI atingido: {rate_err}"
            ) from rate_err
        except (APIStatusError, APIConnectionError) as api_err:
            raise ProviderError(
                f"Erro de comunicação com a API da OpenAI: {api_err}"
            ) from api_err
        except Exception as exc:
            raise ProviderError(f"Erro inesperado no OpenAIProvider: {exc}") from exc
