"""Histórico persistente de alterações do sistema."""

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Optional


DATA_DIR = Path(__file__).resolve().parents[1] / "aprendizado" / "bancos"
DEFAULT_DB = DATA_DIR / "log_mudancas.db"


@dataclass(frozen=True)
class Mudanca:
    id: int
    acao: str
    arquivo: Optional[str]
    sucesso: bool
    mensagem: str
    contexto: Optional[str]


class LogMudancasDB:
    def __init__(self, caminho_db: Optional[Path] = None):
        self.caminho_db = Path(caminho_db or DEFAULT_DB)
        self.caminho_db.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.caminho_db)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS log_mudancas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                acao TEXT NOT NULL,
                arquivo TEXT,
                sucesso INTEGER NOT NULL,
                mensagem TEXT NOT NULL,
                contexto TEXT,
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.commit()

    def registrar(
        self,
        acao: str,
        mensagem: str,
        arquivo: Optional[str] = None,
        sucesso: bool = True,
        contexto: Optional[str] = None,
    ) -> Mudanca:
        cursor = self.conn.execute(
            """
            INSERT INTO log_mudancas (
                acao, arquivo, sucesso, mensagem, contexto
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (acao, arquivo, int(sucesso), mensagem, contexto),
        )
        self.conn.commit()
        linha = self.conn.execute(
            "SELECT * FROM log_mudancas WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        assert linha is not None
        return Mudanca(
            id=int(linha["id"]),
            acao=str(linha["acao"]),
            arquivo=linha["arquivo"],
            sucesso=bool(linha["sucesso"]),
            mensagem=str(linha["mensagem"]),
            contexto=linha["contexto"],
        )

    def listar(self, limite: int = 100) -> list[Mudanca]:
        cursor = self.conn.execute(
            """
            SELECT *
            FROM log_mudancas
            ORDER BY id DESC
            LIMIT ?
            """,
            (limite,),
        )
        return [
            Mudanca(
                id=int(linha["id"]),
                acao=str(linha["acao"]),
                arquivo=linha["arquivo"],
                sucesso=bool(linha["sucesso"]),
                mensagem=str(linha["mensagem"]),
                contexto=linha["contexto"],
            )
            for linha in cursor.fetchall()
        ]

    def fechar(self) -> None:
        self.conn.close()

    def __enter__(self) -> "LogMudancasDB":
        return self

    def __exit__(self, *_args: object) -> None:
        self.fechar()
