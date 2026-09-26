"""Persistência auxiliar para o ciclo auditável de migração.

Esta camada não grava conhecimento canônico. Ela mantém propostas, auditoria
de aplicação e checkpoints em um banco separado, sempre por chamada explícita.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
from typing import Any, Optional
from uuid import uuid4

from core.contratos import ContratoCadastro


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "aprendizado" / "bancos" / "migracao_auditavel_schema.sql"
DEFAULT_DB = ROOT / "data" / "migracao_auditavel.db"
DEFAULT_CHECKPOINT_DIR = ROOT / "data" / "checkpoints_migracao"
ESTADOS_PROPOSTA = (
    "proposta",
    "em_revisao",
    "autorizada",
    "aplicada",
    "recusada",
    "erro",
)


def _texto(valor: Optional[str], nome: str, *, permitir_nulo: bool = False) -> Optional[str]:
    if valor is None and permitir_nulo:
        return None
    if not isinstance(valor, str) or not valor.strip():
        raise ValueError(f"{nome} deve ser texto não vazio")
    return valor.strip()


def _json_canonico(valor: Any) -> str:
    return json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def hash_contrato(contrato: ContratoCadastro) -> tuple[str, str]:
    """Retorna o JSON canônico e seu hash SHA-256."""

    conteudo = _json_canonico(contrato.to_dict())
    return conteudo, hashlib.sha256(conteudo.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class PropostaPersistida:
    proposta_id: str
    idempotencia: str
    hash_conteudo: str
    conteudo_json: str
    versao_contrato: str
    versao_mapeamento: str
    lote: Optional[str]
    origem: str
    estado: str
    criado_em: str
    revisado_em: Optional[str]
    autorizado_em: Optional[str]
    aplicado_em: Optional[str]
    revisor: Optional[str]
    autorizador: Optional[str]
    hash_conteudo_autorizado: Optional[str]
    resultado_aplicacao: Optional[dict[str, Any]]
    erro: Optional[str]

    def contrato(self) -> ContratoCadastro:
        return ContratoCadastro.from_dict(json.loads(self.conteudo_json))


@dataclass(frozen=True)
class MapaAplicacao:
    proposta_id: str
    objeto_id: str
    tipo: str
    id_fisico: str
    disposicao: str
    identidade_logica: str
    lote: Optional[str]
    execucao_id: str


@dataclass(frozen=True)
class Checkpoint:
    checkpoint_id: str
    caminho_banco: Path
    arquivo_checkpoint: Path
    lote: Optional[str]
    manifesto_hash: str
    hash_banco: str
    estado_execucao: str
    criado_em: Optional[str] = None


class MigracaoAuditavelDB:
    """Repositório persistente e separado das propostas de migração JSON."""

    def __init__(
        self,
        caminho_db: Path | str = DEFAULT_DB,
        *,
        schema: Path | str = SCHEMA,
    ) -> None:
        self.caminho_db = Path(caminho_db)
        self.caminho_db.parent.mkdir(parents=True, exist_ok=True)
        self.schema = Path(schema)
        self._inicializar()

    def _conectar(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.caminho_db)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def _inicializar(self) -> None:
        with self._conectar() as conn:
            conn.executescript(self.schema.read_text(encoding="utf-8"))

    @staticmethod
    def _registro(linha: sqlite3.Row) -> PropostaPersistida:
        resultado = (
            json.loads(linha["resultado_aplicacao"])
            if linha["resultado_aplicacao"] is not None
            else None
        )
        return PropostaPersistida(
            proposta_id=str(linha["proposta_id"]),
            idempotencia=str(linha["idempotencia"]),
            hash_conteudo=str(linha["hash_conteudo"]),
            conteudo_json=str(linha["conteudo_json"]),
            versao_contrato=str(linha["versao_contrato"]),
            versao_mapeamento=str(linha["versao_mapeamento"]),
            lote=linha["lote"],
            origem=str(linha["origem"]),
            estado=str(linha["estado"]),
            criado_em=str(linha["criado_em"]),
            revisado_em=linha["revisado_em"],
            autorizado_em=linha["autorizado_em"],
            aplicado_em=linha["aplicado_em"],
            revisor=linha["revisor"],
            autorizador=linha["autorizador"],
            hash_conteudo_autorizado=linha["hash_conteudo_autorizado"],
            resultado_aplicacao=resultado,
            erro=linha["erro"],
        )

    def registrar_proposta(
        self,
        contrato: ContratoCadastro,
        *,
        versao_contrato: str = "1",
        versao_mapeamento: str = "1",
        lote: Optional[str] = None,
        origem: Optional[str] = None,
    ) -> PropostaPersistida:
        if not isinstance(contrato, ContratoCadastro):
            raise TypeError("contrato deve ser um ContratoCadastro")
        versao_contrato = _texto(versao_contrato, "versao_contrato") or ""
        versao_mapeamento = _texto(versao_mapeamento, "versao_mapeamento") or ""
        lote = _texto(lote, "lote", permitir_nulo=True)
        origem = _texto(origem or contrato.entrada, "origem") or ""
        conteudo_json, digest = hash_contrato(contrato)

        with self._conectar() as conn:
            por_id = conn.execute(
                "SELECT * FROM propostas_migracao WHERE proposta_id = ?",
                (contrato.proposta_id,),
            ).fetchone()
            if por_id is not None:
                atual = self._registro(por_id)
                metadados_diferentes = (
                    atual.idempotencia != contrato.idempotencia
                    or atual.versao_contrato != versao_contrato
                    or atual.versao_mapeamento != versao_mapeamento
                    or atual.lote != lote
                    or atual.origem != origem
                )
                if atual.hash_conteudo != digest or metadados_diferentes:
                    raise ValueError(
                        "proposta_id já está associado a conteúdo ou metadados diferentes"
                    )
                return atual

            por_idempotencia = conn.execute(
                "SELECT proposta_id FROM propostas_migracao "
                "WHERE idempotencia = ?",
                (contrato.idempotencia,),
            ).fetchone()
            if por_idempotencia is not None:
                raise ValueError(
                    "idempotência já está associada a outra proposta persistida"
                )

            conn.execute(
                """
                INSERT INTO propostas_migracao (
                    proposta_id, idempotencia, hash_conteudo, conteudo_json,
                    versao_contrato, versao_mapeamento, lote, origem, estado
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'proposta')
                """,
                (
                    contrato.proposta_id,
                    contrato.idempotencia,
                    digest,
                    conteudo_json,
                    versao_contrato,
                    versao_mapeamento,
                    lote,
                    origem,
                ),
            )
            linha = conn.execute(
                "SELECT * FROM propostas_migracao WHERE proposta_id = ?",
                (contrato.proposta_id,),
            ).fetchone()
            assert linha is not None
            return self._registro(linha)

    def obter(self, proposta_id: str) -> PropostaPersistida:
        with self._conectar() as conn:
            linha = conn.execute(
                "SELECT * FROM propostas_migracao WHERE proposta_id = ?",
                (proposta_id,),
            ).fetchone()
        if linha is None:
            raise LookupError(f"proposta persistida não encontrada: {proposta_id}")
        return self._registro(linha)

    def listar(self, *, estado: Optional[str] = None) -> tuple[PropostaPersistida, ...]:
        if estado is not None and estado not in ESTADOS_PROPOSTA:
            raise ValueError(f"estado de proposta desconhecido: {estado}")
        with self._conectar() as conn:
            if estado is None:
                linhas = conn.execute(
                    "SELECT * FROM propostas_migracao ORDER BY criado_em, proposta_id"
                ).fetchall()
            else:
                linhas = conn.execute(
                    "SELECT * FROM propostas_migracao "
                    "WHERE estado = ? ORDER BY criado_em, proposta_id",
                    (estado,),
                ).fetchall()
        return tuple(self._registro(linha) for linha in linhas)

    def iniciar_revisao(self, proposta_id: str, revisor: str) -> PropostaPersistida:
        revisor = _texto(revisor, "revisor") or ""
        return self._mudar_estado(
            proposta_id,
            estado_atual="proposta",
            novo_estado="em_revisao",
            campos=("revisor = ?", "revisado_em = CURRENT_TIMESTAMP"),
            valores=(revisor,),
        )

    def autorizar(
        self,
        proposta_id: str,
        autorizador: str,
    ) -> PropostaPersistida:
        autorizador = _texto(autorizador, "autorizador") or ""
        atual = self.obter(proposta_id)
        return self._mudar_estado(
            proposta_id,
            estado_atual="em_revisao",
            novo_estado="autorizada",
            campos=(
                "autorizador = ?",
                "autorizado_em = CURRENT_TIMESTAMP",
                "hash_conteudo_autorizado = ?",
                "erro = NULL",
            ),
            valores=(autorizador, atual.hash_conteudo),
        )

    def recusar(self, proposta_id: str, motivo: str) -> PropostaPersistida:
        motivo = _texto(motivo, "motivo") or ""
        return self._mudar_estado(
            proposta_id,
            estado_atual=None,
            novo_estado="recusada",
            campos=("erro = ?",),
            valores=(motivo,),
            estados_permitidos=("proposta", "em_revisao", "autorizada"),
        )

    def registrar_erro(
        self,
        proposta_id: str,
        erro: str,
        *,
        resultado: Optional[dict[str, Any]] = None,
    ) -> PropostaPersistida:
        erro = _texto(erro, "erro") or ""
        resultado_json = (
            _json_canonico(resultado) if resultado is not None else None
        )
        with self._conectar() as conn:
            conn.execute(
                "UPDATE propostas_migracao SET estado = 'erro', erro = ?, "
                "resultado_aplicacao = ? WHERE proposta_id = ?",
                (erro, resultado_json, proposta_id),
            )
            if conn.total_changes == 0:
                raise LookupError(f"proposta persistida não encontrada: {proposta_id}")
        return self.obter(proposta_id)

    def registrar_aplicacao(
        self,
        proposta_id: str,
        contrato: ContratoCadastro,
        resultado: dict[str, Any],
        *,
        lote: Optional[str],
        execucao_id: Optional[str] = None,
    ) -> PropostaPersistida:
        execucao_id = execucao_id or uuid4().hex
        registro = self.obter(proposta_id)
        if registro.hash_conteudo != hash_contrato(contrato)[1]:
            raise ValueError("contrato aplicado não corresponde ao hash persistido")
        if registro.estado == "aplicada":
            return registro
        if registro.estado != "autorizada":
            raise ValueError("somente proposta autorizada pode ser marcada como aplicada")

        objetos = {objeto.objeto_id: objeto for objeto in contrato.objetos}
        ids_por_objeto = {
            str(objeto_id): str(registro_id)
            for objeto_id, registro_id in resultado.get("ids_por_objeto", ())
        }
        reutilizados = {
            str(item) for item in resultado.get("registros_reutilizados", ())
        }

        with self._conectar() as conn:
            conn.execute(
                """
                UPDATE propostas_migracao
                SET estado = 'aplicada',
                    aplicado_em = CURRENT_TIMESTAMP,
                    resultado_aplicacao = ?,
                    erro = NULL
                WHERE proposta_id = ? AND estado = 'autorizada'
                """,
                (_json_canonico(resultado), proposta_id),
            )
            if conn.total_changes == 0:
                atual = conn.execute(
                    "SELECT estado FROM propostas_migracao WHERE proposta_id = ?",
                    (proposta_id,),
                ).fetchone()
                if atual is None:
                    raise LookupError(
                        f"proposta persistida não encontrada: {proposta_id}"
                    )
                if atual["estado"] == "aplicada":
                    return self.obter(proposta_id)
                raise ValueError("estado da proposta mudou durante a aplicação")

            for objeto_id, id_fisico in sorted(ids_por_objeto.items()):
                objeto = objetos[objeto_id]
                identidade = f"{objeto.tipo}:{objeto.chave}"
                disposicao = (
                    "reutilizado"
                    if identidade in reutilizados
                    else "criado"
                )
                conn.execute(
                    """
                    INSERT OR IGNORE INTO mapa_aplicacao_migracao (
                        proposta_id, objeto_id, tipo, id_fisico, disposicao,
                        identidade_logica, lote, execucao_id
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        proposta_id,
                        objeto_id,
                        objeto.tipo,
                        id_fisico,
                        disposicao,
                        identidade,
                        lote,
                        execucao_id,
                    ),
                )
        return self.obter(proposta_id)

    def listar_mapa(self, proposta_id: str) -> tuple[MapaAplicacao, ...]:
        with self._conectar() as conn:
            linhas = conn.execute(
                """
                SELECT proposta_id, objeto_id, tipo, id_fisico, disposicao,
                       identidade_logica, lote, execucao_id
                FROM mapa_aplicacao_migracao
                WHERE proposta_id = ?
                ORDER BY id
                """,
                (proposta_id,),
            ).fetchall()
        return tuple(
            MapaAplicacao(
                proposta_id=str(linha["proposta_id"]),
                objeto_id=str(linha["objeto_id"]),
                tipo=str(linha["tipo"]),
                id_fisico=str(linha["id_fisico"]),
                disposicao=str(linha["disposicao"]),
                identidade_logica=str(linha["identidade_logica"]),
                lote=linha["lote"],
                execucao_id=str(linha["execucao_id"]),
            )
            for linha in linhas
        )

    def registrar_checkpoint(self, checkpoint: Checkpoint) -> None:
        with self._conectar() as conn:
            conn.execute(
                """
                INSERT INTO checkpoints_migracao (
                    checkpoint_id, caminho_banco, arquivo_checkpoint, lote,
                    manifesto_hash, hash_banco, estado_execucao
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    checkpoint.checkpoint_id,
                    str(checkpoint.caminho_banco),
                    str(checkpoint.arquivo_checkpoint),
                    checkpoint.lote,
                    checkpoint.manifesto_hash,
                    checkpoint.hash_banco,
                    checkpoint.estado_execucao,
                ),
            )

    def obter_checkpoint(self, checkpoint_id: str) -> Checkpoint:
        with self._conectar() as conn:
            linha = conn.execute(
                "SELECT * FROM checkpoints_migracao WHERE checkpoint_id = ?",
                (checkpoint_id,),
            ).fetchone()
        if linha is None:
            raise LookupError(f"checkpoint não encontrado: {checkpoint_id}")
        return Checkpoint(
            checkpoint_id=str(linha["checkpoint_id"]),
            caminho_banco=Path(linha["caminho_banco"]),
            arquivo_checkpoint=Path(linha["arquivo_checkpoint"]),
            lote=linha["lote"],
            manifesto_hash=str(linha["manifesto_hash"]),
            hash_banco=str(linha["hash_banco"]),
            estado_execucao=str(linha["estado_execucao"]),
            criado_em=linha["criado_em"],
        )

    def _mudar_estado(
        self,
        proposta_id: str,
        *,
        estado_atual: Optional[str],
        novo_estado: str,
        campos: tuple[str, ...],
        valores: tuple[Any, ...],
        estados_permitidos: Optional[tuple[str, ...]] = None,
    ) -> PropostaPersistida:
        if novo_estado not in ESTADOS_PROPOSTA:
            raise ValueError(f"estado de proposta desconhecido: {novo_estado}")
        permitidos = estados_permitidos or (estado_atual,)
        if any(item is None for item in permitidos):
            raise ValueError("estado atual obrigatório")
        with self._conectar() as conn:
            linha = conn.execute(
                "SELECT estado FROM propostas_migracao WHERE proposta_id = ?",
                (proposta_id,),
            ).fetchone()
            if linha is None:
                raise LookupError(f"proposta persistida não encontrada: {proposta_id}")
            if str(linha["estado"]) not in permitidos:
                raise ValueError(
                    f"proposta está em estado incompatível: {linha['estado']}"
                )
            conn.execute(
                "UPDATE propostas_migracao SET estado = ?, "
                + ", ".join(campos)
                + " WHERE proposta_id = ?",
                (novo_estado, *valores, proposta_id),
            )
        return self.obter(proposta_id)


def _hash_arquivo(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as arquivo:
        for bloco in iter(lambda: arquivo.read(1024 * 1024), b""):
            digest.update(bloco)
    return digest.hexdigest()


def criar_checkpoint(
    caminho_db: Path | str,
    *,
    lote: Optional[str],
    manifesto_hash: str,
    estado_execucao: str,
    persistencia: MigracaoAuditavelDB,
    diretorio: Path | str = DEFAULT_CHECKPOINT_DIR,
    checkpoint_id: Optional[str] = None,
) -> Checkpoint:
    """Cria uma cópia SQLite consistente e registra sua identidade."""

    origem = Path(caminho_db)
    if not origem.exists():
        raise FileNotFoundError(f"banco para checkpoint não encontrado: {origem}")
    manifesto_hash = _texto(manifesto_hash, "manifesto_hash") or ""
    estado_execucao = _texto(estado_execucao, "estado_execucao") or ""
    pasta = Path(diretorio)
    pasta.mkdir(parents=True, exist_ok=True)
    checkpoint_id = checkpoint_id or uuid4().hex
    destino = pasta / f"{checkpoint_id}.sqlite"
    temporario = destino.with_suffix(".tmp")

    origem_conn = sqlite3.connect(
        f"file:{origem.resolve()}?mode=ro",
        uri=True,
    )
    destino_conn = sqlite3.connect(temporario)
    try:
        origem_conn.backup(destino_conn)
        destino_conn.commit()
    finally:
        destino_conn.close()
        origem_conn.close()
    os.replace(temporario, destino)

    checkpoint = Checkpoint(
        checkpoint_id=checkpoint_id,
        caminho_banco=origem.resolve(),
        arquivo_checkpoint=destino.resolve(),
        lote=lote,
        manifesto_hash=manifesto_hash,
        hash_banco=_hash_arquivo(destino),
        estado_execucao=estado_execucao,
    )
    persistencia.registrar_checkpoint(checkpoint)
    return persistencia.obter_checkpoint(checkpoint_id)


def restaurar_checkpoint(
    checkpoint: Checkpoint,
    destino_db: Path | str,
    *,
    confirmar_substituicao: bool = False,
) -> Path:
    """Restaura explicitamente um checkpoint, nunca por chamada implícita."""

    if not confirmar_substituicao:
        raise PermissionError(
            "restauração destrutiva exige confirmar_substituicao=True"
        )
    origem = Path(checkpoint.arquivo_checkpoint)
    destino = Path(destino_db)
    if not origem.exists():
        raise FileNotFoundError(f"arquivo de checkpoint não encontrado: {origem}")
    destino.parent.mkdir(parents=True, exist_ok=True)
    fd, nome_temporario = tempfile.mkstemp(
        prefix=f".{destino.name}.restore-",
        suffix=".tmp",
        dir=destino.parent,
    )
    os.close(fd)
    temporario = Path(nome_temporario)
    origem_conn = sqlite3.connect(
        f"file:{origem.resolve()}?mode=ro",
        uri=True,
    )
    destino_conn = sqlite3.connect(temporario)
    try:
        origem_conn.backup(destino_conn)
        destino_conn.commit()
    finally:
        destino_conn.close()
        origem_conn.close()
    os.replace(temporario, destino)
    return destino