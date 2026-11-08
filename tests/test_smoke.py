"""Teste de fumaça (smoke test) ponta a ponta provando o fluxo:

PDF -> Palavras -> IA (mockada) -> .apkg / .tsv / .csv
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from typer.testing import CliRunner

from lexideck.cli import app
from scripts.make_sample_pdf import create_sample_pdf

runner = CliRunner()


def build_mock_card_response(word: str) -> dict:
    is_func = word in {"the", "of", "in", "that", "although"}
    return {
        "word": word,
        "lemma": word,
        "pos": "palavra funcional" if is_func else "substantivo",
        "is_function_word": is_func,
        "ipa": f"/{word}/",
        "translation_pt": [f"tradução de {word}"],
        "definition_en": f"definition for {word}",
        "usage_notes_pt": f"notas de uso sobre {word}",
        "examples": [
            {"en": f"Example sentence with {word} 1.", "pt": f"Exemplo com {word} 1."},
            {"en": f"Example sentence with {word} 2.", "pt": f"Exemplo com {word} 2."},
            {"en": f"Example sentence with {word} 3.", "pt": f"Exemplo com {word} 3."},
        ],
        "cefr_level": "A1" if is_func else "B1",
    }


def test_end_to_end_smoke_pipeline(tmp_path: Path) -> None:
    # 1. Cria PDF sintético de teste
    pdf_path = tmp_path / "smoke_sample.pdf"
    create_sample_pdf(pdf_path)
    output_dir = tmp_path / "deck_output"

    from lexideck.models import WordCardResponse
    from lexideck.providers.base import LLMProvider

    def fake_generate_batch_cards(
        _self: LLMProvider, prompt: str, words_in_batch: int = 1
    ):
        _ = words_in_batch
        cards_raw = []
        for line in prompt.splitlines():
            if line.startswith('- Palavra: "'):
                word = line.split('"')[1]
                cards_raw.append(build_mock_card_response(word))
        return [WordCardResponse.model_validate(c) for c in cards_raw]

    with patch.object(LLMProvider, "generate_batch_cards", fake_generate_batch_cards):
        # 2. Executa a CLI com provedor gemini e limite de 5 palavras
        result = runner.invoke(
            app,
            [
                str(pdf_path),
                "--provider",
                "gemini",
                "--limit",
                "5",
                "--output",
                str(output_dir),
                "--no-resume",
            ],
        )

        assert result.exit_code == 0, f"CLI falhou: {result.stdout}"
        assert "Resumo de Execução do LexiDeck" in result.stdout
        assert "Sucesso!" in result.stdout

        # 3. Valida se os 3 arquivos de saída foram gerados
        apkg_file = output_dir / "smoke_sample.apkg"
        tsv_file = output_dir / "smoke_sample.tsv"
        csv_file = output_dir / "smoke_sample.csv"

        assert apkg_file.exists() and apkg_file.stat().st_size > 0
        assert tsv_file.exists() and tsv_file.stat().st_size > 0
        assert csv_file.exists() and csv_file.stat().st_size > 0

        # 4. Verifica o conteúdo do TSV gerado
        tsv_content = tsv_file.read_text(encoding="utf-8")
        assert "Front\tBack\tWord\tIPA" in tsv_content
        assert "palavra_funcional" in tsv_content

        # 5. Testa execução repetida com cache ativado (--resume)
        result_cached = runner.invoke(
            app,
            [
                str(pdf_path),
                "--provider",
                "gemini",
                "--limit",
                "5",
                "--output",
                str(output_dir),
                "--resume",
            ],
        )
        assert result_cached.exit_code == 0
        assert "Resumo de Execução do LexiDeck" in result_cached.stdout
