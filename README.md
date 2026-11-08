# LexiDeck

> Transforme qualquer PDF em inglês em um baralho Anki com traduções em português, exemplos de uso e explicação das palavras funcionais, usando Gemini, ChatGPT ou Claude.

[![Python Version](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Code Style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Commitizen Friendly](https://img.shields.io/badge/commitizen-friendly-brightgreen.svg)](http://commitizen.github.io/cz-cli/)

O **LexiDeck** é uma ferramenta de linha de comando (CLI) voltada para estudantes de inglês, autodidatas e poliglotas brasileiros. Em vez de simplesmente gerar listas descontextualizadas de vocabulário, o LexiDeck analisa o texto original de um livro, artigo científico ou documento em PDF, desambigua o significado com base nas frases reais do texto e gera baralhos Anki completos (`.apkg`), além de planilhas tabulares (`.tsv` e `.csv`).

---

## 🚀 Destaques e Funcionalidades

- **Extração e Higienização de PDF**: Processa texto selecionável com PyMuPDF, unifica quebras de linha hifenizadas (ex.: `"exam-\nple"` ➜ `"example"`), remove cabeçalhos/rodapés repetidos, filtra números de página e descarta parágrafos fora do idioma inglês.
- **Processamento de Linguagem Natural (spaCy)**: Tokenização contextual, POS-tagging, lematização inteligente mantendo as formas originais encontradas como referência e extração de 1 a 3 sentenças reais do PDF para cada palavra.
- **Tratamento Especial para Palavras Funcionais**:
  - Stop words essenciais (*the, a, of, in, that, would, although...*) **não são descartadas**.
  - Recebem a tag `palavra_funcional` e estilização diferenciada no cartão.
  - Explicação rica da função gramatical em português (artigo, preposição, conjunção, pronome, modal), posição típica na frase e dicas sobre erros frequentes de brasileiros.
  - 3 exemplos práticos com tradução demonstrando usos sintáticos distintos.
- **Multi-Provedor com Validação Pydantic**:
  - **Google Gemini** (`gemini-2.5-flash`, `gemini-1.5-pro`) via SDK oficial `google-genai`.
  - **OpenAI** (`gpt-4o-mini`, `gpt-4o`) com modo JSON estrito.
  - **Anthropic Claude** (`claude-3-5-haiku-20241022`, `claude-3-5-sonnet-20241022`) via Tool Use.
  - Tentativas automáticas com retroalimentação de erros de validação e backoff exponencial para limites de requisição (HTTP 429).
- **Cache Local com SQLite (WAL mode)**: Armazena análises por hash de `palavra + provedor + modelo`. Nunca pague duas vezes pela mesma palavra e retome processos interrompidos instantaneamente com `--resume`.
- **Exportação Pronta para o Anki**: Gera arquivos `.apkg` com modelo de cartão limpo e moderno, estilização para modo escuro (`nightMode`), além de versões tabulares `.tsv` e `.csv`.

---

## 📦 Instalação

### Requisitos
- **Python 3.10 ou superior**
- Git

### Passo a Passo

1. **Clone o repositório:**
   ```bash
   git clone https://github.com/enzosarmento/lexideck.git
   cd lexideck
   ```

2. **Crie e ative um ambiente virtual:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # No Windows: .venv\Scripts\activate
   ```

3. **Instale o LexiDeck e as dependências em modo editável:**
   ```bash
   pip install -e ".[dev]"
   ```

4. **Baixe o modelo spaCy em inglês:**
   ```bash
   python -m spacy download en_core_web_sm
   ```

5. **Verifique a instalação:**
   ```bash
   lexideck --version
   ```

---

## 🔑 Configuração de Chaves de API

Copie o arquivo de exemplo `.env.example` para `.env`:
```bash
cp .env.example .env
```

Abra o arquivo `.env` e insira a chave do provedor que deseja utilizar:
```env
# Google Gemini (recomendado pelo custo-benefício)
GEMINI_API_KEY=AIzaSy...

# OpenAI (ChatGPT)
OPENAI_API_KEY=sk-...

# Anthropic Claude
ANTHROPIC_API_KEY=sk-ant-...
```
> **Nota de Segurança:** O arquivo `.env` está incluído no `.gitignore` e **nunca** será comitado no repositório.

---

## 🛡️ Fluxo Recomendado de Primeiro Uso (Econômico e Seguro)

Para garantir previsibilidade de custos e conferir o resultado antes de processar um documento grande, recomendamos sempre este fluxo:

1. **Gere uma estimativa prévia sem gastar nada (`--dry-run`):**
   ```bash
   lexideck seu_livro.pdf --dry-run --provider gemini
   ```
   *Exibe o total de palavras, tokens de prompt/completion e o custo projetado em dólares.*

2. **Processe uma amostra pequena para teste barato (`--limit 20`):**
   ```bash
   lexideck seu_livro.pdf --limit 20 --provider gemini --output ./saida_teste
   ```

3. **Importe o `.apkg` no Anki e avalie a qualidade dos cartões:**
   - Abra o Anki e dê um duplo clique no arquivo `./saida_teste/seu_livro.apkg`.
   - Revise o design, a pronúncia IPA, os exemplos e as explicações das palavras funcionais.

4. **Processe o PDF completo com cache ativo:**
   ```bash
   lexideck seu_livro.pdf --provider gemini --batch-size 30 --output ./saida_final
   ```
   *As palavras já analisadas no passo 2 serão lidas do cache instantaneamente, sem nova cobrança.*

---

## 💻 Exemplos de Uso da CLI

### 1. Execução padrão com Gemini
```bash
lexideck documento.pdf --provider gemini --output ./baralhos
```

### 2. Uso com OpenAI e lote customizado
```bash
lexideck artigo.pdf --provider openai --model gpt-4o-mini --batch-size 25
```

### 3. Exclusão de palavras funcionais e frequência mínima
```bash
lexideck livro.pdf --min-frequency 2 --exclude-function-words
```

### 4. Sem lematização (preservar formas exatas)
```bash
lexideck texto.pdf --no-lemmatize --limit 50
```

### 5. Resumo das principais opções
| Opção | Descrição | Padrão |
| :--- | :--- | :--- |
| `pdf_path` | Caminho do arquivo PDF de entrada | *(obrigatório)* |
| `--provider`, `-p` | Provedor de IA (`gemini`, `openai`, `claude`) | `gemini` |
| `--model`, `-m` | Sobrescreve o modelo do provedor | *(do config.yaml)* |
| `--batch-size`, `-b` | Tamanho do lote de palavras por requisição | `30` |
| `--min-frequency`, `-f` | Frequência mínima no texto para inclusão | `1` |
| `--limit`, `-l` | Restringe o processamento às N palavras mais frequentes | `None` (todas) |
| `--dry-run` | Mostra estimativa de custo sem chamar a IA | `False` |
| `--resume` / `--no-resume` | Ativa/desativa cache local SQLite | `True` |
| `--no-lemmatize` | Desativa a lematização canônica | `False` |
| `--exclude-proper-nouns` | Ignora nomes próprios identificados | `True` |
| `--output`, `-o` | Diretório de destino dos arquivos exportados | `./output` |
| `--verbose`, `-v` | Exibe logs detalhados de depuração | `False` |
| `--version` | Exibe a versão do LexiDeck | — |

---

## 📥 Como Importar no Anki

1. **Anki Desktop (Windows, macOS, Linux):**
   - Abra o Anki.
   - Vá em **Arquivo** ➜ **Importar...** e selecione o arquivo `.apkg` gerado (ou simplesmente dê duplo clique nele).
   - O baralho aparecerá organizado sob o subbaralho `LexiDeck::<Nome-do-PDF>`.
2. **AnkiMobile (iOS) / AnkiDroid (Android):**
   - Envie o arquivo `.apkg` por e-mail, nuvem ou cabo para o dispositivo móvel e selecione "Abrir com Anki".
3. **Reimportação segura:**
   - Como os IDs de modelo e baralho são estáveis e determinísticos, reimportar o baralho atualiza os cartões existentes sem criar duplicatas.

---

## 🧩 Adicionando um Novo Provedor de IA

A arquitetura do LexiDeck adota o padrão Strategy/Adapter. Para adicionar um novo provedor (por exemplo, um provedor local ou customizado):

1. Crie uma classe em `src/lexideck/providers/` herdando de `LLMProvider`:
   ```python
   from lexideck.providers.base import LLMProvider


   class MeuNovoProvider(LLMProvider):
       @property
       def name(self) -> str:
           return "meu_provedor"

       def generate(self, prompt: str, schema=None):
           # Chame sua API e retorne o JSON cru (string ou dict)
           return "{ ... }"
   ```
2. Registre o provedor em `create_llm_provider` no arquivo `src/lexideck/cli.py`.
3. Adicione as configurações padrão em `config.yaml`.

---

## 🛠️ Desenvolvimento e Boas Práticas

### Pre-commit e Commitizen
O projeto utiliza **pre-commit** para garantir formatação, validação de tipos e conformidade com a convenção **Conventional Commits 1.0**:

```bash
# Instalação das ferramentas de desenvolvimento
pip install pre-commit commitizen

# Ativação dos hooks no repositório local
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

### Padrão de Commits
Utilize o padrão:
```
<tipo>(<escopo>): <descrição no imperativo e em inglês>

[corpo opcional]
```

Exemplos:
- `feat(pdf): extract and clean text from pdf`
- `fix(cache): resolve concurrency lock in sqlite wal mode`
- `test(nlp): add tests for function word tagging`

Você também pode utilizar o assistente interativo do Commitizen:
```bash
cz commit
```

### Execução de Testes e Linter
```bash
# Rodar linter e formatador
ruff check .
ruff format .

# Rodar a suíte completa de testes unitários
pytest
```

---

## 📄 Licença

Distribuído sob a licença **MIT**. Consulte o arquivo [LICENSE](LICENSE) para mais detalhes.
