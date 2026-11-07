#!/usr/bin/env python3
"""Script para gerar PDF de teste sintético com texto em inglês e palavras funcionais."""

from __future__ import annotations

import argparse
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:
    import fitz


def create_sample_pdf(output_path: Path) -> Path:
    """Cria um PDF de 2 páginas contendo texto em inglês, palavras funcionais,

    hifenização proposital e cabeçalhos repetidos para testes.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    doc = fitz.open()

    rect = fitz.Rect(50, 72, 545, 770)

    # Página 1
    page1 = doc.new_page(width=595, height=842)
    header = "LexiDeck Automated Test Document - Running Header\n\n"
    body1 = (
        "The quick brown fox jumps over the lazy dog.\n\n"
        "In this exam-\n"
        "ple, we explore how natural language processing can be applied to "
        "language learning.\n\n"
        "The significance of function words such as 'the', 'of', 'in', and 'that' "
        "is paramount. When students read complex texts, they must understand both "
        "vocabulary and syntax.\n\n"
        "Page 1 of 2"
    )
    page1.insert_textbox(rect, header + body1, fontsize=11)

    # Página 2
    page2 = doc.new_page(width=595, height=842)
    body2 = (
        "Although many people consider prepositions simple, their proper usage "
        "requires consistent practice and exposure.\n\n"
        "That idea was discussed in the previous chapter. Furthermore, this paragraph "
        "demonstrates that continuous practice leads to fluency.\n\n"
        "Este parágrafo foi escrito intencionalmente em língua portuguesa para testar "
        "o filtro automático de idioma do leitor de documentos.\n\n"
        "Page 2 of 2"
    )
    page2.insert_textbox(rect, header + body2, fontsize=11)

    doc.save(output_path)
    doc.close()
    return output_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera PDF sintético para testes.")
    parser.add_argument(
        "--output",
        "-o",
        type=Path,
        default=Path("tests/fixtures/sample.pdf"),
        help="Caminho do arquivo PDF de saída.",
    )
    args = parser.parse_args()
    created = create_sample_pdf(args.output)
    print(f"PDF sintético gerado com sucesso em: {created}")


if __name__ == "__main__":
    main()
