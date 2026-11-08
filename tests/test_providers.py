"""Testes unitários para provedores de IA utilizando mocks (sem chamadas reais de API)."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from lexideck.providers.base import (
    LLMProvider,
    ProviderAuthError,
    ProviderValidationError,
)
from lexideck.providers.claude_provider import ClaudeProvider
from lexideck.providers.gemini_provider import GeminiProvider
from lexideck.providers.openai_provider import OpenAIProvider

SAMPLE_CARD_DICT = {
    "word": "the",
    "lemma": "the",
    "pos": "artigo definido",
    "is_function_word": True,
    "ipa": "/ðiː/",
    "translation_pt": ["o", "a", "os", "as"],
    "definition_en": "denoting one or more people or things already mentioned",
    "usage_notes_pt": "Usado antes de substantivos específicos.",
    "examples": [
        {"en": "The sky is blue.", "pt": "O céu é azul."},
        {"en": "The books are here.", "pt": "Os livros estão aqui."},
        {"en": "She plays the piano.", "pt": "Ela toca piano."},
    ],
    "cefr_level": "A1",
}


def test_openai_provider_mock() -> None:
    provider = OpenAIProvider(api_key="sk-mock-key")
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = json.dumps({"cards": [SAMPLE_CARD_DICT]})
    mock_response.choices = [mock_choice]

    with patch.object(provider, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        cards = provider.generate_batch_cards("Analise a palavra the", 1)
        assert len(cards) == 1
        assert cards[0].word == "the"
        assert cards[0].is_function_word is True
        assert len(cards[0].examples) == 3


def test_gemini_provider_mock() -> None:
    provider = GeminiProvider(api_key="gemini-mock-key")
    mock_response = MagicMock()
    mock_response.text = json.dumps({"cards": [SAMPLE_CARD_DICT]})

    with patch.object(provider, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.models.generate_content.return_value = mock_response
        mock_get_client.return_value = mock_client

        cards = provider.generate_batch_cards("Analise a palavra the", 1)
        assert len(cards) == 1
        assert cards[0].word == "the"
        assert cards[0].translation_pt == ["o", "a", "os", "as"]


def test_claude_provider_mock() -> None:
    provider = ClaudeProvider(api_key="claude-mock-key")
    mock_response = MagicMock()
    mock_block = MagicMock()
    mock_block.type = "tool_use"
    mock_block.name = "export_anki_cards"
    mock_block.input = {"cards": [SAMPLE_CARD_DICT]}
    mock_response.content = [mock_block]

    with patch.object(provider, "_get_client") as mock_get_client:
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_get_client.return_value = mock_client

        cards = provider.generate_batch_cards("Analise a palavra the", 1)
        assert len(cards) == 1
        assert cards[0].word == "the"
        assert cards[0].pos == "artigo definido"


def test_provider_auth_error_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    openai_p = OpenAIProvider(api_key=None)
    with pytest.raises(ProviderAuthError):
        openai_p._get_client()

    gemini_p = GeminiProvider(api_key=None)
    with pytest.raises(ProviderAuthError):
        gemini_p._get_client()

    claude_p = ClaudeProvider(api_key=None)
    with pytest.raises(ProviderAuthError):
        claude_p._get_client()


def test_provider_retry_on_validation_failure() -> None:
    class FailingThenSucceedingProvider(LLMProvider):
        def __init__(self) -> None:
            super().__init__(model="mock", api_key="mock", max_retries=3)
            self.calls = 0

        @property
        def name(self) -> str:
            return "mock"

        def generate(self, prompt: str, schema: type | None = None) -> str:
            _ = (prompt, schema)
            self.calls += 1
            if self.calls == 1:
                # Retorna JSON que viola o schema
                return json.dumps({"cards": [{"word": "the"}]})
            return json.dumps({"cards": [SAMPLE_CARD_DICT]})

    p = FailingThenSucceedingProvider()
    cards = p.generate_batch_cards("prompt inicial", 1)
    assert p.calls == 2
    assert len(cards) == 1
    assert cards[0].word == "the"


def test_provider_exhausted_retries_raises_validation_error() -> None:
    class AlwaysFailingProvider(LLMProvider):
        @property
        def name(self) -> str:
            return "failing"

        def generate(self, prompt: str, schema: type | None = None) -> str:
            _ = (prompt, schema)
            return "invalid json {"

    p = AlwaysFailingProvider("mock-model", max_retries=2)
    with pytest.raises(ProviderValidationError):
        p.generate_batch_cards("prompt", 1)


def test_cost_estimation() -> None:
    provider = OpenAIProvider(model="gpt-4o-mini", api_key="mock")
    estimate = provider.estimate_cost(num_words=100, batch_size=25)

    assert estimate["total_words"] == 100.0
    assert estimate["batches_count"] == 4.0
    assert estimate["estimated_input_tokens"] == 15000.0
    assert estimate["estimated_output_tokens"] == 18000.0
    assert estimate["estimated_cost_usd"] > 0.0


def test_ollama_provider_mock() -> None:
    from lexideck.providers.ollama_provider import OllamaProvider

    provider = OllamaProvider(model="llama3.2")
    mock_body = json.dumps(
        {"response": json.dumps({"cards": [SAMPLE_CARD_DICT]})}
    ).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.read.return_value = mock_body
    mock_resp.__enter__.return_value = mock_resp
    mock_resp.__exit__.return_value = None

    with patch("urllib.request.urlopen", return_value=mock_resp):
        cards = provider.generate_batch_cards("Analise a palavra the", 1)
        assert len(cards) == 1
        assert cards[0].word == "the"
        assert provider.estimate_cost(10)["estimated_cost_usd"] == 0.0


def test_ollama_provider_connection_error() -> None:
    import urllib.error

    from lexideck.providers.base import ProviderError
    from lexideck.providers.ollama_provider import OllamaProvider

    provider = OllamaProvider(model="llama3.2")

    with (
        patch(
            "urllib.request.urlopen",
            side_effect=urllib.error.URLError("Connection refused"),
        ),
        pytest.raises(
            ProviderError, match="Não foi possível conectar ao servidor Ollama"
        ),
    ):
        provider.generate("prompt de teste")
