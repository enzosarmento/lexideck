"""Módulo de provedores de IA (LLMs) para o LexiDeck."""

from lexideck.providers.base import (
    LLMProvider,
    ProviderAuthError,
    ProviderError,
    ProviderRateLimitError,
    ProviderValidationError,
)

__all__ = [
    "LLMProvider",
    "ProviderAuthError",
    "ProviderError",
    "ProviderRateLimitError",
    "ProviderValidationError",
]
