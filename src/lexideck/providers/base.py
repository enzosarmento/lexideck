"""Interface base e contratos abstratos para provedores de Modelos de Linguagem (LLMs)."""

from __future__ import annotations

import json
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, ValidationError

from lexideck.models import WordCardBatch, WordCardResponse, parse_and_validate_llm_json

logger = logging.getLogger(__name__)


class ProviderError(Exception):
    """Exceção base para erros em provedores de IA."""


class ProviderAuthError(ProviderError):
    """Exceção levantada quando a autenticação/chave de API é inválida."""


class ProviderRateLimitError(ProviderError):
    """Exceção levantada quando a requisição atinge limite de taxa (HTTP 429)."""


class ProviderValidationError(ProviderError):
    """Exceção levantada quando o conteúdo retornado não atende ao esquema Pydantic."""


# Tabela referencial de custos por milhão de tokens (USD) para estimativa de dry-run
MODEL_PRICING_PER_MILLION: dict[str, tuple[float, float]] = {
    # Provedor OpenAI: (input_cost_per_1M, output_cost_per_1M)
    "gpt-4o-mini": (0.15, 0.60),
    "gpt-4o": (2.50, 10.00),
    # Provedor Gemini
    "gemini-3.8-flash": (0.075, 0.30),
    "gemini-2.5-flash": (0.075, 0.30),
    "gemini-1.5-flash": (0.075, 0.30),
    "gemini-1.5-pro": (1.25, 5.00),
    # Provedor Claude
    "claude-3-5-haiku-20241022": (0.80, 4.00),
    "claude-3-5-sonnet-20241022": (3.00, 15.00),
    # Ollama / modelos locais
    "llama3.2": (0.0, 0.0),
    "ollama": (0.0, 0.0),
}


class LLMProvider(ABC):
    """Classe base abstrata para todos os provedores de IA do LexiDeck."""

    def __init__(
        self,
        model: str,
        api_key: str | None = None,
        timeout: int = 30,
        max_retries: int = 3,
    ) -> None:
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.max_retries = max_retries

    @property
    @abstractmethod
    def name(self) -> str:
        """Nome identificador do provedor (ex: 'openai', 'gemini', 'claude')."""

    @abstractmethod
    def generate(
        self, prompt: str, schema: type[BaseModel] | None = None
    ) -> dict[str, Any] | list[Any] | str:
        """Envia um prompt ao provedor de IA e retorna o payload cru ou decodificado."""

    def generate_batch_cards(
        self, prompt: str, words_in_batch: int
    ) -> list[WordCardResponse]:
        """Orquestra a chamada de geração em lote, incluindo validação Pydantic e tentativas de correção."""
        current_prompt = prompt
        last_error: Exception | None = None

        for attempt in range(1, self.max_retries + 1):
            try:
                logger.debug(
                    "[%s] Tentativa %d/%d para lote de %d palavras...",
                    self.name,
                    attempt,
                    self.max_retries,
                    words_in_batch,
                )
                raw_response = self._execute_with_retry(current_prompt)
                batch = parse_and_validate_llm_json(raw_response)
                return batch.cards
            except (ValidationError, ValueError, json.JSONDecodeError) as val_err:
                last_error = val_err
                logger.warning(
                    "[%s] Resposta da IA com schema inválido (tentativa %d/%d): %s",
                    self.name,
                    attempt,
                    self.max_retries,
                    val_err,
                )
                if attempt < self.max_retries:
                    # Prompt de correção retroalimentado com a mensagem de erro
                    current_prompt = (
                        f"{prompt}\n\n"
                        f"[AVISO DE CORREÇÃO]: Sua resposta anterior falhou na validação de formato com o erro:\n"
                        f"{val_err}\n"
                        f"Por favor, retorne estritamente o JSON válido correspondente ao schema solicitado."
                    )
                    time.sleep(1.0 * attempt)

        raise ProviderValidationError(
            f"Falha ao validar resposta da IA após {self.max_retries} tentativas: {last_error}"
        ) from last_error

    def _execute_with_retry(self, prompt: str) -> dict[str, Any] | list[Any] | str:
        """Executa a chamada 'generate' com backoff exponencial para erros transitórios (429, 500, timeouts)."""
        backoff = 2.0
        for attempt in range(1, self.max_retries + 1):
            try:
                return self.generate(prompt, schema=WordCardBatch)
            except ProviderRateLimitError as rate_err:
                logger.warning(
                    "[%s] Rate limit atingido (429). Aguardando %.1fs antes de tentar novamente...",
                    self.name,
                    backoff,
                )
                if attempt == self.max_retries:
                    raise rate_err
                time.sleep(backoff)
                backoff *= 2.0
            except ProviderAuthError:
                raise
            except Exception as exc:
                err_msg = str(exc).lower()
                is_rate_limit = (
                    "429" in err_msg or "rate limit" in err_msg or "quota" in err_msg
                )
                is_transient = (
                    "500" in err_msg
                    or "503" in err_msg
                    or "timeout" in err_msg
                    or "overloaded" in err_msg
                )

                if is_rate_limit:
                    if attempt == self.max_retries:
                        raise ProviderRateLimitError(
                            f"Rate limit persistente: {exc}"
                        ) from exc
                    logger.warning(
                        "[%s] Rate limit detectado. Aguardando %.1fs...",
                        self.name,
                        backoff,
                    )
                    time.sleep(backoff)
                    backoff *= 2.0
                elif is_transient and attempt < self.max_retries:
                    logger.warning(
                        "[%s] Erro temporário (%s). Retentando em %.1fs...",
                        self.name,
                        exc,
                        backoff,
                    )
                    time.sleep(backoff)
                    backoff *= 1.5
                else:
                    raise ProviderError(
                        f"Erro na chamada do provedor {self.name}: {exc}"
                    ) from exc

        raise ProviderError(f"Excedido número máximo de tentativas em {self.name}.")

    def estimate_cost(self, num_words: int, batch_size: int = 30) -> dict[str, float]:
        """Calcula a estimativa de tokens de entrada/saída e o custo financeiro aproximado (USD).

        Baseado em médias típicas do LexiDeck:
        - ~150 tokens de prompt por palavra (instruções do sistema + contexto do PDF)
        - ~180 tokens de saída por palavra (tradução, IPA, notas de uso, 3 exemplos com tradução)
        """
        prompt_tokens_per_word = 150
        output_tokens_per_word = 180

        total_input_tokens = num_words * prompt_tokens_per_word
        total_output_tokens = num_words * output_tokens_per_word
        total_tokens = total_input_tokens + total_output_tokens

        # Localiza o preço correspondente ao modelo ou adota custo padrão econômico
        input_price_1m, output_price_1m = MODEL_PRICING_PER_MILLION.get(
            self.model, (0.50, 1.50)
        )

        estimated_cost_usd = (total_input_tokens / 1_000_000) * input_price_1m + (
            total_output_tokens / 1_000_000
        ) * output_price_1m

        return {
            "total_words": float(num_words),
            "batches_count": float(max(1, (num_words + batch_size - 1) // batch_size)),
            "estimated_input_tokens": float(total_input_tokens),
            "estimated_output_tokens": float(total_output_tokens),
            "estimated_total_tokens": float(total_tokens),
            "estimated_cost_usd": round(estimated_cost_usd, 4),
        }
