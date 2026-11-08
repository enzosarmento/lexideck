# Changelog

Todas as alterações notáveis neste projeto serão documentadas neste arquivo.

O formato é baseado em [Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/),
e este projeto adere ao [Semantic Versioning](https://semver.org/lang/pt-BR/).

## v0.2.0 (2026-11-07)

### Feat

- **cli**: add reverse-cards, audio and ocr flags
- **ollama**: add ollama provider for local models
- **anki**: add pronunciation audio with gtts
- **anki**: add reverse and cloze card models
- **pdf**: add ocr fallback for scanned pages

## v0.1.0 (2026-11-07)

### Feat

- **cli**: add lexideck command with progress, limit and dry-run
- **anki**: export apkg and csv with english to portuguese cards
- **prompts**: add batch prompts with function word guidance
- **cache**: add sqlite cache with resume support
- **claude**: add claude provider
- **gemini**: add gemini provider
- **openai**: add openai provider
- **providers**: add llm provider interface and pydantic schema
- **nlp**: flag function words and proper nouns
- **nlp**: tokenize, lemmatize and count word frequency
- **pdf**: extract and clean text from pdf
