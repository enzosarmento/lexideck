"""Módulo de construção e engenharia de prompts em lote com tratamento especial para palavras funcionais."""

from __future__ import annotations

from collections.abc import Sequence

from lexideck.word_extractor import ExtractedWord

SYSTEM_PROMPT_TEMPLATE = """Você é um lexicógrafo sênior e professor de inglês especialista em alunos brasileiros.
Sua missão é gerar análises linguísticas para cartões de estudo do Anki para uma lista de palavras extraídas de um texto real.

REGRAS OBRIGATÓRIAS:
1. Retorne EXCLUSIVAMENTE um objeto JSON válido, sem texto explicativo, sem saudações e sem Markdown antes ou depois.
2. A estrutura do JSON deve conter a chave "cards", contendo a lista de análises para cada palavra solicitada.
3. Considere as frases reais de contexto do documento original para DESAMBIGUAR o sentido exato da palavra e escolher a melhor tradução em português do Brasil.
4. Para palavras lexicais comuns: forneça de 2 a 3 frases de exemplo naturais e idiomáticas com tradução.

5. TRATAMENTO ESPECIAL PARA PALAVRAS FUNCIONAIS (artigos, preposições, conjunções, pronomes, verbos auxiliares/modais):
   - Marque "is_function_word": true.
   - No campo "translation_pt": informe a equivalência mais comum e note se muitas vezes não é traduzida literalmente.
   - No campo "usage_notes_pt", elabore uma explicação rica cobrindo:
     * A função gramatical exata em português (ex: artigo definido, preposição de posse/origem, etc.);
     * Onde ela costuma aparecer na frase (ex: antes de substantivos, início de oração subordinada, após verbos);
     * Em quais situações é mais comum;
     * Erros mais comuns cometidos por brasileiros com essa palavra (ex: uso indevido de "the" antes de possessivos ou nomes próprios);
     * Mencione a frequência observada no documento.
   - No campo "examples": inclua EXATAMENTE 3 frases de exemplo em inglês com tradução, demonstrando 3 usos ou sentidos sintáticos distintos da palavra.

FORMATO JSON ESPERADO:
{
  "cards": [
    {
      "word": "string",
      "lemma": "string",
      "pos": "string",
      "is_function_word": true,
      "ipa": "/pronúncia IPA/",
      "translation_pt": ["tradução 1", "tradução 2"],
      "definition_en": "definição curta em inglês simples",
      "usage_notes_pt": "explicação detalhada de uso, posição na frase e dicas para brasileiros",
      "examples": [
        {"en": "exemplo 1", "pt": "tradução 1"},
        {"en": "exemplo 2", "pt": "tradução 2"},
        {"en": "exemplo 3", "pt": "tradução 3"}
      ],
      "cefr_level": "A1|A2|B1|B2|C1|C2"
    }
  ]
}
"""


def format_word_entry(word: ExtractedWord) -> str:
    """Formata os dados de uma única palavra e seu contexto original para o prompt."""
    func_indicator = (
        f" [PALAVRA FUNCIONAL - {word.functional_category_pt or 'Gramatical'}]"
        if word.is_function_word
        else ""
    )
    lines = [
        f'- Palavra: "{word.word}" (Lema: "{word.lemma}", Classe: {word.pos}, Freq no PDF: {word.frequency}){func_indicator}'
    ]

    if word.original_forms:
        forms_str = ", ".join(f'"{f}"' for f in word.original_forms[:5])
        lines.append(f"  Formas encontradas no texto: {forms_str}")

    if word.contexts:
        contexts_str = " | ".join(f'"{c}"' for c in word.contexts[:3])
        lines.append(f"  Contexto real do PDF: {contexts_str}")
    else:
        lines.append("  Contexto real do PDF: (não informado)")

    return "\n".join(lines)


def build_batch_prompt(
    words: Sequence[ExtractedWord],
    batch_index: int = 1,
    total_batches: int = 1,
) -> str:
    """Constrói o prompt completo para um lote de palavras."""
    words_entries = "\n\n".join(format_word_entry(w) for w in words)

    prompt = (
        f"{SYSTEM_PROMPT_TEMPLATE}\n\n"
        f"LOTE {batch_index}/{total_batches} ({len(words)} palavras para analisar):\n\n"
        f"{words_entries}\n\n"
        f"Gere o JSON estrito com a análise de todas as {len(words)} palavras listadas acima:"
    )
    return prompt


def chunk_words(
    words: Sequence[ExtractedWord], batch_size: int = 30
) -> list[list[ExtractedWord]]:
    """Divide a lista de palavras em lotes homogêneos de tamanho configurável."""
    if batch_size <= 0:
        batch_size = 30
    return [list(words[i : i + batch_size]) for i in range(0, len(words), batch_size)]
