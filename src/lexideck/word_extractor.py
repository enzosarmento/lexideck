"""Módulo de processamento de linguagem natural (NLP): tokenização, lematização,

frequência, detecção de palavras funcionais, nomes próprios e filtragem.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from dataclasses import dataclass, field

import spacy
from spacy.language import Language
from spacy.tokens import Doc, Token

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


# Mapeamento de classes sintáticas universais para categorias funcionais em português
FUNCTION_POS_MAPPING: dict[str, str] = {
    "DET": "artigo / determinante",
    "ADP": "preposição",
    "CCONJ": "conjunção coordenativa",
    "SCONJ": "conjunção subordinativa",
    "PRON": "pronome",
    "AUX": "verbo auxiliar / modal",
    "PART": "partícula gramatical",
}

# Lista explícita de palavras funcionais clássicas da língua inglesa
KNOWN_FUNCTION_WORDS: set[str] = {
    # Artigos e determinantes
    "the",
    "a",
    "an",
    "this",
    "that",
    "these",
    "those",
    "each",
    "every",
    "either",
    "neither",
    "all",
    "both",
    "few",
    "any",
    "some",
    "no",
    # Preposições
    "of",
    "to",
    "in",
    "for",
    "on",
    "with",
    "at",
    "by",
    "from",
    "up",
    "about",
    "into",
    "over",
    "after",
    "under",
    "above",
    "through",
    "between",
    "before",
    "during",
    "without",
    # Conjunções
    "and",
    "but",
    "or",
    "so",
    "yet",
    "nor",
    "if",
    "because",
    "although",
    "though",
    "while",
    "since",
    "until",
    "unless",
    "as",
    "than",
    # Pronomes
    "it",
    "its",
    "they",
    "them",
    "their",
    "theirs",
    "we",
    "us",
    "our",
    "ours",
    "you",
    "your",
    "yours",
    "he",
    "him",
    "his",
    "she",
    "her",
    "hers",
    "i",
    "me",
    "my",
    "mine",
    "who",
    "whom",
    "whose",
    "which",
    "what",
    # Verbos auxiliares e modais
    "be",
    "is",
    "are",
    "was",
    "were",
    "been",
    "being",
    "have",
    "has",
    "had",
    "do",
    "does",
    "did",
    "can",
    "could",
    "will",
    "would",
    "shall",
    "should",
    "may",
    "might",
    "must",
    # Partículas e advérbios gramaticais
    "not",
    "n't",
}


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
    functional_category_pt: str | None = (
        None  # Descrição da função gramatical em português
    )
    is_proper_noun: bool = False  # Marcador de nome próprio
    is_numeral: bool = False  # Marcador de número
    is_acronym: bool = False  # Marcador de sigla


def clean_sentence_text(text: str) -> str:
    """Higieniza o texto de uma frase extraída do PDF para exibição nos cartões."""
    return re.sub(r"\s+", " ", text).strip()


def is_token_proper_noun(token: Token) -> bool:
    """Determina se o token é um nome próprio."""
    return token.pos_ == "PROPN" or token.tag_ in {"NNP", "NNPS"}


def is_token_acronym(token_text: str) -> bool:
    """Determina se o texto corresponde a uma sigla (letras maiúsculas de 2 a 5 caracteres)."""
    return len(token_text) >= 2 and len(token_text) <= 5 and token_text.isupper()


def is_token_numeral(token: Token, token_text: str) -> bool:
    """Determina se o token representa um número ou numeral."""
    return token.like_num or token.pos_ == "NUM" or token_text.isdigit()


def identify_function_word(
    lemma: str, token_lower: str, pos: str
) -> tuple[bool, str | None]:
    """Identifica se a palavra é funcional e qual sua classe em português."""
    if (
        pos in FUNCTION_POS_MAPPING
        or lemma in KNOWN_FUNCTION_WORDS
        or token_lower in KNOWN_FUNCTION_WORDS
    ):
        category = FUNCTION_POS_MAPPING.get(pos)
        if not category:
            # Fallbacks baseados na palavra
            if lemma in {"the", "a", "an", "this", "that"}:
                category = "artigo / determinante"
            elif lemma in {"of", "to", "in", "for", "on", "at", "by", "with"}:
                category = "preposição"
            elif lemma in {"and", "but", "or", "if", "because", "although"}:
                category = "conjunção"
            elif lemma in {"it", "they", "we", "you", "he", "she", "who"}:
                category = "pronome"
            elif lemma in {"be", "have", "do", "can", "will", "would", "should"}:
                category = "verbo auxiliar / modal"
            else:
                category = "palavra funcional"
        return True, category
    return False, None


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

    freq_counter: dict[str, int] = defaultdict(int)
    surface_forms: dict[str, set[str]] = defaultdict(set)
    pos_tags: dict[str, list[str]] = defaultdict(list)
    detailed_tags: dict[str, list[str]] = defaultdict(list)
    lemmas_map: dict[str, str] = {}
    contexts_map: dict[str, list[str]] = defaultdict(list)

    # Marcadores coletados
    proper_nouns_flags: dict[str, bool] = defaultdict(bool)
    numerals_flags: dict[str, bool] = defaultdict(bool)
    acronyms_flags: dict[str, bool] = defaultdict(bool)

    for sent in doc.sents:
        sent_clean = clean_sentence_text(sent.text)
        if not sent_clean:
            continue

        for token in sent:
            if token.is_punct or token.is_space or token.is_bracket or token.like_url:
                continue

            raw_word = token.text.strip()
            if not raw_word or len(raw_word) < 1:
                continue

            # Se for apenas símbolos não alfanuméricos
            if not any(c.isalnum() for c in raw_word):
                continue

            token_lemma = token.lemma_.strip().lower()
            token_lower = raw_word.lower()

            # Normalização de contrações como "n't" -> "not"
            if token_lemma in {"n't", "not"}:
                token_lemma = "not"

            key = token_lemma if lemmatize else token_lower

            freq_counter[key] += 1
            surface_forms[key].add(raw_word)
            pos_tags[key].append(token.pos_)
            detailed_tags[key].append(token.tag_)
            lemmas_map[key] = token_lemma

            if is_token_proper_noun(token):
                proper_nouns_flags[key] = True

            if is_token_numeral(token, raw_word):
                numerals_flags[key] = True

            if is_token_acronym(raw_word):
                acronyms_flags[key] = True

            current_contexts = contexts_map[key]
            if (
                len(current_contexts) < max_contexts
                and sent_clean not in current_contexts
            ):
                current_contexts.append(sent_clean)

    extracted_words: list[ExtractedWord] = []

    for key, count in freq_counter.items():
        all_pos = pos_tags[key]
        predominant_pos = max(set(all_pos), key=all_pos.count)

        all_tags = detailed_tags[key]
        predominant_tag = max(set(all_tags), key=all_tags.count)

        sorted_surfaces = sorted(surface_forms[key], key=lambda s: len(s), reverse=True)

        is_func, func_cat = identify_function_word(
            lemma=lemmas_map[key],
            token_lower=key.lower(),
            pos=predominant_pos,
        )

        extracted_words.append(
            ExtractedWord(
                word=key,
                lemma=lemmas_map[key],
                pos=predominant_pos,
                tag=predominant_tag,
                frequency=count,
                original_forms=sorted_surfaces,
                contexts=contexts_map[key],
                is_function_word=is_func,
                functional_category_pt=func_cat,
                is_proper_noun=proper_nouns_flags[key],
                is_numeral=numerals_flags[key],
                is_acronym=acronyms_flags[key],
            )
        )

    extracted_words.sort(key=lambda item: item.frequency, reverse=True)
    return extracted_words


def filter_extracted_words(
    words: list[ExtractedWord],
    min_frequency: int = 1,
    include_function_words: bool = True,
    exclude_proper_nouns: bool = True,
    exclude_acronyms: bool = True,
    limit: int | None = None,
) -> list[ExtractedWord]:
    """Aplica as regras de negócio e filtros configuráveis pelo usuário na lista de palavras.

    Args:
        words: Lista de palavras extraídas.
        min_frequency: Frequência mínima para inclusão da palavra no baralho.
        include_function_words: Se True, mantém palavras funcionais com tag especial.
        exclude_proper_nouns: Se True, descarta nomes próprios (ex: John, London).
        exclude_acronyms: Se True, descarta siglas (ex: PDF, API).
        limit: Se informado, limita a saída às N palavras mais frequentes.

    Returns:
        Lista filtrada de ExtractedWord.
    """
    filtered: list[ExtractedWord] = []

    for item in words:
        # Filtro de frequência mínima
        if item.frequency < min_frequency:
            continue

        # Sempre descarta números e caracteres isolados não-palavras
        if item.is_numeral:
            continue
        if len(item.word) == 1 and item.word.lower() not in {"a", "i"}:
            continue

        # Regra de nomes próprios
        if exclude_proper_nouns and item.is_proper_noun:
            continue

        # Regra de siglas
        if exclude_acronyms and item.is_acronym:
            continue

        # Regra de palavras funcionais
        if not include_function_words and item.is_function_word:
            continue

        filtered.append(item)

    if limit is not None and limit > 0:
        filtered = filtered[:limit]

    return filtered
