"""Índice dos módulos e símbolos criados em aprendizado/gerado/."""

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Optional


DATA_DIR = Path(__file__).resolve().parents[1] / "aprendizado" / "bancos"
DEFAULT_DB = DATA_DIR / "indice_codigo.db"


@dataclass(frozen=True)
class RegistroCodigo:
    id: int
    categoria: str
    arquivo: str
    classe: Optional[str]
    funcao: Optional[str]
    status: str


class IndiceCodigoDB:
    def __init__(self, caminho_db: Optional[Path] = None):
        self.caminho_db = Path(caminho_db or DEFAULT_DB)
        self.caminho_db.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.caminho_db)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS indice_codigo (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                categoria TEXT NOT NULL,
                arquivo TEXT NOT NULL,
                classe TEXT,
                funcao TEXT,
                status TEXT NOT NULL DEFAULT 'ativo',
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_indice_categoria
            ON indice_codigo(categoria)
            """
        )
        self.conn.commit()

    @staticmethod
    def _registro(linha: sqlite3.Row) -> RegistroCodigo:
        return RegistroCodigo(
            id=int(linha["id"]),
            categoria=str(linha["categoria"]),
            arquivo=str(linha["arquivo"]),
            classe=linha["classe"],
            funcao=linha["funcao"],
            status=str(linha["status"]),
        )

    def registrar(
        self,
        categoria: str,
        arquivo: str,
        classe: Optional[str] = None,
        funcao: Optional[str] = None,
        status: str = "ativo",
    ) -> RegistroCodigo:
        cursor = self.conn.execute(
            """
            INSERT INTO indice_codigo (
                categoria, arquivo, classe, funcao, status
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (categoria, arquivo, classe, funcao, status),
        )
        self.conn.commit()
        linha = self.conn.execute(
            "SELECT * FROM indice_codigo WHERE id = ?",
            (cursor.lastrowid,),
        ).fetchone()
        assert linha is not None
        return self._registro(linha)

    def listar(self, categoria: Optional[str] = None) -> list[RegistroCodigo]:
        if categoria is None:
            cursor = self.conn.execute(
                "SELECT * FROM indice_codigo ORDER BY id"
            )
        else:
            cursor = self.conn.execute(
                """
                SELECT * FROM indice_codigo
                WHERE categoria = ?
                ORDER BY id
                """,
                (categoria,),
            )
        return [self._registro(linha) for linha in cursor.fetchall()]

    def fechar(self) -> None:
        self.conn.close()

    def __enter__(self) -> "IndiceCodigoDB":
        return self

    def __exit__(self, *_args: object) -> None:
        self.fechar()
