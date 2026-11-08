"""Interface de linha de comando (CLI) do LexiDeck utilizando Typer e Rich."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any

import typer
import yaml
from dotenv import find_dotenv, load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table

from lexideck import __version__
from lexideck.anki_exporter import export_deck
from lexideck.cache import SQLiteCache
from lexideck.models import WordCardResponse
from lexideck.pdf_reader import extract_text_from_pdf
from lexideck.prompts import build_batch_prompt, chunk_words
from lexideck.providers.base import LLMProvider, ProviderAuthError, ProviderError
from lexideck.providers.claude_provider import ClaudeProvider
from lexideck.providers.gemini_provider import GeminiProvider
from lexideck.providers.ollama_provider import OllamaProvider
from lexideck.providers.openai_provider import OpenAIProvider
from lexideck.word_extractor import (
    ExtractedWord,
    extract_words_from_text,
    filter_extracted_words,
)

# Inicializa console Rich e aplicação Typer
console = Console()
app = typer.Typer(
    name="lexideck",
    help="Transforme qualquer PDF em inglês em um baralho Anki com traduções, exemplos e explicação das palavras funcionais.",
    add_completion=False,
)

DEFAULT_CONFIG_PATH = Path("config.yaml")


def load_application_config(config_path: Path | None = None) -> dict[str, Any]:
    """Carrega as configurações do arquivo YAML ou retorna os padrões do sistema."""
    path = config_path or DEFAULT_CONFIG_PATH
    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = yaml.safe_load(f)
                if isinstance(data, dict):
                    return data
        except Exception as exc:
            console.print(
                f"[yellow]Aviso:[/yellow] Não foi possível ler {path}: {exc}. Usando configurações padrão."
            )

    return {
        "providers": {
            "openai": {"model": "gpt-4o-mini", "timeout": 30, "max_retries": 3},
            "gemini": {"model": "gemini-3.8-flash", "timeout": 30, "max_retries": 3},
            "claude": {
                "model": "claude-3-5-haiku-20241022",
                "timeout": 30,
                "max_retries": 3,
            },
        },
        "processing": {
            "batch_size": 30,
            "min_frequency": 1,
            "include_function_words": True,
            "exclude_proper_nouns": True,
            "lemmatize": True,
        },
        "anki": {
            "deck_name_prefix": "LexiDeck::",
            "default_sort": "frequency",
        },
    }


def create_llm_provider(
    provider_name: str,
    model_override: str | None,
    config: dict[str, Any],
) -> LLMProvider:
    """Instancia o provedor de IA apropriado de acordo com a seleção do usuário."""
    name = provider_name.strip().lower()
    providers_cfg = config.get("providers", {})
    provider_cfg = providers_cfg.get(name, {})

    model = model_override or provider_cfg.get("model")
    timeout = provider_cfg.get("timeout", 30)
    max_retries = provider_cfg.get("max_retries", 3)

    if name == "openai":
        return OpenAIProvider(
            model=model or "gpt-4o-mini",
            timeout=timeout,
            max_retries=max_retries,
        )
    if name == "gemini":
        return GeminiProvider(
            model=model or "gemini-3.8-flash",
            timeout=timeout,
            max_retries=max_retries,
        )
    if name == "claude":
        return ClaudeProvider(
            model=model or "claude-3-5-haiku-20241022",
            timeout=timeout,
            max_retries=max_retries,
        )
    if name == "ollama":
        base_url = provider_cfg.get("base_url", "http://localhost:11434")
        return OllamaProvider(
            model=model or "llama3.2",
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
        )

    raise typer.BadParameter(
        f"Provedor '{provider_name}' não suportado. Opções válidas: openai, gemini, claude, ollama."
    )


def version_callback(value: bool) -> None:
    """Exibe a versão do LexiDeck e encerra a execução."""
    if value:
        console.print(
            f"[bold cyan]LexiDeck[/bold cyan] versão [bold green]{__version__}[/bold green]"
        )
        raise typer.Exit()


@app.command()
def main(
    pdf_path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Caminho para o arquivo PDF em inglês.",
    ),
    provider: str = typer.Option(
        "gemini",
        "--provider",
        "-p",
        help="Provedor de IA a ser utilizado: gemini, openai, claude ou ollama.",
    ),
    model: str | None = typer.Option(
        None,
        "--model",
        "-m",
        help="Nome do modelo de IA (sobrescreve a configuração padrão).",
    ),
    batch_size: int = typer.Option(
        30,
        "--batch-size",
        "-b",
        min=1,
        max=100,
        help="Quantidade de palavras analisadas por requisição à IA.",
    ),
    min_frequency: int = typer.Option(
        1,
        "--min-frequency",
        "-f",
        min=1,
        help="Frequência mínima de ocorrência no PDF para inclusão no baralho.",
    ),
    include_function_words: bool = typer.Option(
        True,
        "--include-function-words/--exclude-function-words",
        help="Inclui ou exclui palavras funcionais com explicações especiais.",
    ),
    no_lemmatize: bool = typer.Option(
        False,
        "--no-lemmatize",
        help="Desativa a lematização (usa a forma exata encontrada no texto).",
    ),
    exclude_proper_nouns: bool = typer.Option(
        True,
        "--exclude-proper-nouns/--include-proper-nouns",
        help="Exclui ou inclui nomes próprios identificados no documento.",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        "-l",
        min=1,
        help="Limita o processamento às N palavras mais frequentes (ideal para testes econômicos).",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Executa estimativa prévia de palavras, tokens e custos sem chamar APIs reais.",
    ),
    resume: bool = typer.Option(
        True,
        "--resume/--no-resume",
        help="Utiliza o cache local SQLite para evitar reprocessar palavras já analisadas.",
    ),
    reverse_cards: bool = typer.Option(
        False,
        "--reverse-cards",
        help="Gera também cartões reversos (Português -> Inglês).",
    ),
    cloze: bool = typer.Option(
        False,
        "--cloze",
        help="Gera cartões no modelo Cloze (omissão de palavras nas frases de exemplo).",
    ),
    audio: bool = typer.Option(
        False,
        "--audio",
        help="Gera e inclui áudio de pronúncia nativa com gTTS no baralho .apkg.",
    ),
    ocr: bool = typer.Option(
        False,
        "--ocr",
        help="Ativa reconhecimento óptico (OCR) como fallback para páginas escaneadas.",
    ),
    output: Path = typer.Option(
        Path("./output"),
        "--output",
        "-o",
        file_okay=False,
        dir_okay=True,
        help="Diretório onde os arquivos .apkg, .tsv e .csv serão salvos.",
    ),
    config: Path | None = typer.Option(
        None,
        "--config",
        help="Caminho alternativo para o arquivo config.yaml.",
    ),
    verbose: bool = typer.Option(
        False,
        "--verbose",
        "-v",
        help="Habilita exibição de logs detalhados de depuração.",
    ),
    version: bool | None = typer.Option(
        None,
        "--version",
        callback=version_callback,
        is_eager=True,
        help="Exibe a versão do LexiDeck e encerra.",
    ),
) -> None:
    """Transforme qualquer PDF em inglês em um baralho Anki completo com suporte a IA."""
    _ = version
    # Carrega variáveis de ambiente do .env (do diretório atual ou da raiz do projeto)
    load_dotenv(find_dotenv(usecwd=True))
    project_env = Path(__file__).resolve().parent.parent.parent / ".env"
    if project_env.is_file():
        load_dotenv(project_env)

    # Configuração de logging
    log_level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    start_time = time.time()
    cfg = load_application_config(config)

    console.print(
        Panel.fit(
            f"[bold cyan]LexiDeck[/bold cyan] v{__version__} — "
            "Transforme PDFs em baralhos Anki inteligentes\n"
            f"[dim]Documento: {pdf_path.name} | Provedor: {provider.lower()}[/dim]",
            border_style="cyan",
        )
    )

    # 1. Instanciação e validação prévia do provedor de IA
    try:
        llm = create_llm_provider(provider, model, cfg)
    except Exception as exc:
        console.print(f"[bold red]Erro de configuração do provedor:[/bold red] {exc}")
        raise typer.Exit(code=1) from exc

    # 2. Leitura e limpeza de texto do PDF
    with console.status(
        "[bold green]Lendo e higienizando o PDF...[/bold green]", spinner="dots"
    ):
        try:
            doc = extract_text_from_pdf(
                pdf_path, filter_language=True, ocr_fallback=ocr
            )
        except Exception as exc:
            console.print(f"[bold red]Erro ao processar PDF:[/bold red] {exc}")
            raise typer.Exit(code=1) from exc

    if not doc.full_text.strip():
        console.print(
            "[bold yellow]Nenhum texto legível em inglês foi extraído do PDF.[/bold yellow] "
            "Se o documento for composto de páginas escaneadas, utilize a flag --ocr."
        )
        raise typer.Exit(code=1)

    ocr_info = f" ({len(doc.ocr_pages)} via OCR)" if doc.ocr_pages else ""
    console.print(
        f"✓ [green]PDF processado:[/green] {doc.total_pages} páginas{ocr_info} "
        f"({len(doc.empty_pages)} vazias/escaneadas ignoradas)."
    )

    # 3. Extração e contagem de palavras (NLP)
    with console.status(
        "[bold green]Executando análise linguística (spaCy)...[/bold green]",
        spinner="dots",
    ):
        extracted = extract_words_from_text(
            doc.full_text,
            lemmatize=not no_lemmatize,
            max_contexts=3,
        )

    # 4. Aplicação de filtros de negócio
    filtered = filter_extracted_words(
        extracted,
        min_frequency=min_frequency,
        include_function_words=include_function_words,
        exclude_proper_nouns=exclude_proper_nouns,
        limit=limit,
    )

    if not filtered:
        console.print(
            "[bold yellow]Nenhuma palavra restante após a aplicação dos filtros.[/bold yellow] "
            "Tente reduzir a frequência mínima (--min-frequency) ou permitir palavras funcionais."
        )
        raise typer.Exit(code=0)

    console.print(
        f"✓ [green]Vocabulário extraído:[/green] {len(extracted)} palavras únicas "
        f"➜ [bold cyan]{len(filtered)} palavras selecionadas[/bold cyan] para o baralho."
    )

    # 5. Modo DRY-RUN (estimativa sem chamadas de API)
    if dry_run:
        cost_info = llm.estimate_cost(len(filtered), batch_size=batch_size)

        table = Table(
            title="[bold yellow]Estimativa de Execução (Dry-Run)[/bold yellow]"
        )
        table.add_column("Métrica", style="cyan")
        table.add_column("Valor Estimado", style="bold white")

        table.add_row("Provedor selecionado", llm.name.upper())
        table.add_row("Modelo de IA", llm.model)
        table.add_row("Palavras a processar", str(int(cost_info["total_words"])))
        table.add_row("Lotes de requisição", str(int(cost_info["batches_count"])))
        table.add_row(
            "Tokens de Entrada (Prompt)",
            f"~{int(cost_info['estimated_input_tokens']):,}",
        )
        table.add_row(
            "Tokens de Saída (Completion)",
            f"~{int(cost_info['estimated_output_tokens']):,}",
        )
        table.add_row(
            "Total de Tokens", f"~{int(cost_info['estimated_total_tokens']):,}"
        )
        table.add_row(
            "Custo Financeiro Estimado",
            f"[green]${cost_info['estimated_cost_usd']:.4f} USD[/green]",
        )

        console.print(table)
        console.print(
            "\n[dim]Dica: Para gerar os cartões reais, execute o mesmo comando sem a flag --dry-run.[/dim]"
        )
        raise typer.Exit(code=0)

    # 6. Verificação de cache local e identificação de palavras pendentes
    cache = SQLiteCache() if resume else None
    cached_cards_map: dict[str, WordCardResponse] = {}
    words_to_query: list[ExtractedWord] = []

    if cache is not None:
        word_keys = [w.word for w in filtered]
        cached_cards_map = cache.get_many(word_keys, provider=llm.name, model=llm.model)

    for item in filtered:
        if item.word in cached_cards_map:
            # Vincula contexto original do documento atual ao cartão em cache
            card = cached_cards_map[item.word]
            card.frequency = item.frequency
            if item.contexts:
                card.original_sentence = item.contexts[0]
        else:
            words_to_query.append(item)

    cached_count = len(filtered) - len(words_to_query)
    if cached_count > 0:
        console.print(
            f"✓ [cyan]Cache local:[/cyan] {cached_count} palavras já disponíveis (não serão cobradas)."
        )

    final_cards: list[WordCardResponse] = list(cached_cards_map.values())

    # 7. Geração com IA para palavras não cacheadas com barra de progresso
    if words_to_query:
        batches = chunk_words(words_to_query, batch_size=batch_size)
        total_batches = len(batches)

        console.print(
            f"➜ [bold]Enviando {len(words_to_query)} palavras para {llm.name.upper()} "
            f"({total_batches} lotes)...[/bold]"
        )

        # Mapa rápido de contexto por palavra
        word_meta_map = {w.word: w for w in words_to_query}

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            console=console,
        ) as progress:
            batch_task = progress.add_task(
                "[cyan]Gerando cartões com IA...", total=total_batches
            )

            for idx, batch_words in enumerate(batches, start=1):
                prompt = build_batch_prompt(
                    batch_words,
                    batch_index=idx,
                    total_batches=total_batches,
                )

                try:
                    generated_cards = llm.generate_batch_cards(
                        prompt,
                        words_in_batch=len(batch_words),
                    )

                    # Enriquecimento com metadados do documento
                    for card in generated_cards:
                        meta = word_meta_map.get(card.word.lower())
                        if meta:
                            card.frequency = meta.frequency
                            if meta.contexts:
                                card.original_sentence = meta.contexts[0]

                    # Gravação no cache local
                    if cache is not None:
                        cache.set_many(
                            generated_cards, provider=llm.name, model=llm.model
                        )

                    final_cards.extend(generated_cards)
                    progress.advance(batch_task)

                except ProviderAuthError as auth_err:
                    console.print(
                        f"\n[bold red]Falha de autenticação:[/bold red] {auth_err}"
                    )
                    raise typer.Exit(code=1) from auth_err
                except ProviderError as prov_err:
                    console.print(
                        f"\n[bold red]Erro na chamada da IA:[/bold red] {prov_err}"
                    )
                    raise typer.Exit(code=1) from prov_err
                except Exception as exc:
                    console.print(
                        f"\n[bold red]Erro inesperado durante geração:[/bold red] {exc}"
                    )
                    raise typer.Exit(code=1) from exc

    if cache is not None:
        cache.close()

    if not final_cards:
        console.print("[bold red]Nenhum cartão foi gerado.[/bold red]")
        raise typer.Exit(code=1)

    # 8. Exportação para .apkg, .tsv e .csv
    with console.status(
        "[bold green]Criando baralho Anki (.apkg) e tabelas...[/bold green]",
        spinner="dots",
    ):
        deck_prefix = cfg.get("anki", {}).get("deck_name_prefix", "LexiDeck::")
        sort_by = cfg.get("anki", {}).get("default_sort", "frequency")

        apkg_path, tsv_path, csv_path = export_deck(
            cards=final_cards,
            output_dir=output,
            pdf_name=pdf_path.name,
            deck_name_prefix=deck_prefix,
            sort_by=sort_by,
            reverse_cards=reverse_cards,
            cloze_model=cloze,
            include_audio=audio,
        )

    elapsed_time = time.time() - start_time

    # 9. Tabela de resumo final
    summary_table = Table(
        title="[bold green]Resumo de Execução do LexiDeck[/bold green]"
    )
    summary_table.add_column("Item", style="cyan")
    summary_table.add_column("Detalhe", style="bold white")

    summary_table.add_row("Documento de entrada", pdf_path.name)
    summary_table.add_row("Total de cartões gerados", str(len(final_cards)))
    summary_table.add_row("Palavras vindas do cache", str(cached_count))
    summary_table.add_row("Novas palavras via IA", str(len(words_to_query)))
    summary_table.add_row("Provedor & Modelo", f"{llm.name.upper()} ({llm.model})")
    summary_table.add_row(
        "Cartões reversos (PT -> EN)", "Ativo" if reverse_cards else "Desativado"
    )
    summary_table.add_row("Modelo Cloze (omissão)", "Ativo" if cloze else "Desativado")
    summary_table.add_row(
        "Áudio de pronúncia (gTTS)", "Ativo" if audio else "Desativado"
    )
    summary_table.add_row(
        "Páginas via OCR", str(len(doc.ocr_pages)) if ocr else "Desativado"
    )
    summary_table.add_row("Arquivo Anki (.apkg)", str(apkg_path.resolve()))
    summary_table.add_row("Planilha TSV", str(tsv_path.resolve()))
    summary_table.add_row("Planilha CSV", str(csv_path.resolve()))
    summary_table.add_row("Tempo total", f"{elapsed_time:.1f}s")

    console.print()
    console.print(summary_table)
    console.print(
        f"\n[bold green]Sucesso![/bold green] Baralho [bold cyan]{apkg_path.name}[/bold cyan] pronto para importação no Anki.\n"
    )
