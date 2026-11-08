"""Modelos de dados e esquemas de validação Pydantic para os cartões gerados por IA."""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class CEFRLevel(str, Enum):
    """Níveis de proficiência do Quadro Comum Europeu de Referência (CEFR)."""

    A1 = "A1"
    A2 = "A2"
    B1 = "B1"
    B2 = "B2"
    C1 = "C1"
    C2 = "C2"


class ExampleSentence(BaseModel):
    """Par de frase de exemplo em inglês e sua respectiva tradução em português."""

    en: str = Field(..., description="Frase de exemplo natural em inglês")
    pt: str = Field(..., description="Tradução fiel e fluente em português")

    @field_validator("en", "pt")
    @classmethod
    def strip_whitespace(cls, value: str) -> str:
        return value.strip()


class WordCardResponse(BaseModel):
    """Estrutura estrita de dados gerada pela IA para cada palavra do baralho."""

    word: str = Field(..., description="Palavra analisada")
    lemma: str = Field(..., description="Lema canônico da palavra")
    pos: str = Field(
        ...,
        description="Classe gramatical (ex: substantivo, verbo, adjetivo, preposição)",
    )
    is_function_word: bool = Field(
        default=False,
        description="Se a palavra é uma palavra funcional/stop word (ex: the, of, that)",
    )
    ipa: str = Field(..., description="Pronúncia fonética no padrão IPA")
    translation_pt: list[str] = Field(
        ...,
        min_length=1,
        description="Lista de traduções principais em português do Brasil",
    )
    definition_en: str = Field(
        ...,
        description="Definição curta e direta em inglês simples",
    )
    usage_notes_pt: str = Field(
        ...,
        description="Explicações de uso em português; para palavras funcionais, descreve onde e quando é usada, posições típicas e erros comuns de brasileiros",
    )
    examples: list[ExampleSentence] = Field(
        ...,
        min_length=1,
        description="Lista de frases de exemplo com tradução (2 a 3 exemplos; 3 para palavras funcionais)",
    )
    cefr_level: CEFRLevel = Field(
        default=CEFRLevel.B1,
        description="Nível CEFR estimado (A1, A2, B1, B2, C1, C2)",
    )

    # Campos complementares preenchidos a partir da análise do documento
    original_sentence: str | None = Field(
        default=None,
        description="Frase real de contexto extraída diretamente do PDF original",
    )
    frequency: int = Field(
        default=1,
        description="Frequência de ocorrência identificada no documento",
    )

    @field_validator("cefr_level", mode="before")
    @classmethod
    def normalize_cefr_level(cls, value: Any) -> CEFRLevel:
        if isinstance(value, str):
            clean = value.strip().upper()
            try:
                return CEFRLevel(clean)
            except ValueError:
                return CEFRLevel.B1
        return CEFRLevel.B1

    @field_validator("translation_pt", mode="before")
    @classmethod
    def ensure_translation_list(cls, value: Any) -> list[str]:
        if isinstance(value, str):
            return [t.strip() for t in value.split(",") if t.strip()]
        if isinstance(value, list):
            return [str(t).strip() for t in value if str(t).strip()]
        return ["tradução não disponível"]


class WordCardBatch(BaseModel):
    """Lote de múltiplos cartões retornados em uma única requisição à IA."""

    cards: list[WordCardResponse] = Field(
        default_factory=list,
        description="Lista contendo as análises estruturadas de cada palavra do lote",
    )


def parse_and_validate_llm_json(raw_data: str | dict[str, Any]) -> WordCardBatch:
    """Valida e converte uma resposta crua de LLM (string JSON ou dict) em um WordCardBatch.

    Lida automaticamente com respostas que vêm diretamente como lista de objetos
    ou aninhadas sob a chave 'cards' / 'words'.
    """
    if isinstance(raw_data, str):
        cleaned = raw_data.strip()
        # Remove eventuais blocos de código markdown ```json ... ```
        if cleaned.startswith("```"):
            cleaned = re_clean_markdown(cleaned)
        parsed = json.loads(cleaned)
    else:
        parsed = raw_data

    if isinstance(parsed, list):
        return WordCardBatch(
            cards=[WordCardResponse.model_validate(item) for item in parsed]
        )

    if isinstance(parsed, dict):
        if "cards" in parsed and isinstance(parsed["cards"], list):
            return WordCardBatch.model_validate(parsed)
        if "words" in parsed and isinstance(parsed["words"], list):
            return WordCardBatch(
                cards=[
                    WordCardResponse.model_validate(item) for item in parsed["words"]
                ]
            )
        # Se for um único cartão isolado
        if "word" in parsed:
            return WordCardBatch(cards=[WordCardResponse.model_validate(parsed)])

    raise ValueError(
        "Formato de resposta inesperado da IA: não contém lista nem chave 'cards'."
    )


def re_clean_markdown(text: str) -> str:
    """Remove delimitadores markdown ```json ou ``` de uma string."""
    lines = text.strip().splitlines()
    if lines and lines[0].startswith("```"):
        lines = lines[1:]
    if lines and lines[-1].startswith("```"):
        lines = lines[:-1]
    return "\n".join(lines).strip()
