"""Módulo de processamento, limpeza e normalização de texto extraído."""

from __future__ import annotations

import logging
import re
from collections.abc import Sequence

try:
    from langdetect import DetectorFactory, LangDetectException, detect

    # Garante resultados determinísticos na detecção de idioma
    DetectorFactory.seed = 0
except ImportError:  # pragma: no cover
    detect = None
    LangDetectException = Exception

logger = logging.getLogger(__name__)

# Expressão regular para remover quebras de palavras no fim de linha (ex: "exam-\nple" -> "example")
HYPHENATION_REGEX = re.compile(r"(\b[a-zA-Z]+)-\s*\n\s*([a-zA-Z]+)\b")

# Expressão regular para identificar números de página isolados
PAGE_NUMBER_REGEX = re.compile(
    r"^\s*(?:page\s+)?\d+(?:\s*(?:of|/|-)\s*\d+)?\s*$",
    re.IGNORECASE,
)


def clean_hyphenation(text: str) -> str:
    """Remove hifenizações artificiais causadas por quebras de linha em PDFs.

    Exemplo:
        'exam-\\nple' -> 'example'
    """
    if not text:
        return ""
    return HYPHENATION_REGEX.sub(r"\1\2", text)


def is_page_number_line(line: str) -> bool:
    """Verifica se uma linha contém apenas uma indicação ou número de página."""
    return bool(PAGE_NUMBER_REGEX.match(line.strip()))


def remove_repeated_headers_and_footers(
    pages_text: Sequence[str], min_page_ratio: float = 0.5
) -> list[str]:
    """Identifica e remove cabeçalhos e rodapés repetidos entre as páginas do documento.

    Também remove linhas que contenham unicamente numeração de páginas.
    """
    if not pages_text:
        return []

    num_pages = len(pages_text)
    if num_pages < 2:
        # Documento de uma única página: apenas remove numeração explícita
        single_page_lines = [
            line for line in pages_text[0].splitlines() if not is_page_number_line(line)
        ]
        return ["\n".join(single_page_lines)]

    # Analisa linhas potenciais de cabeçalho (início) e rodapé (fim)
    header_candidates: dict[str, int] = {}
    footer_candidates: dict[str, int] = {}

    for page in pages_text:
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        if not lines:
            continue
        # Linha inicial (cabeçalho potencial)
        header_candidates[lines[0]] = header_candidates.get(lines[0], 0) + 1
        # Linha final (rodapé potencial)
        if len(lines) > 1:
            footer_candidates[lines[-1]] = footer_candidates.get(lines[-1], 0) + 1

    min_occurrences = max(2, int(num_pages * min_page_ratio))

    repeated_headers = {
        h for h, count in header_candidates.items() if count >= min_occurrences
    }
    repeated_footers = {
        f for f, count in footer_candidates.items() if count >= min_occurrences
    }

    cleaned_pages: list[str] = []
    for page in pages_text:
        page_lines = page.splitlines()
        filtered_lines: list[str] = []

        for line in page_lines:
            stripped = line.strip()
            if not stripped:
                filtered_lines.append("")
                continue
            if is_page_number_line(stripped):
                continue
            if stripped in repeated_headers or stripped in repeated_footers:
                continue
            filtered_lines.append(line)

        cleaned_pages.append("\n".join(filtered_lines))

    return cleaned_pages


def is_english_text(text: str, default: bool = True) -> bool:
    """Verifica se um determinado trecho de texto está no idioma inglês.

    Trechos muito curtos ou com poucas palavras retornam o valor 'default'
    para evitar falsos negativos em títulos ou legendas.
    """
    cleaned = re.sub(r"[^\w\s]", "", text).strip()
    words = cleaned.split()

    if len(words) < 3 or len(cleaned) < 15:
        return default

    if detect is None:
        return default

    try:
        lang = detect(text)
        return lang == "en"
    except LangDetectException:
        return default


def filter_english_paragraphs(text: str) -> str:
    """Filtra parágrafos de um texto, retendo apenas aqueles em inglês."""
    if not text:
        return ""

    paragraphs = re.split(r"\n\s*\n", text)
    valid_paragraphs: list[str] = []

    for paragraph in paragraphs:
        stripped = paragraph.strip()
        if not stripped:
            continue
        if is_english_text(stripped, default=True):
            valid_paragraphs.append(stripped)
        else:
            logger.info("Trecho em idioma não-inglês ignorado: %s...", stripped[:50])

    return "\n\n".join(valid_paragraphs)
