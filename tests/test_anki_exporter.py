"""Testes unitários dedicados aos recursos do exportador Anki (Reverso, Cloze e Áudio)."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from lexideck.anki_exporter import (
    export_deck,
    format_examples_html,
    make_cloze_sentence,
    sort_cards,
)
from lexideck.models import ExampleSentence, WordCardResponse

SAMPLE_CARD = WordCardResponse(
    word="run",
    lemma="run",
    pos="verb",
    is_function_word=False,
    ipa="/rʌn/",
    translation_pt=["correr"],
    definition_en="to move quickly on foot",
    usage_notes_pt="Verbo irregular comum.",
    examples=[
        ExampleSentence(en="The athlete runs every day.", pt="O atleta corre todo dia.")
    ],
    cefr_level="A1",
    original_sentence="He had to run fast to catch the train.",
    frequency=15,
)

SAMPLE_FUNC_CARD = WordCardResponse(
    word="the",
    lemma="the",
    pos="article",
    is_function_word=True,
    ipa="/ðiː/",
    translation_pt=["o", "a"],
    definition_en="definite article",
    usage_notes_pt="Usado antes de substantivos específicos.",
    examples=[ExampleSentence(en="The sun is shining.", pt="O sol está brilhando.")],
    cefr_level="A1",
    frequency=42,
)


def test_make_cloze_sentence() -> None:
    # Caso 1: Palavra exata encontrada
    res1 = make_cloze_sentence("She loves to run in the park.", "run", "run")
    assert "{{c1::run}}" in res1

    # Caso 2: Variante flexionada correspondente ao lema
    res2 = make_cloze_sentence("He runs very quickly.", "run", "run")
    assert "{{c1::runs}}" in res2

    # Caso 3: Palavra não encontrada diretamente (fallback)
    res3 = make_cloze_sentence("An unrelated sentence.", "run", "run")
    assert res3 == "{{c1::run}}: An unrelated sentence."


def test_sort_cards() -> None:
    cards = [SAMPLE_CARD, SAMPLE_FUNC_CARD]

    # Ordenação por frequência (padrão)
    sorted_freq = sort_cards(cards, sort_by="frequency")
    assert sorted_freq[0].word == "the"  # freq 42 > 15

    # Ordenação por nível
    sorted_level = sort_cards(cards, sort_by="level")
    assert len(sorted_level) == 2


def test_format_examples_html() -> None:
    examples = [ExampleSentence(en="Hello world", pt="Olá mundo")]
    html = format_examples_html(examples)
    assert '<span class="en">Hello world</span>' in html
    assert '<span class="pt">Olá mundo</span>' in html


def test_export_deck_with_reverse_and_cloze(tmp_path: Path) -> None:
    out_dir = tmp_path / "deck_out"
    apkg, tsv, csv_f = export_deck(
        cards=[SAMPLE_CARD, SAMPLE_FUNC_CARD],
        output_dir=out_dir,
        pdf_name="test_book.pdf",
        reverse_cards=True,
        cloze_model=True,
        include_audio=False,
    )

    assert apkg.exists() and apkg.stat().st_size > 0
    assert tsv.exists() and tsv.stat().st_size > 0
    assert csv_f.exists() and csv_f.stat().st_size > 0


def test_export_deck_with_audio_mock(tmp_path: Path) -> None:
    out_dir = tmp_path / "deck_audio_out"

    def fake_gtts_save(_self: object, path: str | Path) -> None:
        Path(path).write_bytes(b"MOCK_MP3_BYTES")

    with patch("gtts.gTTS.save", fake_gtts_save):
        apkg, _, _ = export_deck(
            cards=[SAMPLE_CARD],
            output_dir=out_dir,
            pdf_name="audio_test.pdf",
            include_audio=True,
        )

        assert apkg.exists()
        media_file = out_dir / ".media" / "lexideck_run.mp3"
        assert media_file.exists()
        assert media_file.read_bytes() == b"MOCK_MP3_BYTES"
