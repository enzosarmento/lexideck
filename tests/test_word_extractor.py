"""Testes unitários para o extrator, normalizador e classificador de palavras."""

from __future__ import annotations

from lexideck.word_extractor import (
    extract_words_from_text,
    filter_extracted_words,
)


def test_word_extraction_and_lemmatization() -> None:
    text = (
        "The athlete is running in the park. Yesterday, she ran five miles, "
        "and tomorrow she will run again. Running keeps her healthy."
    )

    # Com lematização ativa (padrão)
    words_lemmatized = extract_words_from_text(text, lemmatize=True)
    run_entry = next(w for w in words_lemmatized if w.word == "run")

    assert run_entry.lemma == "run"
    assert run_entry.frequency >= 3
    # Formas originais preservadas
    assert "running" in [f.lower() for f in run_entry.original_forms]
    assert "ran" in [f.lower() for f in run_entry.original_forms]
    assert "run" in [f.lower() for f in run_entry.original_forms]

    # Sem lematização: formas superficiais separadas
    words_exact = extract_words_from_text(text, lemmatize=False)
    words_set = {w.word for w in words_exact}
    assert "running" in words_set
    assert "ran" in words_set
    assert "run" in words_set


def test_context_sentence_extraction() -> None:
    text = (
        "Artificial intelligence is transforming education. "
        "Language models help learners understand complex grammar. "
        "With artificial intelligence, students get personalized feedback."
    )

    words = extract_words_from_text(text, max_contexts=3)
    ai_entry = next(w for w in words if w.word == "intelligence")

    assert len(ai_entry.contexts) == 2
    assert "Artificial intelligence is transforming education." in ai_entry.contexts
    assert (
        "With artificial intelligence, students get personalized feedback."
        in ai_entry.contexts
    )


def test_function_words_flagging() -> None:
    text = (
        "The students that studied in the library could understand that grammar "
        "because they practiced with enthusiasm."
    )

    words = extract_words_from_text(text)
    words_by_name = {w.word: w for w in words}

    # "the" -> artigo / determinante
    the_word = words_by_name["the"]
    assert the_word.is_function_word is True
    assert "artigo" in (the_word.functional_category_pt or "").lower()

    # "in" -> preposição
    in_word = words_by_name["in"]
    assert in_word.is_function_word is True
    assert "preposição" in (in_word.functional_category_pt or "").lower()

    # "that" -> palavra funcional com múltiplos sentidos
    that_word = words_by_name["that"]
    assert that_word.is_function_word is True

    # "because" -> conjunção
    because_word = words_by_name["because"]
    assert because_word.is_function_word is True
    assert "conjunção" in (because_word.functional_category_pt or "").lower()

    # "could" -> verbo modal
    could_word = words_by_name["could"]
    assert could_word.is_function_word is True
    assert "modal" in (could_word.functional_category_pt or "").lower()

    # "grammar" e "student" -> palavras lexicais de conteúdo (não funcionais)
    student_word = words_by_name["student"]
    assert student_word.is_function_word is False


def test_proper_nouns_numerals_and_acronyms() -> None:
    text = (
        "Alan Turing lived in London in 1950. He researched AI algorithms for the BBC."
    )

    words = extract_words_from_text(text)
    words_by_name = {w.word: w for w in words}

    assert words_by_name["alan"].is_proper_noun is True
    assert words_by_name["turing"].is_proper_noun is True
    assert words_by_name["london"].is_proper_noun is True

    # Numerais e siglas
    assert words_by_name["1950"].is_numeral is True
    assert words_by_name["ai"].is_acronym is True
    assert words_by_name["bbc"].is_acronym is True


def test_contractions_handling() -> None:
    text = "They don't think it's impossible to learn English."
    words = extract_words_from_text(text)
    words_set = {w.word for w in words}

    # Contração "don't" deve normalizar "not" e "do"
    assert "do" in words_set
    assert "not" in words_set


def test_filter_extracted_words() -> None:
    text = (
        "Alice loves reading books. Bob also loves books. Books, books, books everywhere! "
        "They read in the library in 2026 with great joy."
    )

    words = extract_words_from_text(text)

    # 1. Filtro com exclusão padrão de nomes próprios e inclusão de funcionais
    filtered = filter_extracted_words(
        words,
        min_frequency=1,
        include_function_words=True,
        exclude_proper_nouns=True,
    )
    filtered_keys = {w.word for w in filtered}

    assert "book" in filtered_keys
    assert "love" in filtered_keys
    assert "the" in filtered_keys
    assert "in" in filtered_keys
    assert "alice" not in filtered_keys
    assert "bob" not in filtered_keys
    assert "2026" not in filtered_keys

    # 2. Filtro com exclusão de palavras funcionais
    filtered_no_func = filter_extracted_words(
        words,
        include_function_words=False,
        exclude_proper_nouns=True,
    )
    no_func_keys = {w.word for w in filtered_no_func}
    assert "book" in no_func_keys
    assert "the" not in no_func_keys
    assert "in" not in no_func_keys

    # 3. Filtro por frequência mínima
    filtered_min_freq = filter_extracted_words(
        words,
        min_frequency=3,
    )
    # Apenas "book" aparece com alta frequência (>= 3)
    assert len(filtered_min_freq) == 1
    assert filtered_min_freq[0].word == "book"

    # 4. Filtro por limite N
    limited = filter_extracted_words(words, limit=2)
    assert len(limited) == 2
