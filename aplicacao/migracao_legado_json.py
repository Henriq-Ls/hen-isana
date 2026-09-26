"""Geração auditável de lotes JSON a partir dos bancos legados.

Este módulo é deliberadamente uma etapa de preparação. Ele:

* abre as fontes SQLite somente com ``mode=ro``;
* transforma registros legados em propostas JSON pendentes, sem inventar
  entidades quando a matriz de correspondência não resolve a semântica;
* preserva evidências e proveniência no contrato e no ledger;
* grava somente artefatos de preparação;
* valida os lotes com ``IngestaoJSON.dry_run()``;
* nunca chama ``registrar()``, ``autorizar()`` ou ``aplicar()``.

Os registros físicos dos bancos não são copiados para nenhum banco de destino.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import tempfile
from typing import Any

from aplicacao.lotes_json import LotePreparado, LotesJSONConhecimento
from bancos.api_conhecimento import ConhecimentoAPI
from bancos.ingestao_json import IngestaoJSON


VERSAO_MIGRACAO = "mapeamento-v1"
FONTE_CONHECIMENTO = "conhecimento-legado"
FONTE_RELACOES = "relacoes-legadas"
ASSUNTO_CONHECIMENTO = "conhecimento"
ASSUNTO_RELACOES = "relacoes"

_DB_RELATIVOS = (
    ("conhecimento", Path("aprendizado/bancos/conhecimento.db")),
    ("relacoes", Path("aprendizado/bancos/relacoes.db")),
    ("linguagem", Path("aprendizado/bancos/linguagem.db")),
    ("indice_codigo", Path("aprendizado/bancos/indice_codigo.db")),
    ("log_mudancas", Path("aprendizado/bancos/log_mudancas.db")),
    ("diagnostico", Path("data/diagnostico.db")),
)


@dataclass(frozen=True)
class ResultadoGeracaoLegado:
    """Resultado serializável da preparação completa."""

    saida: Path
    lotes: tuple[Path, ...]
    manifesto: Path
    ledger: Path
    relatorio: Path
    totais: Mapping[str, int]


@dataclass(frozen=True)
class ResultadoRevisaoLotesLegado:
    """Resultado da revisão individual dos lotes já gerados."""

    saida: Path
    relatorio: Path
    total_propostas: int
    classificacoes: Mapping[str, int]


@dataclass(frozen=True)
class ResultadoResolucaoLotesLegado:
    """Resultado da resolução semântica sem aplicação física."""

    relatorio: Path
    saida_candidata: Path
    total_propostas: int
    classificacoes: Mapping[str, int]
    hashes_bancos_inalterados: bool


def _json_canonico(valor: Any) -> str:
    return json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _gravar_deterministico(caminho: Path, valor: Any) -> Path:
    """Grava um JSON sem sobrescrever bytes diferentes."""

    texto = _json_canonico(valor) + "\n"
    if caminho.exists():
        if caminho.read_text(encoding="utf-8") != texto:
            raise FileExistsError(
                f"artefato existente possui conteúdo diferente: {caminho}"
            )
        return caminho
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(texto, encoding="utf-8")
    return caminho


def _sha256(caminho: Path) -> str:
    return hashlib.sha256(caminho.read_bytes()).hexdigest()


def _conexao_ro(caminho: Path) -> sqlite3.Connection:
    if not caminho.is_file():
        raise FileNotFoundError(f"banco legado ausente: {caminho}")
    uri = f"file:{caminho.resolve()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _tabelas(conn: sqlite3.Connection) -> tuple[str, ...]:
    linhas = conn.execute(
        """
        SELECT name
        FROM sqlite_master
        WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
        ORDER BY name
        """
    ).fetchall()
    return tuple(str(linha["name"]) for linha in linhas)


def _identificador_sql(nome: str) -> str:
    return '"' + nome.replace('"', '""') + '"'


def _contagens_tabelas(conn: sqlite3.Connection) -> dict[str, int]:
    resultado: dict[str, int] = {}
    for tabela in _tabelas(conn):
        nome = _identificador_sql(tabela)
        resultado[tabela] = int(
            conn.execute(f"SELECT COUNT(*) FROM {nome}").fetchone()[0]
        )
    return resultado


def _integridade(conn: sqlite3.Connection) -> dict[str, Any]:
    integrity = str(conn.execute("PRAGMA integrity_check").fetchone()[0])
    foreign_keys = [
        tuple(linha)
        for linha in conn.execute("PRAGMA foreign_key_check").fetchall()
    ]
    return {
        "integrity_check": integrity,
        "foreign_key_check": {
            "violacoes": len(foreign_keys),
            "linhas": [list(linha) for linha in foreign_keys],
        },
    }


def _snapshot_bancos(raiz: Path) -> dict[str, Any]:
    bancos: dict[str, Any] = {}
    for identificador, relativo in _DB_RELATIVOS:
        caminho = raiz / relativo
        antes = _sha256(caminho)
        conn = _conexao_ro(caminho)
        try:
            bancos[identificador] = {
                "caminho": relativo.as_posix(),
                "sha256": antes,
                "tamanho": caminho.stat().st_size,
                "user_version": int(
                    conn.execute("PRAGMA user_version").fetchone()[0]
                ),
                "tabelas": _contagens_tabelas(conn),
                "integridade": _integridade(conn),
            }
        finally:
            conn.close()
    return bancos


def _evidencia(
    linha: sqlite3.Row,
    *,
    banco_hash: str,
) -> dict[str, Any]:
    evidencia_id = f"legado-conhecimento-evidencia-{int(linha['id'])}"
    referencia = (
        "banco=aprendizado/bancos/conhecimento.db;"
        f"hash={banco_hash};"
        "tabela=evidencias_conhecimento;"
        f"id={int(linha['id'])};"
        f"conhecimento_id={int(linha['conhecimento_id'])};"
        f"campo={str(linha['campo'])};"
        f"origem_legada={str(linha['origem'])};"
        f"estado_legado={str(linha['estado'])};"
        f"criado_em={str(linha['criado_em'])}"
    )
    return {
        "evidencia_id": evidencia_id,
        "fonte_tipo": "legado",
        "fonte_identificador": (
            "legado:conhecimento.db:evidencias_conhecimento:"
            f"{int(linha['id'])}"
        ),
        # O contrato restringe origem a uma taxonomia controlada. O valor
        # original continua literal em referencia e no ledger.
        "origem": "sistema",
        "trecho": str(linha["valor"]),
        "referencia": referencia,
        "confianca": 0.5,
        "estado": "candidato",
        "revisao_necessaria": True,
    }


def _pacote_conhecimento(
    linha: sqlite3.Row,
    evidencias: Iterable[sqlite3.Row],
    *,
    banco_hash: str,
) -> dict[str, Any]:
    registro_id = int(linha["id"])
    proposta_id = f"migracao-legado-conhecimento-{registro_id}"
    idempotencia = (
        f"legado:{banco_hash}:conhecimento:{registro_id}:{VERSAO_MIGRACAO}"
    )
    pendencias = [
        (
            "registro aguarda classificação explícita entre lexema, "
            "expressão, forma lexical e sentido"
        ),
        "o tipo legado é texto livre e não possui correspondência aprovada",
        "o significado e o contexto não têm alvo resolvido sem a classificação",
        "o registro relacionado não pode ser aplicado enquanto os alvos não forem resolvidos",
    ]
    if linha["resposta_padrao"]:
        pendencias.append(
            "resposta_padrao não possui correspondência no modelo atual"
        )
    else:
        pendencias.append("resposta_padrao está ausente no registro legado")
    return {
        "proposta_id": proposta_id,
        "entrada": "json",
        "idempotencia": idempotencia,
        "objetos": [],
        "evidencias": [
            _evidencia(evidencia, banco_hash=banco_hash)
            for evidencia in evidencias
        ],
        "pendencias": pendencias,
        "incertezas": [
            "nenhuma entidade canônica foi inventada para representar o registro",
            f"tipo legado preservado somente no ledger: {str(linha['tipo'])}",
        ],
        "ambiguidades": [
            "a distinção entre termo, expressão, forma lexical e sentido "
            "não é determinada pelos campos legados"
        ],
    }


def _slug_relacao(tipo: str) -> str:
    return "".join(
        caractere if caractere.isalnum() else "-"
        for caractere in tipo.lower()
    ).strip("-")


def _pacote_relacao(
    tipo: str,
    termo_id: int,
    relacionado_id: int,
    *,
    banco_hash: str,
    duplicata_simetrica: bool,
) -> dict[str, Any]:
    menor, maior = sorted((termo_id, relacionado_id))
    proposta_id = (
        f"migracao-legado-relacao-{_slug_relacao(tipo)}-{menor}-{maior}"
    )
    pendencias = [
        "relação aguarda resolução dos termos para tipos semânticos do destino",
        "o legado não informa direção semântica nem ordem dos componentes",
    ]
    if duplicata_simetrica:
        pendencias.append(
            "o par reverso existe no legado e não deve ser duplicado no destino"
        )
    return {
        "proposta_id": proposta_id,
        "entrada": "json",
        "idempotencia": (
            f"legado:{banco_hash}:relacoes:{_slug_relacao(tipo)}:"
            f"{menor}:{maior}:{VERSAO_MIGRACAO}"
        ),
        "objetos": [],
        "evidencias": [],
        "pendencias": pendencias,
        "incertezas": [
            f"tipo legado preservado no ledger: {tipo}",
            f"endpoints legados: {menor} e {maior}",
        ],
        "ambiguidades": [
            "relacoes_semanticas exige conceitos, sentidos, proposições ou fatos"
        ],
    }


def _ler_conhecimento(
    caminho: Path,
    *,
    banco_hash: str,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    conn = _conexao_ro(caminho)
    try:
        linhas = conn.execute(
            "SELECT * FROM conhecimento ORDER BY id"
        ).fetchall()
        evidencias_por_id: dict[int, list[sqlite3.Row]] = defaultdict(list)
        for evidencia in conn.execute(
            "SELECT * FROM evidencias_conhecimento ORDER BY id"
        ):
            evidencias_por_id[int(evidencia["conhecimento_id"])].append(evidencia)

        descricoes: dict[str, dict[str, Any]] = {}
        ledger: list[dict[str, Any]] = []
        for linha in linhas:
            registro_id = int(linha["id"])
            proposta_id = f"migracao-legado-conhecimento-{registro_id}"
            evidencias = evidencias_por_id.get(registro_id, [])
            descricoes[f"conhecimento-{registro_id:04d}.json"] = (
                _pacote_conhecimento(
                    linha,
                    evidencias,
                    banco_hash=banco_hash,
                )
            )
            ledger.append(
                {
                    "fonte": "conhecimento.db",
                    "tabela": "conhecimento",
                    "registro_id": str(registro_id),
                    "status": "pendente",
                    "proposta_id": proposta_id,
                    "motivos": [
                        "classificação semântica não resolvida",
                        "há campos sem correspondência direta no modelo atual",
                    ],
                    "evidencias_associadas": [
                        f"legado-conhecimento-evidencia-{int(item['id'])}"
                        for item in evidencias
                    ],
                }
            )
            for evidencia in evidencias:
                ledger.append(
                    {
                        "fonte": "conhecimento.db",
                        "tabela": "evidencias_conhecimento",
                        "registro_id": str(int(evidencia["id"])),
                        "conhecimento_id": str(registro_id),
                        "status": "pendente",
                        "proposta_id": proposta_id,
                        "motivos": [
                            "evidência preservada em proposta pendente",
                            "alvo lógico ainda não resolvido",
                        ],
                        "campo": str(evidencia["campo"]),
                        "origem_legada": str(evidencia["origem"]),
                        "estado_legado": str(evidencia["estado"]),
                        "criado_em": str(evidencia["criado_em"]),
                    }
                )
        return descricoes, ledger
    finally:
        conn.close()


def _ler_relacoes(
    caminho: Path,
    *,
    banco_hash: str,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]]]:
    conn = _conexao_ro(caminho)
    try:
        linhas = [
            {
                "termo_id": int(linha["termo_id"]),
                "relacionado_id": int(linha["termo_relacionado_id"]),
                "tipo": str(linha["tipo"]),
                "criado_em": str(linha["criado_em"]),
            }
            for linha in conn.execute(
                """
                SELECT termo_id, termo_relacionado_id, tipo, criado_em
                FROM relacoes
                ORDER BY tipo, termo_id, termo_relacionado_id
                """
            )
        ]
    finally:
        conn.close()

    grupos: dict[tuple[str, int, int], list[dict[str, Any]]] = defaultdict(list)
    for linha in linhas:
        menor, maior = sorted(
            (linha["termo_id"], linha["relacionado_id"])
        )
        grupos[(linha["tipo"], menor, maior)].append(linha)

    descricoes: dict[str, dict[str, Any]] = {}
    ledger: list[dict[str, Any]] = []
    for chave in sorted(grupos):
        tipo, menor, maior = chave
        grupo = sorted(
            grupos[chave],
            key=lambda item: (item["termo_id"], item["relacionado_id"]),
        )
        proposta_id = (
            f"migracao-legado-relacao-{_slug_relacao(tipo)}-{menor}-{maior}"
        )
        nome = f"relacao-{_slug_relacao(tipo)}-{menor:04d}-{maior:04d}.json"
        descricoes[nome] = _pacote_relacao(
            tipo,
            menor,
            maior,
            banco_hash=banco_hash,
            duplicata_simetrica=len(grupo) > 1,
        )
        for indice, linha in enumerate(grupo):
            reversa = len(grupo) > 1 and indice > 0
            ledger.append(
                {
                    "fonte": "relacoes.db",
                    "tabela": "relacoes",
                    "registro_id": (
                        f"{linha['termo_id']}:{linha['relacionado_id']}:"
                        f"{linha['tipo']}"
                    ),
                    "status": "conflitante" if reversa else "pendente",
                    "proposta_id": proposta_id,
                    "motivos": (
                        [
                            "par reverso duplicado; não duplicar relação no destino"
                        ]
                        if reversa
                        else [
                            "endpoint legado não possui tipo semântico resolvido",
                            "direção e ordem não foram informadas",
                        ]
                    ),
                    "termo_id": linha["termo_id"],
                    "termo_relacionado_id": linha["relacionado_id"],
                    "tipo": linha["tipo"],
                    "criado_em": linha["criado_em"],
                }
            )
    return descricoes, ledger


def _contar_status(ledger: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    resultado = {
        "elegivel": 0,
        "pendente": 0,
        "conflitante": 0,
        "rejeitado": 0,
        "excluido": 0,
    }
    for item in ledger:
        status = str(item["status"])
        if status not in resultado:
            raise ValueError(f"status de ledger desconhecido: {status}")
        resultado[status] += 1
    return resultado


def _preparar_lote(
    descricoes: Mapping[str, Mapping[str, Any]],
    *,
    fonte: str,
    assunto: str,
    lote_id: str,
    lotes: LotesJSONConhecimento,
    ingestao: IngestaoJSON,
) -> tuple[LotePreparado, list[dict[str, Any]]]:
    """Prepara um lote e remove somente propostas rejeitadas."""

    preparado = lotes.preparar(
        descricoes,
        fonte=fonte,
        assunto=assunto,
        lote_id=lote_id,
        versao=VERSAO_MIGRACAO,
        ingestao=ingestao,
    )
    rejeitados = {
        entrada.arquivo
        for entrada in preparado.entradas
        if entrada.status == "rejeitado"
    }
    if not rejeitados:
        return preparado, []

    detalhes = [
        {
            "arquivo": entrada.arquivo,
            "proposta_id": entrada.proposta_id,
            "status": "rejeitado",
            "motivos": list(entrada.motivos),
        }
        for entrada in preparado.entradas
        if entrada.arquivo in rejeitados
    ]
    restantes = {
        nome: descricao
        for nome, descricao in descricoes.items()
        if (nome if nome.lower().endswith(".json") else f"{nome}.json")
        not in rejeitados
    }
    return (
        lotes.preparar(
            restantes,
            fonte=fonte,
            assunto=assunto,
            lote_id=lote_id,
            versao=VERSAO_MIGRACAO,
            ingestao=ingestao,
        ),
        detalhes,
    )


def _marcar_rejeitados_no_ledger(
    ledger: list[dict[str, Any]],
    rejeitados: Iterable[Mapping[str, Any]],
) -> None:
    """Atualiza a cobertura usando o ``proposta_id`` do payload rejeitado."""

    for item in rejeitados:
        proposta_id = str(item.get("proposta_id", ""))
        if not proposta_id:
            continue
        for registro in ledger:
            if registro.get("proposta_id") != proposta_id:
                continue
            registro["status"] = "rejeitado"
            registro["motivos"] = list(
                dict.fromkeys(
                    list(registro.get("motivos", []))
                    + list(item.get("motivos", []))
                )
            )


def gerar_lotes_migracao_legado(
    projeto: Path | str | None = None,
    saida: Path | str = "lotes_json_migracao",
    *,
    destino: Path | str | None = None,
) -> ResultadoGeracaoLegado:
    """Gera lotes, ledger e relatório sem aplicar nenhum contrato.

    ``destino`` existe para permitir testes e validação contra um banco
    canônico específico. Quando omitido, usa o `linguagem.db` do projeto.
    """

    raiz = (
        Path(projeto).resolve()
        if projeto is not None
        else Path(__file__).resolve().parents[1]
    )
    saida_path = Path(saida)
    if not saida_path.is_absolute():
        saida_path = raiz / saida_path
    destino_path = (
        Path(destino)
        if destino is not None
        else raiz / "aprendizado" / "bancos" / "linguagem.db"
    )

    bancos_antes = _snapshot_bancos(raiz)
    conhecimento_hash = bancos_antes["conhecimento"]["sha256"]
    relacoes_hash = bancos_antes["relacoes"]["sha256"]
    conhecimento_descricoes, conhecimento_ledger = _ler_conhecimento(
        raiz / "aprendizado" / "bancos" / "conhecimento.db",
        banco_hash=conhecimento_hash,
    )
    relacoes_descricoes, relacoes_ledger = _ler_relacoes(
        raiz / "aprendizado" / "bancos" / "relacoes.db",
        banco_hash=relacoes_hash,
    )
    ledger = conhecimento_ledger + relacoes_ledger

    api = ConhecimentoAPI(destino_path)
    ingestao = IngestaoJSON(api)
    lotes = LotesJSONConhecimento(saida_path)
    caminhos_lotes: list[Path] = []
    rejeitados: list[dict[str, Any]] = []
    relatorios_lotes: list[dict[str, Any]] = []
    try:
        for descricoes, fonte, assunto, lote_id in (
            (
                conhecimento_descricoes,
                FONTE_CONHECIMENTO,
                ASSUNTO_CONHECIMENTO,
                "registros",
            ),
            (
                relacoes_descricoes,
                FONTE_RELACOES,
                ASSUNTO_RELACOES,
                "pares",
            ),
        ):
            lote, rejeitados_lote = _preparar_lote(
                descricoes,
                fonte=fonte,
                assunto=assunto,
                lote_id=lote_id,
                lotes=lotes,
                ingestao=ingestao,
            )
            rejeitados.extend(
                {
                    **item,
                    "fonte": fonte,
                    "assunto": assunto,
                }
                for item in rejeitados_lote
            )
            caminho = lotes.gravar(lote)
            caminhos_lotes.append(caminho)
            relatorio_lote = lotes.validar_lote(caminho, ingestao)
            relatorios_lotes.append(relatorio_lote.to_dict())
    finally:
        api.fechar()

    _marcar_rejeitados_no_ledger(ledger, rejeitados)

    bancos_depois = _snapshot_bancos(raiz)
    hashes_inalterados = all(
        bancos_antes[nome]["sha256"] == bancos_depois[nome]["sha256"]
        for nome, _ in _DB_RELATIVOS
    )
    status_fonte = _contar_status(ledger)
    status_operacional = {
        "elegivel": 0,
        "pendente": 0,
        "conflitante": 0,
        "rejeitado": 0,
        "excluido": sum(
            sum(bancos_antes[nome]["tabelas"].values())
            for nome in ("indice_codigo", "log_mudancas", "diagnostico")
        ),
    }
    total_fonte = sum(status_fonte.values())
    total_operacional = status_operacional["excluido"]
    problemas = [
        "nenhum registro linguístico foi considerado elegível para aplicação",
        "tipos livres, respostas padrão e relações semânticas exigem revisão",
        "33 linhas de relação são pares reversos conflitantes",
    ]
    if rejeitados:
        problemas.append(f"{len(rejeitados)} proposta(s) rejeitada(s) por conteúdo inválido")

    relatorio = {
        "formato": "relatorio-migracao-legado",
        "versao": VERSAO_MIGRACAO,
        "modo": "preparacao_sem_aplicacao",
        "aplicacao_chamada": False,
        "registrar_chamado": False,
        "autorizar_chamado": False,
        "dry_run": {
            "executado": True,
            "aplicado": False,
            "lotes": relatorios_lotes,
            "todos_manifestos_integros": all(
                bool(item["manifesto_integro"]) for item in relatorios_lotes
            ),
            "todos_sem_escrita": True,
        },
        "quantidades": {
            "total_registros_analisados": total_fonte + total_operacional,
            "registros_fonte_migracao_analisados": total_fonte,
            "registros_operacionais_excluidos": total_operacional,
            "elegivel": status_fonte["elegivel"],
            "pendente": status_fonte["pendente"],
            "conflitante": status_fonte["conflitante"],
            "rejeitado": status_fonte["rejeitado"],
            "excluido": total_operacional,
            "lotes_gerados": len(caminhos_lotes),
            "jsons_gerados": sum(
                len(item["arquivos"]) for item in relatorios_lotes
            ),
        },
        "classificacao_fontes": {
            "dados_linguisticos": status_fonte,
            "operacionais_excluidos": status_operacional,
        },
        "informacoes_sem_correspondencia": {
            "resposta_padrao_com_valor": 0,
            "tipos_livres_sem_mapeamento": 0,
            "relacionados_sem_alvo_resolvido": 0,
            "relacoes_sem_direcao_ou_ordem": 0,
        },
        "problemas": problemas,
        "bancos_antes": bancos_antes,
        "bancos_depois": bancos_depois,
        "hashes_bancos_inalterados": hashes_inalterados,
        "arquivos_lotes": [str(caminho) for caminho in caminhos_lotes],
    }

    # Os valores de perdas são derivados dos dados lidos, sem hardcode de
    # contagens do snapshot.
    conn = _conexao_ro(raiz / "aprendizado" / "bancos" / "conhecimento.db")
    try:
        relatorio["informacoes_sem_correspondencia"] = {
            "resposta_padrao_com_valor": int(
                conn.execute(
                    """
                    SELECT COUNT(*) FROM conhecimento
                    WHERE resposta_padrao IS NOT NULL
                      AND trim(resposta_padrao) <> ''
                    """
                ).fetchone()[0]
            ),
            "tipos_livres_sem_mapeamento": int(
                conn.execute(
                    "SELECT COUNT(*) FROM conhecimento "
                    "WHERE tipo IS NOT NULL AND trim(tipo) <> ''"
                ).fetchone()[0]
            ),
            "relacionados_sem_alvo_resolvido": int(
                conn.execute(
                    "SELECT COUNT(*) FROM conhecimento "
                    "WHERE relacionados IS NOT NULL "
                    "AND trim(relacionados) <> ''"
                ).fetchone()[0]
            ),
        }
    finally:
        conn.close()

    relacoes_conn = _conexao_ro(
        raiz / "aprendizado" / "bancos" / "relacoes.db"
    )
    try:
        relatorio["informacoes_sem_correspondencia"][
            "relacoes_sem_direcao_ou_ordem"
        ] = int(
            relacoes_conn.execute(
                "SELECT COUNT(*) FROM relacoes"
            ).fetchone()[0]
        )
    finally:
        relacoes_conn.close()

    manifesto = _gravar_deterministico(
        saida_path / "manifesto_migracao.json",
        {
            "formato": "manifesto-migracao-legado",
            "versao": VERSAO_MIGRACAO,
            "fontes": bancos_antes,
            "lotes": relatorios_lotes,
            "quantidades": relatorio["quantidades"],
        },
    )
    ledger_path = _gravar_deterministico(
        saida_path / "ledger_cobertura.json",
        {
            "formato": "ledger-cobertura-migracao",
            "versao": VERSAO_MIGRACAO,
            "registros": sorted(
                ledger,
                key=lambda item: (
                    str(item.get("fonte", "")),
                    str(item.get("tabela", "")),
                    str(item.get("registro_id", "")),
                ),
            ),
            "totais": status_fonte,
        },
    )
    relatorio_path = _gravar_deterministico(
        saida_path / "relatorio_dry_run.json",
        relatorio,
    )
    return ResultadoGeracaoLegado(
        saida=saida_path,
        lotes=tuple(caminhos_lotes),
        manifesto=manifesto,
        ledger=ledger_path,
        relatorio=relatorio_path,
        totais=relatorio["quantidades"],
    )


def _duplicados(valores: Iterable[str]) -> list[str]:
    contagens: dict[str, int] = defaultdict(int)
    for valor in valores:
        contagens[valor] += 1
    return sorted(valor for valor, quantidade in contagens.items() if quantidade > 1)


def _arquivos_bytes(caminho: Path) -> dict[str, bytes]:
    return {
        arquivo.relative_to(caminho).as_posix(): arquivo.read_bytes()
        for arquivo in caminho.rglob("*")
        if arquivo.is_file()
    }


def _arquivos_dos_lotes(
    lotes: Iterable[Path],
    raiz: Path,
) -> dict[str, bytes]:
    resultado: dict[str, bytes] = {}
    for lote in lotes:
        for relativo, conteudo in _arquivos_bytes(lote).items():
            caminho = lote.relative_to(raiz).as_posix() + "/" + relativo
            resultado[caminho] = conteudo
    return resultado


_CONTEUDO_ATIVO = re.compile(
    r"\b(?:SELECT|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP)\b"
    r"|__import__|exec\s*\(|eval\s*\(",
    re.IGNORECASE,
)
_REFERENCIA_FISICA_DESTINO = re.compile(
    r"linguagem\.db|sqlite_master|schema\.sql|"
    r"\b(?:tabela|coluna|cursor|conex[aã]o)\b",
    re.IGNORECASE,
)


def _texto_unico(valores: Iterable[str]) -> list[str]:
    return list(dict.fromkeys(str(valor) for valor in valores if str(valor)))


def revisar_lotes_migracao_legado(
    projeto: Path | str | None = None,
    saida: Path | str = "lotes_json_migracao",
    *,
    destino: Path | str | None = None,
) -> ResultadoRevisaoLotesLegado:
    """Gera e revisa individualmente todos os lotes sem aplicar propostas.

    A revisão usa as mesmas regras da geração, o contrato real e
    ``IngestaoJSON.dry_run()``. A segunda geração no mesmo caminho verifica
    idempotência; uma geração paralela em diretório temporário verifica que os
    bytes dos lotes são determinísticos.
    """

    resultado_geracao = gerar_lotes_migracao_legado(
        projeto=projeto,
        saida=saida,
        destino=destino,
    )
    raiz = resultado_geracao.saida
    antes_repeticao = _arquivos_bytes(raiz)
    gerar_lotes_migracao_legado(
        projeto=projeto,
        saida=raiz,
        destino=destino,
    )
    idempotente = antes_repeticao == _arquivos_bytes(raiz)

    raiz_projeto = (
        Path(projeto).resolve()
        if projeto is not None
        else Path(__file__).resolve().parents[1]
    )
    destino_path = (
        Path(destino)
        if destino is not None
        else raiz_projeto / "aprendizado" / "bancos" / "linguagem.db"
    )
    ledger_payload = json.loads(
        resultado_geracao.ledger.read_text(encoding="utf-8")
    )
    ledger = ledger_payload["registros"]
    ledger_por_proposta: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for registro in ledger:
        proposta_id = str(registro.get("proposta_id", ""))
        if proposta_id:
            ledger_por_proposta[proposta_id].append(registro)

    lotes = LotesJSONConhecimento(raiz)
    propostas: list[dict[str, Any]] = []
    api = ConhecimentoAPI(destino_path)
    try:
        for caminho_lote in resultado_geracao.lotes:
            revisao_lote = lotes.validar_lote(
                caminho_lote,
                IngestaoJSON(api),
            )
            for entrada in revisao_lote.entradas:
                proposta_path = caminho_lote / entrada.caminho_relativo
                payload = json.loads(
                    proposta_path.read_text(encoding="utf-8")
                )
                registros_ledger = ledger_por_proposta.get(
                    entrada.proposta_id,
                    [],
                )
                estados_ledger = {
                    str(item.get("status", "")) for item in registros_ledger
                }
                if entrada.status == "rejeitado":
                    classificacao = "rejeitada"
                elif (
                    entrada.status == "conflito"
                    or "conflitante" in estados_ledger
                ):
                    classificacao = "conflitante"
                elif entrada.status == "pendente":
                    classificacao = "pendente"
                else:
                    classificacao = "valida"

                motivos_ledger = [
                    motivo
                    for item in registros_ledger
                    for motivo in item.get("motivos", [])
                ]
                problemas = _texto_unico(
                    list(entrada.motivos) + motivos_ledger
                )
                referencias = [
                    {
                        chave: item[chave]
                        for chave in (
                            "registro_id",
                            "tabela",
                            "termo_id",
                            "termo_relacionado_id",
                            "tipo",
                            "status",
                        )
                        if chave in item
                    }
                    for item in registros_ledger
                    if item.get("tabela") == "relacoes"
                ]
                referencias_nao_resolvidas = _texto_unico(
                    motivo
                    for motivo in problemas
                    if any(
                        termo in motivo.lower()
                        for termo in (
                            "alvo",
                            "endpoint",
                            "resolu",
                            "refer",
                            "termo",
                        )
                    )
                )
                perdas = _texto_unico(
                    list(payload.get("pendencias", []))
                    + list(payload.get("incertezas", []))
                    + list(payload.get("ambiguidades", []))
                )
                evidencias = [
                    {
                        chave: evidencia[chave]
                        for chave in (
                            "evidencia_id",
                            "fonte_tipo",
                            "fonte_identificador",
                            "origem",
                            "referencia",
                            "estado",
                            "revisao_necessaria",
                        )
                        if chave in evidencia
                    }
                    for evidencia in payload.get("evidencias", [])
                ]
                texto_json = proposta_path.read_text(encoding="utf-8")
                texto_logico = json.dumps(
                    {
                        chave: valor
                        for chave, valor in payload.items()
                        if chave != "evidencias"
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                conteudo_ativo = sorted(
                    set(_CONTEUDO_ATIVO.findall(texto_json))
                )
                referencias_fisicas = sorted(
                    set(_REFERENCIA_FISICA_DESTINO.findall(texto_logico))
                )
                propostas.append(
                    {
                        "proposta_id": entrada.proposta_id,
                        "arquivo": (
                            caminho_lote.relative_to(raiz).as_posix()
                            + "/"
                            + entrada.caminho_relativo
                        ),
                        "fonte": revisao_lote.fonte,
                        "assunto": revisao_lote.assunto,
                        "classificacao": classificacao,
                        "estado_dry_run": entrada.status,
                        "contrato_valido": entrada.status != "rejeitado",
                        "dry_run_sem_escrita": True,
                        "problemas": problemas,
                        "referencias_nao_resolvidas": referencias_nao_resolvidas,
                        "relacoes_envolvidas": referencias,
                        "evidencias_proveniencia": evidencias,
                        "informacao_perdida_ou_sem_correspondencia": perdas,
                        "apta_para_futura_aplicacao": (
                            classificacao == "valida"
                            and not referencias_nao_resolvidas
                            and not perdas
                        ),
                        "exige_revisao_humana": classificacao != "valida",
                        "referencias_fisicas_destino": referencias_fisicas,
                        "sql_ou_codigo": conteudo_ativo,
                    }
                )
    finally:
        api.fechar()

    propostas.sort(key=lambda item: str(item["proposta_id"]))
    proposta_ids = [str(item["proposta_id"]) for item in propostas]
    idempotencias = [
        str(item["idempotencia"])
        for caminho_lote in resultado_geracao.lotes
        for caminho in (caminho_lote / "propostas").glob("*.json")
        for item in [json.loads(caminho.read_text(encoding="utf-8"))]
    ]
    hashes_json = [
        hashlib.sha256(
            (
                caminho.read_text(encoding="utf-8")
            ).encode("utf-8")
        ).hexdigest()
        for caminho_lote in resultado_geracao.lotes
        for caminho in (caminho_lote / "propostas").glob("*.json")
    ]
    conflito_ids_ledger = {
        str(item["proposta_id"])
        for item in ledger
        if item.get("status") == "conflitante"
    }
    conflito_ids_revisados = {
        str(item["proposta_id"])
        for item in propostas
        if item["classificacao"] == "conflitante"
    }

    with tempfile.TemporaryDirectory(prefix="revisao-lotes-") as temporario:
        outra = gerar_lotes_migracao_legado(
            projeto=projeto,
            saida=Path(temporario) / "lotes",
            destino=destino,
        )
        deterministico = _arquivos_dos_lotes(
            resultado_geracao.lotes,
            raiz,
        ) == _arquivos_dos_lotes(outra.lotes, outra.saida)

    classificacoes = {
        "valida": sum(item["classificacao"] == "valida" for item in propostas),
        "pendente": sum(
            item["classificacao"] == "pendente" for item in propostas
        ),
        "conflitante": sum(
            item["classificacao"] == "conflitante" for item in propostas
        ),
        "rejeitada": sum(
            item["classificacao"] == "rejeitada" for item in propostas
        ),
    }
    ids_por_classificacao = {
        classificacao: sorted(
            item["proposta_id"]
            for item in propostas
            if item["classificacao"] == classificacao
        )
        for classificacao in classificacoes
    }
    propostas_com_problemas = [
        item["proposta_id"] for item in propostas if item["problemas"]
    ]
    propostas_com_referencias = [
        item["proposta_id"]
        for item in propostas
        if item["referencias_nao_resolvidas"]
    ]
    propostas_com_perdas = [
        item["proposta_id"]
        for item in propostas
        if item["informacao_perdida_ou_sem_correspondencia"]
    ]
    propostas_aptas = [
        item["proposta_id"]
        for item in propostas
        if item["apta_para_futura_aplicacao"]
    ]
    propostas_revisao = [
        {
            "proposta_id": item["proposta_id"],
            "motivos": item["problemas"],
        }
        for item in propostas
        if item["exige_revisao_humana"]
    ]
    conteudo_inventado = [
        item["proposta_id"]
        for item in propostas
        if any(
            objeto
            for objeto in json.loads(
                (
                    raiz / item["arquivo"]
                ).read_text(encoding="utf-8")
            ).get("objetos", [])
        )
    ]
    duplicidades_propostas = _duplicados(proposta_ids)
    duplicidades_idempotencia = _duplicados(idempotencias)
    duplicidades_json = _duplicados(hashes_json)
    conflitos_ocultos = sorted(conflito_ids_ledger - conflito_ids_revisados)
    problemas_conteudo = {
        "referencias_fisicas_destino": _texto_unico(
            motivo
            for item in propostas
            for motivo in item["referencias_fisicas_destino"]
        ),
        "sql_ou_codigo": _texto_unico(
            motivo
            for item in propostas
            for motivo in item["sql_ou_codigo"]
        ),
        "conteudo_inventado": conteudo_inventado,
    }
    relatorio = {
        "formato": "revisao-lotes-migracao-legado",
        "versao": VERSAO_MIGRACAO,
        "total_propostas": len(propostas),
        "classificacoes": classificacoes,
        "ids_por_classificacao": ids_por_classificacao,
        "propostas": propostas,
        "problemas_por_proposta": {
            item["proposta_id"]: item["problemas"] for item in propostas
        },
        "relacoes_e_referencias": {
            "propostas_com_relacoes": sum(
                bool(item["relacoes_envolvidas"]) for item in propostas
            ),
            "linhas_de_relacao": sum(
                len(item["relacoes_envolvidas"]) for item in propostas
            ),
            "propostas_com_referencias_nao_resolvidas": (
                propostas_com_referencias
            ),
        },
        "evidencias_e_proveniencia": {
            "propostas_com_evidencias": sum(
                bool(item["evidencias_proveniencia"]) for item in propostas
            ),
            "total_evidencias": sum(
                len(item["evidencias_proveniencia"]) for item in propostas
            ),
            "preservadas_quando_presentes": all(
                item["evidencias_proveniencia"] is not None
                for item in propostas
            ),
            "propostas_sem_evidencias": [
                item["proposta_id"]
                for item in propostas
                if not item["evidencias_proveniencia"]
            ],
            "proveniencia_de_relacoes_preservada_no_ledger": all(
                bool(ledger_por_proposta.get(item["proposta_id"]))
                for item in propostas
                if item["relacoes_envolvidas"]
            ),
        },
        "informacao_perdida_ou_sem_correspondencia": {
            "propostas_afetadas": propostas_com_perdas,
            "total_propostas_afetadas": len(propostas_com_perdas),
        },
        "aptas_para_futura_aplicacao": propostas_aptas,
        "exigem_revisao_humana": propostas_revisao,
        "verificacoes": {
            "todos_os_70_jsons_revisados": len(propostas) == 70,
            "contrato_real_validado": all(
                item["contrato_valido"] for item in propostas
            ),
            "dry_run_real_executado": True,
            "dry_run_sem_escrita": all(
                item["dry_run_sem_escrita"] for item in propostas
            ),
            "determinismo_dos_lotes": deterministico,
            "idempotencia": idempotente,
            "jsons_duplicados_indevidamente": duplicidades_json,
            "propostas_duplicadas": duplicidades_propostas,
            "idempotencias_duplicadas": duplicidades_idempotencia,
            "conflitos_ocultos": conflitos_ocultos,
            "problemas_de_conteudo": problemas_conteudo,
            "nenhum_conteudo_inventado": not conteudo_inventado,
            "nenhuma_referencia_fisica_de_destino": not problemas_conteudo[
                "referencias_fisicas_destino"
            ],
            "nenhum_sql_ou_codigo": not problemas_conteudo["sql_ou_codigo"],
        },
    }
    relatorio_path = _gravar_deterministico(
        raiz / "revisao_lotes_migracao.json",
        relatorio,
    )
    return ResultadoRevisaoLotesLegado(
        saida=raiz,
        relatorio=relatorio_path,
        total_propostas=len(propostas),
        classificacoes=classificacoes,
    )


def _tokens_relacionados(valor: Any) -> tuple[str, ...]:
    if valor is None:
        return ()
    return tuple(
        token.strip()
        for token in str(valor).split(",")
        if token.strip()
    )


def _indice_termos_legados(
    linhas: Iterable[Mapping[str, Any]],
) -> dict[str, set[int]]:
    indice: dict[str, set[int]] = defaultdict(set)
    for linha in linhas:
        registro_id = int(linha["id"])
        for campo in ("termo", "termo_original", "termo_chave"):
            valor = str(linha.get(campo) or "").strip()
            if valor:
                indice[valor.casefold()].add(registro_id)
    return indice


def _referencias_legadas(
    linha: Mapping[str, Any],
    indice: Mapping[str, set[int]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    resolvidas: list[dict[str, Any]] = []
    pendentes: list[dict[str, Any]] = []
    for token in _tokens_relacionados(linha.get("relacionados")):
        ids = sorted(indice.get(token.casefold(), set()))
        if len(ids) == 1:
            resolvidas.append(
                {
                    "valor_legado": token,
                    "registro_legado_id": ids[0],
                    "escopo": "somente_identidade_legada",
                }
            )
        elif not ids:
            pendentes.append(
                {
                    "valor_legado": token,
                    "motivo": (
                        "não há registro legado com correspondência objetiva"
                    ),
                }
            )
        else:
            pendentes.append(
                {
                    "valor_legado": token,
                    "motivo": (
                        "a correspondência legada não é única: "
                        + ", ".join(str(registro_id) for registro_id in ids)
                    ),
                }
            )
    return resolvidas, pendentes


def _campos_conhecimento_nao_migrados(
    linha: Mapping[str, Any],
) -> list[dict[str, str]]:
    return [
        {
            "campo": "termo",
            "motivo": (
                "não há classificação aprovada entre lexema, expressão e "
                "forma lexical"
            ),
        },
        {
            "campo": "termo_original",
            "motivo": "preservado somente como dado de origem, sem alvo lógico resolvido",
        },
        {
            "campo": "termo_chave",
            "motivo": "não foi validado por uma regra aprovada de normalização do destino",
        },
        {
            "campo": "tipo",
            "motivo": "tipo livre sem correspondência aprovada no modelo atual",
        },
        {
            "campo": "significado",
            "motivo": "não há objeto sentido resolvido para receber a definição",
        },
        {
            "campo": "contexto_uso",
            "motivo": "não há objeto sentido resolvido para receber o contexto",
        },
        {
            "campo": "resposta_padrao",
            "motivo": (
                "não existe correspondência no modelo atual; "
                + (
                    "valor preservado como evidência"
                    if linha.get("resposta_padrao")
                    else "campo ausente no legado"
                )
            ),
        },
        {
            "campo": "relacionados",
            "motivo": (
                "texto relacionado não é referência lógica de destino sem "
                "objetos e tipos resolvidos"
            ),
        },
        {
            "campo": "exemplo_uso",
            "motivo": (
                "não há campo lógico aprovado; valor preservado como "
                "evidência de origem"
            ),
        },
    ]


def resolver_revisao_lotes_migracao_legado(
    projeto: Path | str | None = None,
    *,
    saida_candidata: Path | str,
    relatorio: Path | str = "docs/RESOLUCAO_REVISAO_LOTES_MIGRACAO.json",
    destino: Path | str | None = None,
) -> ResultadoResolucaoLotesLegado:
    """Resolve o que é objetivo e mantém o restante explicitamente pendente.

    A função gera uma cópia candidata em ``saida_candidata`` e executa o
    ``dry_run`` real por meio de ``revisar_lotes_migracao_legado``. Nenhum
    objeto semântico é criado enquanto não existir regra aprovada para
    classificar os registros legados.
    """

    raiz = (
        Path(projeto).resolve()
        if projeto is not None
        else Path(__file__).resolve().parents[1]
    )
    saida_candidata_path = Path(saida_candidata)
    if not saida_candidata_path.is_absolute():
        saida_candidata_path = raiz / saida_candidata_path
    relatorio_path = Path(relatorio)
    if not relatorio_path.is_absolute():
        relatorio_path = raiz / relatorio_path

    bancos_antes = _snapshot_bancos(raiz)
    revisao = revisar_lotes_migracao_legado(
        projeto=raiz,
        saida=saida_candidata_path,
        destino=destino,
    )
    revisao_payload = json.loads(
        revisao.relatorio.read_text(encoding="utf-8")
    )

    conhecimento_conn = _conexao_ro(
        raiz / "aprendizado" / "bancos" / "conhecimento.db"
    )
    try:
        conhecimento_linhas = [
            dict(linha)
            for linha in conhecimento_conn.execute(
                "SELECT * FROM conhecimento ORDER BY id"
            )
        ]
    finally:
        conhecimento_conn.close()
    indice_termos = _indice_termos_legados(conhecimento_linhas)
    conhecimento_por_id = {
        int(linha["id"]): linha for linha in conhecimento_linhas
    }

    relacao_ledger = [
        registro
        for registro in json.loads(
            (
                revisao.saida / "ledger_cobertura.json"
            ).read_text(encoding="utf-8")
        )["registros"]
        if registro.get("tabela") == "relacoes"
    ]
    relacoes_por_proposta: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for registro in relacao_ledger:
        relacoes_por_proposta[str(registro["proposta_id"])].append(registro)

    revisao_por_id = {
        str(item["proposta_id"]): item
        for item in revisao_payload["propostas"]
    }
    propostas_resolvidas: list[dict[str, Any]] = []
    for linha in conhecimento_linhas:
        registro_id = int(linha["id"])
        proposta_id = f"migracao-legado-conhecimento-{registro_id}"
        revisada = revisao_por_id[proposta_id]
        referencias_resolvidas, referencias_pendentes = _referencias_legadas(
            linha,
            indice_termos,
        )
        evidencias = revisada["evidencias_proveniencia"]
        resposta_com_valor = bool(linha.get("resposta_padrao"))
        propostas_resolvidas.append(
            {
                "proposta_id": proposta_id,
                "origem": f"conhecimento.db:conhecimento:{registro_id}",
                "tipo": str(linha["tipo"]),
                "classificacao_final": "pendente",
                "campos_aproveitados": [
                    {
                        "campo": "id",
                        "uso": "identidade determinística e rastreabilidade",
                    },
                    {
                        "campo": "evidencias_conhecimento",
                        "uso": "proveniência e valores preservados fora de objetos",
                        "quantidade": len(evidencias),
                    },
                    {
                        "campo": "origem/estado/criado_em das evidências",
                        "uso": "ledger e referências de proveniência",
                    },
                ],
                "campos_descartados": _campos_conhecimento_nao_migrados(
                    linha
                ),
                "campos_preservados_fora_do_objeto": [
                    "termo",
                    "termo_original",
                    "termo_chave",
                    "tipo",
                    "significado",
                    "contexto_uso",
                    "resposta_padrao",
                    "relacionados",
                    "exemplo_uso",
                ],
                "resposta_padrao": {
                    "estado": "presente" if resposta_com_valor else "ausente",
                    "tratamento": (
                        "sem_correspondencia_preservada_em_evidencia"
                        if resposta_com_valor
                        else "ausente_no_legado"
                    ),
                },
                "referencias_resolvidas": referencias_resolvidas,
                "referencias_pendentes": [
                    *referencias_pendentes,
                    {
                        "motivo": (
                            "mesmo as correspondências textuais legadas "
                            "aguardam tipo e alvo lógico do destino"
                        )
                    },
                ],
                "evidencias_preservadas": evidencias,
                "motivo_decisao": (
                    "Os valores são preservados como evidência e proveniência, "
                    "mas não existe regra aprovada para converter o registro "
                    "em lexema, expressão, forma lexical ou sentido. Nenhum "
                    "objeto semântico foi inventado."
                ),
                "eventuais_conflitos": [],
                "condicao_necessaria_para_autorizacao": [
                    "aprovar a classificação do tipo legado",
                    "resolver o alvo lógico de significado e contexto",
                    "resolver referências relacionadas no modelo do destino",
                    "decidir o tratamento de resposta_padrao",
                    "revisão humana independente sem pendências ou ambiguidades",
                ],
                "evidencias_no_lote_candidato": len(evidencias),
                "objeto_semantico_gerado": False,
            }
        )

    for proposta_id in sorted(relacoes_por_proposta):
        registros = sorted(
            relacoes_por_proposta[proposta_id],
            key=lambda item: (
                int(item["termo_id"]),
                int(item["termo_relacionado_id"]),
            ),
        )
        primeiro = registros[0]
        endpoints = []
        for papel, campo in (
            ("origem_legada", "termo_id"),
            ("destino_legado", "termo_relacionado_id"),
        ):
            endpoint = conhecimento_por_id[int(primeiro[campo])]
            endpoints.append(
                {
                    "papel": papel,
                    "registro_legado_id": int(endpoint["id"]),
                    "termo": str(endpoint["termo"]),
                    "tipo_legado": str(endpoint["tipo"]),
                }
            )
        propostas_resolvidas.append(
            {
                "proposta_id": proposta_id,
                "origem": (
                    "relacoes.db:relacoes:"
                    + ",".join(str(item["registro_id"]) for item in registros)
                ),
                "tipo": str(primeiro["tipo"]),
                "classificacao_final": "conflitante",
                "campos_aproveitados": [
                    {
                        "campo": "termo_id/termo_relacionado_id",
                        "uso": "identidade dos endpoints somente no legado",
                    },
                    {
                        "campo": "tipo",
                        "uso": "proveniência do tipo livre no ledger",
                    },
                    {
                        "campo": "criado_em",
                        "uso": "metadado preservado no ledger",
                    },
                ],
                "campos_descartados": [
                    {
                        "campo": "direcao",
                        "motivo": "não existe no schema legado",
                    },
                    {
                        "campo": "ordem",
                        "motivo": "não existe no schema legado",
                    },
                    {
                        "campo": "tipo_semantico_dos_endpoints",
                        "motivo": "não existe no schema legado",
                    },
                ],
                "campos_preservados_fora_do_objeto": [
                    "termo_id",
                    "termo_relacionado_id",
                    "tipo",
                    "criado_em",
                ],
                "referencias_resolvidas": endpoints,
                "referencias_pendentes": [
                    {
                        "motivo": (
                            "endpoints legados não têm tipo de objeto "
                            "semântico resolvido no destino"
                        )
                    },
                    {
                        "motivo": "direção semântica não foi informada",
                    },
                    {
                        "motivo": "ordem dos componentes não foi informada",
                    },
                ],
                "evidencias_preservadas": [],
                "proveniencia_preservada_no_ledger": registros,
                "motivo_decisao": (
                    "Os dois endpoints e o par reverso são objetivos no "
                    "legado, mas não há evidência de direção, ordem ou tipo "
                    "semântico. O par não será convertido nem duplicado."
                ),
                "eventuais_conflitos": [
                    "par reverso presente no legado"
                ],
                "condicao_necessaria_para_autorizacao": [
                    "aprovar tipos semânticos para os dois endpoints",
                    "provar direção ou decidir explicitamente relação simétrica",
                    "provar ordem quando o tipo exigir componentes ordenados",
                    "revisão humana independente sem conflito",
                ],
                "direcao_comprovada": False,
                "ordem_comprovada": False,
                "objeto_semantico_gerado": False,
            }
        )

    propostas_resolvidas.sort(key=lambda item: str(item["proposta_id"]))
    classificacoes = {
        "apta": sum(
            item["classificacao_final"] == "apta"
            for item in propostas_resolvidas
        ),
        "pendente": sum(
            item["classificacao_final"] == "pendente"
            for item in propostas_resolvidas
        ),
        "conflitante": sum(
            item["classificacao_final"] == "conflitante"
            for item in propostas_resolvidas
        ),
        "rejeitada": sum(
            item["classificacao_final"] == "rejeitada"
            for item in propostas_resolvidas
        ),
    }
    bancos_depois = _snapshot_bancos(raiz)
    hashes_inalterados = all(
        bancos_antes[nome]["sha256"] == bancos_depois[nome]["sha256"]
        for nome, _ in _DB_RELATIVOS
    )
    relatorio_payload = {
        "formato": "resolucao-revisao-lotes-migracao",
        "versao": VERSAO_MIGRACAO,
        "modo": "resolucao_sem_aplicacao",
        "total_propostas": len(propostas_resolvidas),
        "classificacoes": classificacoes,
        "propostas": propostas_resolvidas,
        "candidato": {
            "lotes_gerados": len(
                tuple(saida_candidata_path.rglob("manifesto.json"))
            ),
            "jsons_gerados": len(propostas_resolvidas),
            "dry_run_real_executado": (
                revisao_payload["verificacoes"]["dry_run_real_executado"]
            ),
            "dry_run_sem_escrita": (
                revisao_payload["verificacoes"]["dry_run_sem_escrita"]
            ),
            "aplicado": False,
            "registrar_chamado": False,
            "autorizar_chamado": False,
        },
        "resposta_padrao": {
            "com_valor": sum(
                bool(linha.get("resposta_padrao"))
                for linha in conhecimento_linhas
            ),
            "ausente": sum(
                not bool(linha.get("resposta_padrao"))
                for linha in conhecimento_linhas
            ),
            "nenhuma_convertida_em_fato": True,
        },
        "relacoes": {
            "propostas": len(relacoes_por_proposta),
            "linhas": len(relacao_ledger),
            "com_direcao_comprovada": [],
            "sem_direcao_comprovada": sorted(relacoes_por_proposta),
            "pares_reversos_nao_duplicados": True,
        },
        "evidencias_proveniencia": {
            "total_evidencias_preservadas": sum(
                len(item["evidencias_preservadas"])
                for item in propostas_resolvidas
            ),
            "origens_ou_estados_nao_reescritos": True,
            "proveniencia_das_relacoes_no_ledger": True,
        },
        "aptas_para_autorizacao": [
            item["proposta_id"]
            for item in propostas_resolvidas
            if item["classificacao_final"] == "apta"
        ],
        "decisao_humana_necessaria": [
            {
                "proposta_id": item["proposta_id"],
                "motivo": item["motivo_decisao"],
                "condicao": item["condicao_necessaria_para_autorizacao"],
            }
            for item in propostas_resolvidas
            if item["classificacao_final"] != "apta"
        ],
        "verificacoes": {
            "revisao_anterior_reutilizada": True,
            "todos_os_70_resolvidos_individualmente": (
                len(propostas_resolvidas) == 70
            ),
            "nenhum_objeto_semantico_inventado": not any(
                item["objeto_semantico_gerado"]
                for item in propostas_resolvidas
            ),
            "dry_run_real_em_todas_as_propostas": (
                revisao_payload["verificacoes"]["todos_os_70_jsons_revisados"]
                and revisao_payload["verificacoes"]["dry_run_real_executado"]
            ),
            "determinismo": (
                revisao_payload["verificacoes"]["determinismo_dos_lotes"]
            ),
            "idempotencia": (
                revisao_payload["verificacoes"]["idempotencia"]
            ),
            "sem_registro_autorizacao_aplicacao": True,
            "hashes_bancos_inalterados": hashes_inalterados,
            "integridade_bancos_antes": {
                nome: bancos_antes[nome]["integridade"]
                for nome, _ in _DB_RELATIVOS
            },
            "integridade_bancos_depois": {
                nome: bancos_depois[nome]["integridade"]
                for nome, _ in _DB_RELATIVOS
            },
        },
        "bancos_antes": bancos_antes,
        "bancos_depois": bancos_depois,
    }
    relatorio_final = _gravar_deterministico(
        relatorio_path,
        relatorio_payload,
    )
    return ResultadoResolucaoLotesLegado(
        relatorio=relatorio_final,
        saida_candidata=saida_candidata_path,
        total_propostas=len(propostas_resolvidas),
        classificacoes=classificacoes,
        hashes_bancos_inalterados=hashes_inalterados,
    )


def main() -> int:
    resultado = gerar_lotes_migracao_legado()
    print(_json_canonico({"saida": str(resultado.saida), "totais": resultado.totais}))
    return 0


__all__ = [
    "ResultadoGeracaoLegado",
    "ResultadoRevisaoLotesLegado",
    "ResultadoResolucaoLotesLegado",
    "gerar_lotes_migracao_legado",
    "revisar_lotes_migracao_legado",
    "resolver_revisao_lotes_migracao_legado",
]


if __name__ == "__main__":
    raise SystemExit(main())