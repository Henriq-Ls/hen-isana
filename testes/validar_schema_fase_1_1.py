"""Validação física isolada do schema da Fase 1.1.

Executável diretamente com a biblioteca padrão:
    python testes/validar_schema_fase_1_1.py

O teste usa cópias temporárias para criação, inserção, constraints, rollback e
recriação. O banco real é verificado apenas quanto a schema, integridade e
ausência de dados.
"""

from __future__ import annotations

import argparse
import os
import sqlite3
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DDL = ROOT / "aprendizado" / "bancos" / "linguagem_schema.sql"
DATABASE = ROOT / "aprendizado" / "bancos" / "linguagem.db"
EXPECTED_TABLES = {
    "lexemas",
    "formas_lexicais",
    "analises_morfologicas",
    "sentidos",
    "conceitos",
    "sentidos_conceitos",
    "expressoes",
    "expressao_componentes",
    "proposicoes",
    "proposicao_argumentos",
    "fatos",
    "relacoes_semanticas",
    "fontes",
    "evidencias",
}


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.execute("PRAGMA foreign_keys = ON")
    connection.row_factory = sqlite3.Row
    return connection


def user_tables(connection: sqlite3.Connection) -> set[str]:
    rows = connection.execute(
        "SELECT name FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
    )
    return {row["name"] for row in rows}


def application_column_count(connection: sqlite3.Connection) -> int:
    return sum(
        len(connection.execute(f"PRAGMA table_info({name})").fetchall())
        for name in sorted(user_tables(connection))
    )


def assert_schema(connection: sqlite3.Connection) -> None:
    assert user_tables(connection) == EXPECTED_TABLES
    assert application_column_count(connection) == 125
    assert connection.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
    assert connection.execute("PRAGMA foreign_key_check").fetchall() == []
    assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    assert connection.execute("PRAGMA user_version").fetchone()[0] == 110
    for table in EXPECTED_TABLES:
        assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0


def apply_schema(path: Path) -> sqlite3.Connection:
    connection = connect(path)
    connection.executescript(DDL.read_text(encoding="utf-8"))
    assert_schema(connection)
    return connection


def insert_minimum_graph(connection: sqlite3.Connection) -> None:
    source = connection.execute(
        "INSERT INTO fontes (tipo, identificador, origem, estado) "
        "VALUES ('manual', 'teste-fase-1.1', 'validador', 'aprovado')"
    ).lastrowid
    lexeme = connection.execute(
        "INSERT INTO lexemas (lema, categoria_lexical, estado) "
        "VALUES ('dormir', 'verbo', 'aprovado')"
    ).lastrowid
    form = connection.execute(
        "INSERT INTO formas_lexicais "
        "(lexema_id, forma, normalizada, tipo_forma, estado) "
        "VALUES (?, 'dormindo', 'dormindo', 'flexionada', 'aprovado')",
        (lexeme,),
    ).lastrowid
    connection.execute(
        "INSERT INTO analises_morfologicas "
        "(forma_lexical_id, classe_gramatical, aspecto, confianca) "
        "VALUES (?, 'verbo', 'progressivo', 0.95)",
        (form,),
    )
    sense = connection.execute(
        "INSERT INTO sentidos "
        "(lexema_id, definicao, estado, confianca) "
        "VALUES (?, 'estar em estado de sono', 'aprovado', 0.9)",
        (lexeme,),
    ).lastrowid
    concept = connection.execute(
        "INSERT INTO conceitos "
        "(chave, rotulo, tipo, estado, confianca) "
        "VALUES ('DORMIR', 'dormir', 'evento', 'aprovado', 0.9)"
    ).lastrowid
    connection.execute(
        "INSERT INTO sentidos_conceitos "
        "(sentido_id, conceito_id, tipo_ligacao, estado, confianca) "
        "VALUES (?, ?, 'principal', 'aprovado', 0.9)",
        (sense, concept),
    )
    expression = connection.execute(
        "INSERT INTO expressoes "
        "(forma, normalizada, tipo, estado, confianca) "
        "VALUES ('estar dormindo', 'estar dormindo', 'produtiva', 'aprovado', 0.8)"
    ).lastrowid
    connection.execute(
        "INSERT INTO expressao_componentes "
        "(expressao_id, ordem, tipo_componente, lexema_id) "
        "VALUES (?, 1, 'lexema', ?)",
        (expression, lexeme),
    )
    proposition = connection.execute(
        "INSERT INTO proposicoes "
        "(predicado_conceito_id, tipo_predicado, estado, fonte_id) "
        "VALUES (?, 'evento', 'aprovado', ?)",
        (concept, source),
    ).lastrowid
    connection.execute(
        "INSERT INTO proposicao_argumentos "
        "(proposicao_id, ordem, papel, alvo_tipo, alvo_id, confianca) "
        "VALUES (?, 1, 'sujeito', 'conceito', ?, 0.8)",
        (proposition, concept),
    )
    fact = connection.execute(
        "INSERT INTO fatos "
        "(proposicao_id, estado, fonte_id, confianca, contexto) "
        "VALUES (?, 'aprovado', ?, 0.8, 'teste')",
        (proposition, source),
    ).lastrowid
    relation = connection.execute(
        "INSERT INTO relacoes_semanticas "
        "(tipo_relacao, origem_tipo, origem_id, destino_tipo, destino_id, "
        "estado, confianca) "
        "VALUES ('relacionado', 'conceito', ?, 'fato', ?, 'aprovado', 0.7)",
        (concept, fact),
    ).lastrowid
    connection.execute(
        "INSERT INTO evidencias "
        "(fonte_id, alvo_tipo, alvo_id, trecho, estado, confianca) "
        "VALUES (?, 'relacao_semantica', ?, 'relação criada pelo teste', "
        "'aprovado', 0.9)",
        (source, relation),
    )


def test_constraints_and_rollback(connection: sqlite3.Connection) -> None:
    insert_minimum_graph(connection)
    connection.commit()

    assert connection.execute("SELECT COUNT(*) FROM fatos").fetchone()[0] == 1
    assert connection.execute("SELECT COUNT(*) FROM evidencias").fetchone()[0] == 1

    try:
        connection.execute(
            "INSERT INTO formas_lexicais "
            "(lexema_id, forma, normalizada) VALUES (99999, 'x', 'x')"
        )
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("FK de forma lexical não rejeitou lexema inexistente")

    try:
        connection.execute(
            "INSERT INTO fontes (tipo, identificador, origem, confiabilidade) "
            "VALUES ('manual', 'invalida', 'teste', 2.0)"
        )
    except sqlite3.IntegrityError:
        pass
    else:
        raise AssertionError("CHECK de confiança não rejeitou valor fora do intervalo")

    before = connection.execute("SELECT COUNT(*) FROM conceitos").fetchone()[0]
    connection.execute(
        "INSERT INTO conceitos (chave, rotulo, tipo) "
        "VALUES ('TEMP_ROLLBACK', 'temporário', 'teste')"
    )
    connection.rollback()
    after = connection.execute("SELECT COUNT(*) FROM conceitos").fetchone()[0]
    assert after == before


def validate(database: Path) -> None:
    if not database.exists():
        raise AssertionError(f"Banco não encontrado: {database}")

    with connect(database) as connection:
        assert_schema(connection)

    with tempfile.TemporaryDirectory(prefix="hen_isana_schema_") as directory:
        fresh = Path(directory) / "linguagem.db"
        with apply_schema(fresh) as connection:
            test_constraints_and_rollback(connection)

        recreated = Path(directory) / "recreated.db"
        with apply_schema(recreated) as connection:
            assert_schema(connection)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=DATABASE)
    args = parser.parse_args()
    validate(args.database)
    print("OK: schema, 125 colunas, integridade, FKs, constraints, rollback e recriação")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())