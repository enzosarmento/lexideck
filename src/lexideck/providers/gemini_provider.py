"""Implementação do provedor Google Gemini utilizando o SDK oficial google-genai."""

from __future__ import annotations

import logging
import os
from typing import Any

from pydantic import BaseModel

try:
    from google import genai
    from google.genai import types
    from google.genai.errors import APIError
except ImportError:  # pragma: no cover
    genai = None
    types = None
    APIError = Exception

from lexideck.models import WordCardBatch
from lexideck.providers.base import (
    LLMProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
)

logger = logging.getLogger(__name__)


class GeminiProvider(LLMProvider):
    """Provedor para modelos Google Gemini (ex: gemini-3.8-flash) via SDK google-genai."""

    def __init__(
        self,
        model: str = "gemini-3.8-flash",
        api_key: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        resolved_key = (
            api_key or os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
        )
        if resolved_key:
            resolved_key = resolved_key.strip("'\" \t\r\n")
        super().__init__(
            model=model,
            api_key=resolved_key,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._client: genai.Client | None = None

    @property
    def name(self) -> str:
        return "gemini"

    def _get_client(self) -> genai.Client:
        """Inicializa e retorna o cliente Gemini com validação de credencial."""
        if self._client is None:
            if not self.api_key:
                raise ProviderAuthError(
                    "Chave GEMINI_API_KEY (ou GOOGLE_API_KEY) não encontrada. "
                    "Configure-a no arquivo .env ou defina a variável de ambiente."
                )
            if genai is None:
                raise ProviderError(
                    "Pacote 'google-genai' não está instalado no ambiente."
                )
            self._client = genai.Client(api_key=self.api_key)
        return self._client

    def generate(
        self, prompt: str, schema: type[BaseModel] | None = None
    ) -> dict[str, Any] | list[Any] | str:
        """Executa a geração de conteúdo no Gemini com modo de resposta JSON estruturada."""
        client = self._get_client()

        target_schema = schema or WordCardBatch
        system_instruction = (
            "Você é um especialista em linguística e ensino de inglês para falantes de português do Brasil. "
            "Sua resposta deve ser estritamente em formato JSON válido, de acordo com o schema solicitado, "
            "sem texto conversacional fora do JSON."
        )

        logger.debug(
            "[%s] Enviando requisição para modelo %s com schema %s",
            self.name,
            self.model,
            target_schema,
        )

        try:
            config = types.GenerateContentConfig(
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=target_schema,
                temperature=0.2,
            )

            response = client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=config,
            )

            text = response.text
            if not text:
                raise ProviderError("Resposta vazia retornada pelo modelo Gemini.")

            return text
        except APIError as api_err:
            err_str = str(api_err).lower()
            if (
                "401" in err_str
                or "403" in err_str
                or "api_key" in err_str
                or "unauthenticated" in err_str
            ):
                raise ProviderAuthError(
                    f"Erro de autenticação na API do Gemini: {api_err}"
                ) from api_err
            if (
                "429" in err_str
                or "quota" in err_str
                or "resource_exhausted" in err_str
            ):
                raise ProviderRateLimitError(
                    f"Limite de cota ou requisições (429) no Gemini atingido: {api_err}"
                ) from api_err
            raise ProviderError(f"Erro na API do Google Gemini: {api_err}") from api_err
        except Exception as exc:
            err_str = str(exc).lower()
            if "api_key" in err_str or "unauthenticated" in err_str:
                raise ProviderAuthError(
                    f"Falha de credencial do Gemini: {exc}"
                ) from exc
            if "429" in err_str or "resource_exhausted" in err_str:
                raise ProviderRateLimitError(
                    f"Rate limit do Gemini atingido: {exc}"
                ) from exc
            raise ProviderError(f"Erro inesperado no GeminiProvider: {exc}") from exc
