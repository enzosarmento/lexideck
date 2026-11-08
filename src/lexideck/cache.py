"""Sistema de cache local resiliente utilizando SQLite com suporte à retomada."""

from __future__ import annotations

import hashlib
import json
import logging
import sqlite3
from pathlib import Path
from types import TracebackType

from lexideck.models import WordCardResponse

logger = logging.getLogger(__name__)

DEFAULT_CACHE_PATH = Path(".lexideck_cache.db")


def make_cache_key(provider: str, model: str, word: str) -> str:
    """Gera uma chave determinística baseada no hash de provedor, modelo e palavra."""
    raw = f"{provider.strip().lower()}:{model.strip().lower()}:{word.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class SQLiteCache:
    """Gerenciador de cache local persistente em SQLite para respostas de IA."""

    def __init__(self, db_path: str | Path = DEFAULT_CACHE_PATH) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn: sqlite3.Connection | None = None
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = sqlite3.connect(str(self.db_path), timeout=10.0)
            self._conn.row_factory = sqlite3.Row
            # Ativa modo WAL (Write-Ahead Logging) para maior desempenho e concorrência segura
            self._conn.execute("PRAGMA journal_mode=WAL;")
            self._conn.execute("PRAGMA synchronous=NORMAL;")
        return self._conn

    def _init_db(self) -> None:
        """Cria as tabelas e índices necessários caso ainda não existam."""
        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS word_cache (
                    cache_key TEXT PRIMARY KEY,
                    provider TEXT NOT NULL,
                    model TEXT NOT NULL,
                    word TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_word_lookup
                ON word_cache(provider, model, word);
                """
            )

    def get(self, word: str, provider: str, model: str) -> WordCardResponse | None:
        """Recupera um cartão de palavra do cache se existir."""
        key = make_cache_key(provider, model, word)
        conn = self._get_connection()
        cursor = conn.execute(
            "SELECT data_json FROM word_cache WHERE cache_key = ? LIMIT 1;", (key,)
        )
        row = cursor.fetchone()
        if row is None:
            return None

        try:
            data = json.loads(row["data_json"])
            return WordCardResponse.model_validate(data)
        except Exception as exc:
            logger.warning(
                "Falha ao desserializar item em cache para '%s': %s", word, exc
            )
            return None

    def get_many(
        self, words: list[str], provider: str, model: str
    ) -> dict[str, WordCardResponse]:
        """Recupera múltiplos cartões em lote a partir de uma única consulta SQL."""
        if not words:
            return {}

        results: dict[str, WordCardResponse] = {}
        # Mapeamento reverso de hash para palavra original consultada
        hash_to_word = {make_cache_key(provider, model, w): w.lower() for w in words}
        keys = list(hash_to_word.keys())

        conn = self._get_connection()
        # Divide em lotes de 500 chaves para respeitar limites do SQLite
        chunk_size = 500
        for i in range(0, len(keys), chunk_size):
            chunk = keys[i : i + chunk_size]
            placeholders = ",".join("?" for _ in chunk)
            cursor = conn.execute(
                f"SELECT cache_key, data_json FROM word_cache WHERE cache_key IN ({placeholders});",
                chunk,
            )
            for row in cursor.fetchall():
                try:
                    word_key = hash_to_word[row["cache_key"]]
                    data = json.loads(row["data_json"])
                    results[word_key] = WordCardResponse.model_validate(data)
                except Exception as exc:
                    logger.debug("Erro ao ler item em lote do cache: %s", exc)

        return results

    def set(self, card: WordCardResponse, provider: str, model: str) -> None:
        """Salva um cartão de palavra no cache."""
        key = make_cache_key(provider, model, card.word)
        data_json = card.model_dump_json()
        conn = self._get_connection()
        with conn:
            conn.execute(
                """
                INSERT INTO word_cache (cache_key, provider, model, word, data_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    data_json = excluded.data_json,
                    created_at = CURRENT_TIMESTAMP;
                """,
                (key, provider.lower(), model.lower(), card.word.lower(), data_json),
            )

    def set_many(
        self, cards: list[WordCardResponse], provider: str, model: str
    ) -> None:
        """Salva uma lista de cartões no cache dentro de uma transação atômica."""
        if not cards:
            return

        records = [
            (
                make_cache_key(provider, model, c.word),
                provider.lower(),
                model.lower(),
                c.word.lower(),
                c.model_dump_json(),
            )
            for c in cards
        ]

        conn = self._get_connection()
        with conn:
            conn.executemany(
                """
                INSERT INTO word_cache (cache_key, provider, model, word, data_json)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(cache_key) DO UPDATE SET
                    data_json = excluded.data_json,
                    created_at = CURRENT_TIMESTAMP;
                """,
                records,
            )

    def count(self) -> int:
        """Retorna a contagem total de palavras cacheadas."""
        conn = self._get_connection()
        cursor = conn.execute("SELECT COUNT(*) AS total FROM word_cache;")
        row = cursor.fetchone()
        return int(row["total"]) if row else 0

    def clear(self) -> None:
        """Limpa todos os registros do cache."""
        conn = self._get_connection()
        with conn:
            conn.execute("DELETE FROM word_cache;")

    def close(self) -> None:
        """Fecha a conexão com o banco de dados."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> SQLiteCache:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        self.close()
