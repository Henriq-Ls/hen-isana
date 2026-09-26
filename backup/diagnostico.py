"""Registro persistente de falhas e bloqueios."""

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Optional


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
DEFAULT_DB = DATA_DIR / "diagnostico.db"


@dataclass(frozen=True)
class Diagnostico:
    id: int
    acao: str
    alvo: Optional[str]
    erro: str
    contexto: Optional[str]


class DiagnosticoDB:
    def __init__(self, caminho_db: Optional[Path] = None):
        self.caminho_db = Path(caminho_db or DEFAULT_DB)
        self.caminho_db.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.caminho_db)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS diagnostico (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                acao TEXT NOT NULL,
                alvo TEXT,
                erro TEXT NOT NULL,
                contexto TEXT,
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    def registrar(
        self,
        acao: str,
        erro: str,
        alvo: Optional[str] = None,
        contexto: Optional[str] = None,
    ) -> Diagnostico:
        cursor = self.conn.execute(
            """
            INSERT INTO diagnostico (acao, alvo, erro, contexto)
            VALUES (?, ?, ?, ?)
            """,
            (acao, alvo, erro, contexto),
        )
        self.conn.commit()
        linha = self.conn.execute(
            "SELECT * FROM diagnostico WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        assert linha is not None
        return Diagnostico(
            id=int(linha["id"]),
            acao=str(linha["acao"]),
            alvo=linha["alvo"],
            erro=str(linha["erro"]),
            contexto=linha["contexto"],
        )

    def listar(self, limite: int = 100) -> list[Diagnostico]:
        cursor = self.conn.execute(
            """
            SELECT *
            FROM diagnostico
            ORDER BY id DESC
            LIMIT ?
            """,
            (limite,),
        )
        return [
            Diagnostico(
                id=int(linha["id"]),
                acao=str(linha["acao"]),
                alvo=linha["alvo"],
                erro=str(linha["erro"]),
                contexto=linha["contexto"],
            )
            for linha in cursor.fetchall()
        ]

    def fechar(self) -> None:
        self.conn.close()

    def __enter__(self) -> "DiagnosticoDB":
        return self

    def __exit__(self, *_args: object) -> None:
        self.fechar()
