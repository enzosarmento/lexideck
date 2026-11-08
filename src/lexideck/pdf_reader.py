"""Módulo para leitura e extração de texto de arquivos PDF usando PyMuPDF com fallback OCR."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # pragma: no cover
    try:
        import fitz
    except ImportError:  # pragma: no cover
        fitz = None

try:
    import pytesseract
    from PIL import Image
except ImportError:  # pragma: no cover
    Image = None
    pytesseract = None

from lexideck.text_processor import (
    clean_hyphenation,
    filter_english_paragraphs,
    remove_repeated_headers_and_footers,
)

logger = logging.getLogger(__name__)


@dataclass
class PageContent:
    """Representa o conteúdo extraído de uma única página do PDF."""

    page_number: int  # 1-indexed
    raw_text: str
    cleaned_text: str
    is_empty: bool = False
    ocr_applied: bool = False


@dataclass
class ExtractedDocument:
    """Representa o documento completo processado."""

    file_path: Path
    total_pages: int
    pages: list[PageContent] = field(default_factory=list)
    empty_pages: list[int] = field(default_factory=list)
    ocr_pages: list[int] = field(default_factory=list)
    full_text: str = ""


class PDFReaderError(Exception):
    """Exceção levantada quando ocorre um erro ao processar o arquivo PDF."""


def _perform_ocr_on_page(page: fitz.Page, page_num: int) -> str:
    """Executa OCR (reconhecimento óptico de caracteres) em uma página usando PyMuPDF + pytesseract."""
    if pytesseract is None or Image is None:
        logger.warning(
            "Página %d sem texto, mas as bibliotecas pytesseract/Pillow não estão instaladas. Pulando OCR.",
            page_num,
        )
        return ""

    try:
        # Renderiza a página como imagem em memória com 150 DPI
        pix = page.get_pixmap(dpi=150)
        img = Image.frombytes("RGB", (pix.width, pix.height), pix.samples)

        # Executa extração OCR com pytesseract
        ocr_text = pytesseract.image_to_string(img, lang="eng")
        cleaned_ocr = ocr_text.strip()

        if cleaned_ocr:
            logger.info(
                "Página %d sem texto selecionável. OCR (pytesseract) executado com sucesso como fallback.",
                page_num,
            )
            return cleaned_ocr

        logger.warning(
            "Página %d: OCR executado, mas nenhum texto legível foi identificado.",
            page_num,
        )
        return ""
    except Exception as exc:
        logger.warning(
            "Página %d: Falha ao executar OCR via pytesseract (%s). Pulando página.",
            page_num,
            exc,
        )
        return ""


def extract_text_from_pdf(
    pdf_path: str | Path,
    filter_language: bool = True,
    ocr_fallback: bool = False,
) -> ExtractedDocument:
    """Extrai e limpa o texto selecionável de um arquivo PDF com suporte a fallback OCR.

    Args:
        pdf_path: Caminho para o arquivo PDF.
        filter_language: Se verdadeiro, remove parágrafos que não estejam em inglês.
        ocr_fallback: Flag para habilitar fallback via OCR em páginas escaneadas/sem texto.

    Returns:
        ExtractedDocument contendo as páginas processadas, histórico de OCR e o texto unificado.

    Raises:
        PDFReaderError: Se o arquivo não existir ou não for um PDF legível.
    """
    path = Path(pdf_path)
    if not path.exists():
        raise PDFReaderError(f"Arquivo PDF não encontrado: {path}")

    if fitz is None:
        raise PDFReaderError(
            "Biblioteca PyMuPDF (fitz) não está instalada no ambiente."
        )

    try:
        doc = fitz.open(path)
    except Exception as exc:
        raise PDFReaderError(f"Erro ao abrir arquivo PDF {path}: {exc}") from exc

    total_pages = len(doc)
    raw_pages_text: list[str] = []
    empty_page_indices: list[int] = []
    ocr_page_indices: list[int] = []

    for index in range(total_pages):
        page_num = index + 1
        page = doc[index]
        text = page.get_text("text")

        if not text or not text.strip():
            if ocr_fallback:
                ocr_result = _perform_ocr_on_page(page, page_num)
                if ocr_result:
                    raw_pages_text.append(ocr_result)
                    ocr_page_indices.append(page_num)
                else:
                    empty_page_indices.append(page_num)
                    raw_pages_text.append("")
            else:
                empty_page_indices.append(page_num)
                logger.warning(
                    "Página %d sem texto detectável (provável página escaneada). Pulando página.",
                    page_num,
                )
                raw_pages_text.append("")
        else:
            raw_pages_text.append(text)

    doc.close()

    # Etapa 1 de limpeza: remoção de cabeçalhos/rodapés repetidos e números de página
    pages_without_headers = remove_repeated_headers_and_footers(raw_pages_text)

    pages: list[PageContent] = []
    processed_page_texts: list[str] = []

    for index, cleaned_page in enumerate(pages_without_headers):
        page_num = index + 1
        is_empty = page_num in empty_page_indices
        ocr_applied = page_num in ocr_page_indices

        if is_empty:
            pages.append(
                PageContent(
                    page_number=page_num,
                    raw_text=raw_pages_text[index],
                    cleaned_text="",
                    is_empty=True,
                    ocr_applied=False,
                )
            )
            continue

        # Etapa 2 de limpeza: unificação de quebras de linha hifenizadas
        dehyphenated = clean_hyphenation(cleaned_page)

        # Etapa 3 de limpeza: filtragem de parágrafos em outros idiomas
        if filter_language:
            final_text = filter_english_paragraphs(dehyphenated)
        else:
            final_text = dehyphenated

        pages.append(
            PageContent(
                page_number=page_num,
                raw_text=raw_pages_text[index],
                cleaned_text=final_text,
                is_empty=False,
                ocr_applied=ocr_applied,
            )
        )

        if final_text.strip():
            processed_page_texts.append(final_text.strip())

    full_document_text = "\n\n".join(processed_page_texts)

    return ExtractedDocument(
        file_path=path,
        total_pages=total_pages,
        pages=pages,
        empty_pages=empty_page_indices,
        ocr_pages=ocr_page_indices,
        full_text=full_document_text,
    )
