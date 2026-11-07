"""Testes unitários para o processador e higienizador de texto."""

from __future__ import annotations

from lexideck.text_processor import (
    clean_hyphenation,
    filter_english_paragraphs,
    is_english_text,
    is_page_number_line,
    remove_repeated_headers_and_footers,
)


def test_clean_hyphenation() -> None:
    # Hifenização quebrada por quebra de linha
    assert clean_hyphenation("exam-\nple") == "example"
    assert clean_hyphenation("infor-\n  mation") == "information"
    assert clean_hyphenation("inter-\n\tacting") == "interacting"

    # Palavras hifenizadas normais no meio da frase devem ser preservadas
    assert clean_hyphenation("state-of-the-art model") == "state-of-the-art model"
    assert clean_hyphenation("well-known concept") == "well-known concept"

    # Casos de borda
    assert clean_hyphenation("") == ""
    assert (
        clean_hyphenation("normal text without hyphens")
        == "normal text without hyphens"
    )


def test_is_page_number_line() -> None:
    assert is_page_number_line("Page 1") is True
    assert is_page_number_line("page 12 of 30") is True
    assert is_page_number_line("4 / 10") is True
    assert is_page_number_line("42") is True
    assert is_page_number_line("  100  ") is True

    # Linhas de texto real não devem ser tratadas como número de página
    assert is_page_number_line("Chapter 1: The Beginning") is False
    assert is_page_number_line("In 1999, things changed.") is False


def test_remove_repeated_headers_and_footers() -> None:
    pages = [
        "Header Title\nActual content of first page.\nFooter Note\nPage 1",
        "Header Title\nActual content of second page.\nFooter Note\nPage 2",
        "Header Title\nActual content of third page.\nFooter Note\nPage 3",
    ]

    cleaned = remove_repeated_headers_and_footers(pages, min_page_ratio=0.5)
    assert len(cleaned) == 3

    for page_text in cleaned:
        assert "Header Title" not in page_text
        assert "Footer Note" not in page_text
        assert "Page 1" not in page_text
        assert "Page 2" not in page_text
        assert "Page 3" not in page_text

    assert "Actual content of first page." in cleaned[0]
    assert "Actual content of second page." in cleaned[1]
    assert "Actual content of third page." in cleaned[2]


def test_remove_headers_single_page() -> None:
    pages = ["Page 1\nSingle page content here."]
    cleaned = remove_repeated_headers_and_footers(pages)
    assert len(cleaned) == 1
    assert "Single page content here." in cleaned[0]
    assert "Page 1" not in cleaned[0]


def test_is_english_text() -> None:
    english = "This is a natural English sentence explaining the context clearly."
    portuguese = "Esta é uma frase em português que não deve ser confundida com inglês."

    assert is_english_text(english) is True
    assert is_english_text(portuguese) is False

    # Textos curtos devem assumir o valor default para segurança
    assert is_english_text("Hi", default=True) is True
    assert is_english_text("Hi", default=False) is False


def test_filter_english_paragraphs() -> None:
    text = (
        "This is an English paragraph discussing vocabulary acquisition.\n\n"
        "Este parágrafo está escrito totalmente em português e deve ser removido.\n\n"
        "Here is another valid English paragraph for flashcard generation."
    )

    filtered = filter_english_paragraphs(text)
    assert "vocabulary acquisition" in filtered
    assert "flashcard generation" in filtered
    assert "parágrafo está escrito totalmente" not in filtered
