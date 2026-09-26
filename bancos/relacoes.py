"""Relações entre termos do banco de conhecimento."""

from pathlib import Path
import sqlite3
from typing import Optional

from protocolo.regras import ALVO_RELACOES, TipoAcao
from protocolo.verificador import validar_permissao


DATA_DIR = Path(__file__).resolve().parents[1] / "aprendizado" / "bancos"
DEFAULT_DB = DATA_DIR / "relacoes.db"


class RelacoesDB:
    def __init__(self, caminho_db: Optional[Path] = None):
        self.caminho_db = Path(caminho_db or DEFAULT_DB)
        self.caminho_db.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.caminho_db)
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS relacoes (
                termo_id INTEGER NOT NULL,
                termo_relacionado_id INTEGER NOT NULL,
                tipo TEXT NOT NULL DEFAULT 'relacionado',
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (termo_id, termo_relacionado_id)
            )
            """
        )
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_relacoes_termo
            ON relacoes(termo_id)
            """
        )
        self.conn.commit()

    def adicionar(
        self,
        termo_id: int,
        termo_relacionado_id: int,
        tipo: str = "relacionado",
        *,
        permissao: object | None = None,
    ) -> None:
        autorizacao = validar_permissao(
            permissao,
            TipoAcao.SALVAR_RELACAO,
            ALVO_RELACOES,
        )
        if not autorizacao.permitida:
            raise PermissionError(autorizacao.mensagem)

        if termo_id == termo_relacionado_id:
            return
        self.conn.execute(
            """
            INSERT OR IGNORE INTO relacoes (
                termo_id, termo_relacionado_id, tipo
            )
            VALUES (?, ?, ?)
            """,
            (termo_id, termo_relacionado_id, tipo),
        )
        self.conn.execute(
            """
            INSERT OR IGNORE INTO relacoes (
                termo_id, termo_relacionado_id, tipo
            )
            VALUES (?, ?, ?)
            """,
            (termo_relacionado_id, termo_id, tipo),
        )
        self.conn.commit()

    def listar_ids(self, termo_id: int) -> list[int]:
        cursor = self.conn.execute(
            """
            SELECT termo_relacionado_id
            FROM relacoes
            WHERE termo_id = ?
            ORDER BY termo_relacionado_id
            """,
            (termo_id,),
        )
        return [int(linha[0]) for linha in cursor.fetchall()]

    def fechar(self) -> None:
        self.conn.close()

    def __enter__(self) -> "RelacoesDB":
        return self

    def __exit__(self, *_args: object) -> None:
        self.fechar()
