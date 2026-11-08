"""Testes unitários para o leitor e extrator de PDF."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

try:
    import pymupdf as fitz
except ImportError:
    import fitz

from lexideck.pdf_reader import PDFReaderError, extract_text_from_pdf
from scripts.make_sample_pdf import create_sample_pdf


def test_extract_text_from_sample_pdf(tmp_path: Path) -> None:
    sample_pdf = tmp_path / "test_sample.pdf"
    create_sample_pdf(sample_pdf)

    doc = extract_text_from_pdf(sample_pdf, filter_language=True)

    assert doc.total_pages == 2
    assert len(doc.pages) == 2
    assert doc.empty_pages == []

    # O cabeçalho repetido deve ter sido removido
    assert "LexiDeck Automated Test Document - Running Header" not in doc.full_text

    # A hifenização de quebra de linha ("exam-\nple") deve ter sido unificada
    assert "example" in doc.full_text

    # O parágrafo em português na página 2 deve ter sido filtrado
    assert (
        "Este parágrafo foi escrito intencionalmente em português" not in doc.full_text
    )

    # Conteúdo em inglês deve estar presente
    assert "quick brown fox" in doc.full_text
    assert "Although many people consider prepositions" in doc.full_text


def test_extract_text_with_empty_or_scanned_page(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    pdf_path = tmp_path / "scanned_page.pdf"
    doc = fitz.open()

    # Página 1 com texto normal
    page1 = doc.new_page(width=595, height=842)
    page1.insert_text((50, 72), "Valid English content on the first page.", fontsize=11)

    # Página 2 sem texto (simulando imagem/escaneado)
    doc.new_page(width=595, height=842)

    doc.save(pdf_path)
    doc.close()

    with caplog.at_level(logging.WARNING):
        extracted = extract_text_from_pdf(pdf_path)

    assert extracted.total_pages == 2
    assert 2 in extracted.empty_pages
    assert extracted.pages[1].is_empty is True
    assert "Página 2 sem texto detectável" in caplog.text
    assert "Valid English content on the first page." in extracted.full_text


def test_extract_text_with_ocr_fallback(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from unittest.mock import patch

    pdf_path = tmp_path / "scanned_with_ocr.pdf"
    doc = fitz.open()
    doc.new_page(width=595, height=842)  # Página sem texto
    doc.save(pdf_path)
    doc.close()

    mock_ocr_text = "Optical character recognition extracted this vocabulary sentence."

    with (
        patch("pytesseract.image_to_string", return_value=mock_ocr_text),
        caplog.at_level(logging.INFO),
    ):
        extracted = extract_text_from_pdf(pdf_path, ocr_fallback=True)

    assert extracted.total_pages == 1
    assert 1 in extracted.ocr_pages
    assert extracted.empty_pages == []
    assert extracted.pages[0].ocr_applied is True
    assert "Optical character recognition extracted" in extracted.full_text
    assert "OCR (pytesseract) executado com sucesso como fallback" in caplog.text


def test_extract_text_file_not_found(tmp_path: Path) -> None:
    non_existent = tmp_path / "does_not_exist.pdf"
    with pytest.raises(PDFReaderError, match="Arquivo PDF não encontrado"):
        extract_text_from_pdf(non_existent)
