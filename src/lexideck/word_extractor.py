"""Módulo de processamento de linguagem natural (NLP): tokenização, lematização,

frequência e extração de contexto original com spaCy.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field

import spacy
from spacy.language import Language
from spacy.tokens import Doc

logger = logging.getLogger(__name__)

# Cache do modelo spaCy para evitar recargas caras
_NLP_INSTANCE: Language | None = None


def load_spacy_model(model_name: str = "en_core_web_sm") -> Language:
    """Carrega o modelo spaCy em memória com cache singleton."""
    global _NLP_INSTANCE
    if _NLP_INSTANCE is None:
        try:
            _NLP_INSTANCE = spacy.load(model_name)
        except OSError:
            logger.info("Baixando modelo spaCy %s...", model_name)
            from spacy.cli import download

            download(model_name)
            _NLP_INSTANCE = spacy.load(model_name)
    return _NLP_INSTANCE


@dataclass
class ExtractedWord:
    """Representa uma palavra extraída com seus metadados sintáticos e contextuais."""

    word: str  # Chave primária (lema se lematizado, ou forma superficial se não)
    lemma: str  # Lema canônico da palavra
    pos: str  # Classe gramatical simplificada (Universal POS)
    tag: str  # Tag gramatical detalhada (Penn Treebank)
    frequency: int  # Frequência absoluta de ocorrência no PDF
    original_forms: list[str] = field(
        default_factory=list
    )  # Formas superficiais encontradas
    contexts: list[str] = field(default_factory=list)  # 1 a 3 frases reais do PDF
    is_function_word: bool = False  # Marcador de palavra funcional
    is_proper_noun: bool = False  # Marcador de nome próprio
    is_numeral: bool = False  # Marcador de número
    is_acronym: bool = False  # Marcador de sigla


def clean_sentence_text(text: str) -> str:
    """Higieniza o texto de uma frase extraída do PDF para exibição nos cartões."""
    # Substitui múltiplas quebras de linha e múltiplos espaços por um espaço único
    cleaned = re.sub(r"\s+", " ", text).strip()
    return cleaned


def extract_words_from_text(
    text: str,
    lemmatize: bool = True,
    max_contexts: int = 3,
    nlp_model: Language | None = None,
) -> list[ExtractedWord]:
    """Tokeniza o texto, calcula frequências, lematiza e extrai sentenças de contexto.

    Args:
        text: Texto higienizado em inglês.
        lemmatize: Se True, agrupa variantes sob o lema canônico; se False, usa a palavra exata.
        max_contexts: Número máximo de frases reais de contexto a armazenar (1 a 3).
        nlp_model: Instância opcional do modelo spaCy.

    Returns:
        Lista de ExtractedWord ordenada decrescentemente por frequência.
    """
    if not text or not text.strip():
        return []

    nlp = nlp_model or load_spacy_model()
    doc: Doc = nlp(text)

    # Dicionários de agregação indexados pela chave (lema ou texto minúsculo)
    freq_counter: dict[str, int] = defaultdict(int)
    surface_forms: dict[str, set[str]] = defaultdict(set)
    pos_tags: dict[str, list[str]] = defaultdict(list)
    detailed_tags: dict[str, list[str]] = defaultdict(list)
    lemmas_map: dict[str, str] = {}
    contexts_map: dict[str, list[str]] = defaultdict(list)

    for sent in doc.sents:
        sent_clean = clean_sentence_text(sent.text)
        if not sent_clean:
            continue

        for token in sent:
            # Ignora pontuações, espaços, símbolos e quebras
            if token.is_punct or token.is_space or token.is_bracket or token.like_url:
                continue

            raw_word = token.text.strip()
            if not raw_word or len(raw_word) < 1:
                continue

            # Se for apenas caracteres não-alfabéticos / pontuação restante
            if not any(c.isalnum() for c in raw_word):
                continue

            token_lemma = token.lemma_.strip().lower()
            token_lower = raw_word.lower()

            # Define a chave de agregação
            key = token_lemma if lemmatize else token_lower

            # Atualiza frequências e formas encontradas
            freq_counter[key] += 1
            surface_forms[key].add(raw_word)
            pos_tags[key].append(token.pos_)
            detailed_tags[key].append(token.tag_)
            lemmas_map[key] = token_lemma

            # Armazena sentenças únicas de contexto onde a palavra aparece
            current_contexts = contexts_map[key]
            if (
                len(current_contexts) < max_contexts
                and sent_clean not in current_contexts
            ):
                current_contexts.append(sent_clean)

    extracted_words: list[ExtractedWord] = []

    for key, count in freq_counter.items():
        # Determina a classe gramatical predominante
        all_pos = pos_tags[key]
        predominant_pos = max(set(all_pos), key=all_pos.count)

        all_tags = detailed_tags[key]
        predominant_tag = max(set(all_tags), key=all_tags.count)

        sorted_surfaces = sorted(surface_forms[key], key=lambda s: len(s), reverse=True)

        extracted_words.append(
            ExtractedWord(
                word=key,
                lemma=lemmas_map[key],
                pos=predominant_pos,
                tag=predominant_tag,
                frequency=count,
                original_forms=sorted_surfaces,
                contexts=contexts_map[key],
            )
        )

    # Ordena decrescentemente por frequência
    extracted_words.sort(key=lambda item: item.frequency, reverse=True)
    return extracted_words
