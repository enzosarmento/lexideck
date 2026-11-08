"""Módulo para exportação de baralhos Anki (.apkg) e arquivos tabulares (CSV/TSV)."""

from __future__ import annotations

import csv
import hashlib
import logging
import re
from collections.abc import Sequence
from pathlib import Path

try:
    import genanki
except ImportError:  # pragma: no cover
    genanki = None

from lexideck.models import ExampleSentence, WordCardResponse

logger = logging.getLogger(__name__)

# ID fixo e estável para o modelo de nota do LexiDeck (Fase 1: Inglês -> Português)
LEXIDECK_MODEL_ID = 1607392319

CARD_CSS = """
.card {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    font-size: 16px;
    text-align: center;
    color: #2c3e50;
    background-color: #f8fafc;
    padding: 15px;
}
.nightMode .card {
    background-color: #1a202c;
    color: #e2e8f0;
}
.card-container {
    max-width: 580px;
    margin: 0 auto;
    background: #ffffff;
    border-radius: 12px;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    padding: 24px;
    text-align: left;
}
.nightMode .card-container {
    background: #2d3748;
    box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.3);
}
.badge-func {
    display: inline-block;
    background-color: #fef3c7;
    color: #92400e;
    font-size: 11px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    padding: 3px 8px;
    border-radius: 9999px;
    border: 1px solid #fcd34d;
    margin-bottom: 8px;
}
.nightMode .badge-func {
    background-color: #78350f;
    color: #fef3c7;
    border-color: #b45309;
}
.word {
    font-size: 28px;
    font-weight: 800;
    color: #1e3a8a;
    margin-bottom: 4px;
}
.nightMode .word {
    color: #60a5fa;
}
.ipa {
    font-size: 15px;
    color: #64748b;
    font-family: "Lucida Sans Unicode", "DejaVu Sans", sans-serif;
    margin-bottom: 12px;
}
.nightMode .ipa {
    color: #94a3b8;
}
.pos-tag {
    display: inline-block;
    font-size: 12px;
    font-style: italic;
    color: #475569;
    background: #f1f5f9;
    padding: 2px 8px;
    border-radius: 4px;
    margin-right: 6px;
}
.nightMode .pos-tag {
    background: #4a5568;
    color: #cbd5e1;
}
.cefr-badge {
    display: inline-block;
    font-size: 11px;
    font-weight: 700;
    color: #0369a1;
    background: #e0f2fe;
    padding: 2px 6px;
    border-radius: 4px;
}
.nightMode .cefr-badge {
    background: #075985;
    color: #bae6fd;
}
hr#answer {
    border: 0;
    height: 1px;
    background: #e2e8f0;
    margin: 16px 0;
}
.nightMode hr#answer {
    background: #4a5568;
}
.translations {
    font-size: 20px;
    font-weight: 700;
    color: #0f172a;
    margin-bottom: 10px;
}
.nightMode .translations {
    color: #f8fafc;
}
.definition {
    font-size: 14px;
    color: #334155;
    margin-bottom: 14px;
    border-left: 3px solid #3b82f6;
    padding-left: 10px;
}
.nightMode .definition {
    color: #cbd5e1;
    border-left-color: #60a5fa;
}
.section-title {
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    color: #64748b;
    margin-top: 14px;
    margin-bottom: 6px;
}
.nightMode .section-title {
    color: #94a3b8;
}
.notes-body {
    font-size: 13.5px;
    line-height: 1.5;
    color: #334155;
    background: #f8fafc;
    border: 1px solid #e2e8f0;
    border-radius: 6px;
    padding: 10px 12px;
}
.nightMode .notes-body {
    background: #1e293b;
    border-color: #334155;
    color: #cbd5e1;
}
.examples-list {
    margin: 0;
    padding-left: 20px;
    font-size: 14px;
}
.examples-list li {
    margin-bottom: 8px;
    line-height: 1.4;
}
.examples-list .en {
    font-weight: 500;
    color: #1e293b;
}
.nightMode .examples-list .en {
    color: #f1f5f9;
}
.examples-list .pt {
    font-size: 13px;
    color: #64748b;
    font-style: italic;
}
.nightMode .examples-list .pt {
    color: #94a3b8;
}
.context-body {
    font-size: 13px;
    font-style: italic;
    color: #475569;
    background: #f1f5f9;
    padding: 8px 12px;
    border-radius: 6px;
}
.nightMode .context-body {
    background: #1e293b;
    color: #94a3b8;
}
.footer-meta {
    font-size: 11px;
    color: #94a3b8;
    margin-top: 16px;
    text-align: right;
}
"""

FRONT_TEMPLATE = """
<div class="card-container">
    {{#FunctionWordBadge}}<div class="badge-func">{{FunctionWordBadge}}</div>{{/FunctionWordBadge}}
    <div class="word">{{Word}}</div>
    {{#IPA}}<div class="ipa">{{IPA}}</div>{{/IPA}}
    <div>
        {{#POS}}<span class="pos-tag">{{POS}}</span>{{/POS}}
        {{#CEFRLevel}}<span class="cefr-badge">{{CEFRLevel}}</span>{{/CEFRLevel}}
    </div>
</div>
"""

BACK_TEMPLATE = """
<div class="card-container">
    {{#FunctionWordBadge}}<div class="badge-func">{{FunctionWordBadge}}</div>{{/FunctionWordBadge}}
    <div class="word">{{Word}}</div>
    {{#IPA}}<div class="ipa">{{IPA}}</div>{{/IPA}}
    <div>
        {{#POS}}<span class="pos-tag">{{POS}}</span>{{/POS}}
        {{#CEFRLevel}}<span class="cefr-badge">{{CEFRLevel}}</span>{{/CEFRLevel}}
    </div>

    <hr id="answer">

    <div class="translations">{{Back}}</div>

    {{#DefinitionEN}}
    <div class="definition">{{DefinitionEN}}</div>
    {{/DefinitionEN}}

    {{#UsageNotes}}
    <div class="section-title">Uso & Gramática</div>
    <div class="notes-body">{{UsageNotes}}</div>
    {{/UsageNotes}}

    {{#ExamplesHTML}}
    <div class="section-title">Exemplos</div>
    {{ExamplesHTML}}
    {{/ExamplesHTML}}

    {{#OriginalSentence}}
    <div class="section-title">Frase Original do Documento</div>
    <div class="context-body">"{{OriginalSentence}}"</div>
    {{/OriginalSentence}}

    <div class="footer-meta">
        Frequência no PDF: {{Frequency}} | Nível: {{CEFRLevel}}
    </div>
</div>
"""


def get_lexideck_model() -> genanki.Model:
    """Retorna o modelo de nota padrão do LexiDeck (Inglês -> Português)."""
    if genanki is None:
        raise RuntimeError("Pacote 'genanki' não está instalado.")

    return genanki.Model(
        LEXIDECK_MODEL_ID,
        "LexiDeck (English to Portuguese)",
        fields=[
            {"name": "Front"},
            {"name": "Back"},
            {"name": "Word"},
            {"name": "IPA"},
            {"name": "POS"},
            {"name": "DefinitionEN"},
            {"name": "ExamplesHTML"},
            {"name": "UsageNotes"},
            {"name": "CEFRLevel"},
            {"name": "OriginalSentence"},
            {"name": "Frequency"},
            {"name": "FunctionWordBadge"},
        ],
        templates=[
            {
                "name": "Inglês -> Português",
                "qfmt": FRONT_TEMPLATE,
                "afmt": BACK_TEMPLATE,
            }
        ],
        css=CARD_CSS,
    )


def generate_deck_id(deck_name: str) -> int:
    """Gera um ID numérico de 31 bits determinístico a partir do nome do baralho."""
    raw = f"lexideck:deck:{deck_name}".encode()
    digest = hashlib.sha256(raw).hexdigest()
    return int(digest[:8], 16) & 0x7FFFFFFF


def format_examples_html(examples: Sequence[ExampleSentence]) -> str:
    """Converte a lista de frases de exemplo em HTML formatado para o cartão Anki."""
    if not examples:
        return ""
    items = [
        f'<li><span class="en">{ex.en}</span><br><span class="pt">{ex.pt}</span></li>'
        for ex in examples
    ]
    return f'<ul class="examples-list">{"".join(items)}</ul>'


def sanitize_filename(name: str) -> str:
    """Higieniza o nome do arquivo removendo caracteres inválidos para o sistema operacional."""
    return re.sub(r"[^\w\-_\.]", "_", name).strip("_")


def sort_cards(
    cards: Sequence[WordCardResponse], sort_by: str = "frequency"
) -> list[WordCardResponse]:
    """Ordena os cartões por frequência ('frequency') ou por nível CEFR ('level')."""
    if sort_by == "level":
        cefr_order = {"A1": 1, "A2": 2, "B1": 3, "B2": 4, "C1": 5, "C2": 6}
        return sorted(
            cards,
            key=lambda c: (cefr_order.get(c.cefr_level.value, 99), -c.frequency),
        )
    # Padrão: mais frequentes primeiro
    return sorted(cards, key=lambda c: c.frequency, reverse=True)


def export_deck(
    cards: Sequence[WordCardResponse],
    output_dir: Path | str,
    pdf_name: str,
    deck_name_prefix: str = "LexiDeck::",
    sort_by: str = "frequency",
) -> tuple[Path, Path, Path]:
    """Exporta os cartões nos formatos .apkg (Anki), .tsv e .csv.

    Args:
        cards: Lista de cartões a exportar.
        output_dir: Diretório de destino.
        pdf_name: Nome do arquivo PDF fonte.
        deck_name_prefix: Prefixo do baralho no Anki (subbaralho).
        sort_by: Critério de ordenação ('frequency' ou 'level').

    Returns:
        Tupla contendo (caminho_apkg, caminho_tsv, caminho_csv).
    """
    out_path = Path(output_dir)
    out_path.mkdir(parents=True, exist_ok=True)

    clean_pdf_title = Path(pdf_name).stem
    sanitized_title = sanitize_filename(clean_pdf_title)
    deck_full_name = f"{deck_name_prefix}{clean_pdf_title}"

    sorted_cards = sort_cards(cards, sort_by=sort_by)

    # 1. Geração do arquivo .apkg com genanki
    deck_id = generate_deck_id(deck_full_name)
    deck = genanki.Deck(deck_id, deck_full_name)
    model = get_lexideck_model()

    for card in sorted_cards:
        # Monta tags temáticas
        tags = [
            f"lexideck_{sanitized_title}",
            f"cefr_{card.cefr_level.value.lower()}",
            f"pos_{sanitize_filename(card.pos.lower())}",
        ]
        if card.is_function_word:
            tags.append("palavra_funcional")

        translations_str = ", ".join(card.translation_pt)
        examples_html = format_examples_html(card.examples)
        badge_func = "Palavra Funcional" if card.is_function_word else ""

        note = genanki.Note(
            model=model,
            fields=[
                f"{card.word} {card.ipa}",
                translations_str,
                card.word,
                card.ipa,
                card.pos,
                card.definition_en,
                examples_html,
                card.usage_notes_pt,
                card.cefr_level.value,
                card.original_sentence or "",
                str(card.frequency),
                badge_func,
            ],
            tags=tags,
        )
        deck.add_note(note)

    apkg_file = out_path / f"{sanitized_title}.apkg"
    genanki.Package(deck).write_to_file(str(apkg_file))

    # 2. Geração dos arquivos tabulares (TSV e CSV)
    tsv_file = out_path / f"{sanitized_title}.tsv"
    csv_file = out_path / f"{sanitized_title}.csv"

    fieldnames = [
        "Front",
        "Back",
        "Word",
        "IPA",
        "POS",
        "DefinitionEN",
        "ExamplesHTML",
        "UsageNotes",
        "CEFRLevel",
        "OriginalSentence",
        "Frequency",
        "IsFunctionWord",
        "Tags",
    ]

    for target_path, delimiter in [(tsv_file, "\t"), (csv_file, ",")]:
        with open(target_path, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter=delimiter)
            writer.writeheader()
            for card in sorted_cards:
                tags_str = " ".join(
                    [
                        f"lexideck_{sanitized_title}",
                        f"cefr_{card.cefr_level.value.lower()}",
                        f"pos_{sanitize_filename(card.pos.lower())}",
                    ]
                    + (["palavra_funcional"] if card.is_function_word else [])
                )
                writer.writerow(
                    {
                        "Front": f"{card.word} {card.ipa}",
                        "Back": ", ".join(card.translation_pt),
                        "Word": card.word,
                        "IPA": card.ipa,
                        "POS": card.pos,
                        "DefinitionEN": card.definition_en,
                        "ExamplesHTML": format_examples_html(card.examples),
                        "UsageNotes": card.usage_notes_pt,
                        "CEFRLevel": card.cefr_level.value,
                        "OriginalSentence": card.original_sentence or "",
                        "Frequency": card.frequency,
                        "IsFunctionWord": "sim" if card.is_function_word else "não",
                        "Tags": tags_str,
                    }
                )

    logger.info("Baralho exportado com sucesso para %s", apkg_file)
    return apkg_file, tsv_file, csv_file
