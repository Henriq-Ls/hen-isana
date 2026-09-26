"""Controlador protegido do ciclo de escrita de código gerado.

Somente main.py deve chamar este módulo. Ferramentas e código gerado não
podem importar core nem acessar este controlador.
"""

import ast
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from _LOGS_ import log as runtime_log
from bancos.indice_codigo import IndiceCodigoDB
from bancos.log_mudancas import LogMudancasDB
from backup.diagnostico import DiagnosticoDB
from backup.restaurador import restaurar
from backup.snapshot import Snapshot, criar_snapshot
from core.validador import ResultadoValidacao, validar
from core.versionamento import ResultadoCommit, registrar_alteracao
from ferramentas._caminhos import pasta_bancos_aprendizado, pasta_gerado
from ferramentas.criacao import criar_arquivo_gerado
from ferramentas.edicao import editar_arquivo_gerado
from protocolo.regras import ALVO_GERADO_ROOT, ALVO_GERADO_PREFIXO, TipoAcao, normalizar_alvo
from protocolo.verificador import (
    validar_codigo_gerado,
    validar_permissao,
    verificar_acao,
)


BASE_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = BASE_DIR.parent


@dataclass(frozen=True)
class ResultadoEscrita:
    sucesso: bool
    arquivo: Path
    mensagem: str
    validacao: ResultadoValidacao
    commit: Optional[ResultadoCommit] = None


def _alvo_gerado(caminho_relativo: str) -> str:
    caminho = caminho_relativo.replace("\\", "/").strip()
    if caminho.startswith(ALVO_GERADO_PREFIXO):
        return caminho
    return f"{ALVO_GERADO_ROOT}/{caminho}"


def _caminho_destino(caminho_relativo: str, projeto_dir: Path) -> tuple[str, Path]:
    alvo = _alvo_gerado(caminho_relativo)
    normalizado = normalizar_alvo(alvo)
    if normalizado is None or not normalizado.startswith(ALVO_GERADO_PREFIXO):
        raise PermissionError(
            "o arquivo precisa estar dentro de aprendizado/gerado/"
        )
    relativo = normalizado.removeprefix(ALVO_GERADO_PREFIXO)
    pasta = pasta_gerado(projeto_dir)
    destino = pasta / Path(relativo)
    try:
        destino.resolve().relative_to(pasta.resolve())
    except ValueError as erro:
        raise PermissionError(
            "o caminho escaparia de aprendizado/gerado/"
        ) from erro
    if destino.suffix != ".py":
        raise PermissionError("o arquivo gerado precisa ser Python")
    return normalizado, destino


def _simbolos(codigo: str) -> tuple[list[str], list[str]]:
    arvore = ast.parse(codigo, mode="exec")
    classes = [
        node.name
        for node in arvore.body
        if isinstance(node, ast.ClassDef)
    ]
    funcoes = [
        node.name
        for node in arvore.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    return classes, funcoes


def _registrar_falha(
    arquivo: Path,
    mensagem: str,
    contexto: Optional[str],
    projeto_dir: Path,
    log: LogMudancasDB,
) -> None:
    runtime_log.falha(
        "core.controlador",
        "_registrar_falha",
        mensagem,
        {"arquivo": str(arquivo), "contexto": contexto},
    )
    with DiagnosticoDB(projeto_dir / "data" / "diagnostico.db") as diagnostico:
        diagnostico.registrar(
            acao="escrita_gerado",
            alvo=str(arquivo),
            erro=mensagem,
            contexto=contexto,
        )
    log.registrar(
        acao="escrita_gerado",
        arquivo=str(arquivo),
        sucesso=False,
        mensagem=mensagem,
        contexto=contexto,
    )


def aplicar_codigo_gerado(
    caminho_relativo: str,
    codigo: str,
    *,
    editar: Optional[bool] = None,
    contexto: Optional[str] = None,
    projeto_dir: Optional[Path] = None,
    permissao: object | None = None,
) -> ResultadoEscrita:
    """Valida, grava e versiona um módulo em aprendizado/gerado/."""

    projeto = Path(projeto_dir or BASE_DIR)
    runtime_log.acao(
        "core.controlador",
        "aplicar_codigo_gerado",
        "iniciar escrita protegida",
        {
            "alvo_solicitado": caminho_relativo,
            "bytes": len(codigo.encode("utf-8")),
            "contexto": contexto,
        },
    )
    alvo, arquivo = _caminho_destino(caminho_relativo, projeto)
    acao = TipoAcao.EDITAR_ARQUIVO if arquivo.exists() else TipoAcao.CRIAR_ARQUIVO
    if editar is True:
        acao = TipoAcao.EDITAR_ARQUIVO
    elif editar is False:
        acao = TipoAcao.CRIAR_ARQUIVO

    autorizacao = validar_permissao(permissao, acao, alvo)
    if not autorizacao.permitida:
        validacao = ResultadoValidacao(False, "protocolo", autorizacao.mensagem)
        return ResultadoEscrita(False, arquivo, autorizacao.mensagem, validacao)

    verificacao = verificar_acao(acao, alvo)
    if not verificacao.permitida:
        runtime_log.falha(
            "core.controlador",
            "aplicar_codigo_gerado",
            verificacao.mensagem,
            {"etapa": "protocolo", "alvo": alvo},
        )
        validacao = ResultadoValidacao(False, "protocolo", verificacao.mensagem)
        return ResultadoEscrita(False, arquivo, verificacao.mensagem, validacao)

    isolamento = validar_codigo_gerado(codigo)
    if not isolamento.permitida:
        runtime_log.falha(
            "core.controlador",
            "aplicar_codigo_gerado",
            isolamento.mensagem,
            {"etapa": "isolamento", "alvo": alvo},
        )
        validacao = ResultadoValidacao(False, "protocolo", isolamento.mensagem)
        return ResultadoEscrita(False, arquivo, isolamento.mensagem, validacao)

    pasta_snapshots = projeto / "backup" / "snapshots"
    snapshot: Snapshot = criar_snapshot(arquivo, pasta_snapshots)
    runtime_log.passo(
        "core.controlador",
        "aplicar_codigo_gerado",
        "snapshot criado antes da escrita",
        {"arquivo": str(arquivo), "existia": snapshot.existia},
    )
    bancos = pasta_bancos_aprendizado(projeto)
    indice = IndiceCodigoDB(bancos / "indice_codigo.db")
    log = LogMudancasDB(bancos / "log_mudancas.db")

    try:
        validacao = validar(codigo)
        runtime_log.passo(
            "core.controlador",
            "aplicar_codigo_gerado",
            "validação antes da escrita concluída",
            {
                "arquivo": str(arquivo),
                "valido": validacao.valido,
                "etapa": validacao.etapa,
            },
        )
        if not validacao.valido:
            restaurar(snapshot)
            _registrar_falha(
                arquivo,
                validacao.mensagem,
                contexto,
                projeto,
                log,
            )
            return ResultadoEscrita(
                False,
                arquivo,
                "código rejeitado antes da escrita",
                validacao,
            )

        relativo = alvo.removeprefix(ALVO_GERADO_PREFIXO)
        if acao == TipoAcao.EDITAR_ARQUIVO:
            caminho_escrito = editar_arquivo_gerado(
                permissao,
                relativo,
                codigo,
                pasta_gerado(projeto),
            )
        else:
            caminho_escrito = criar_arquivo_gerado(
                permissao,
                relativo,
                codigo,
                pasta_gerado(projeto),
            )
        runtime_log.acao(
            "core.controlador",
            "aplicar_codigo_gerado",
            "arquivo escrito por ferramenta autorizada",
            {"arquivo": str(caminho_escrito), "acao": acao.value},
        )

        validacao_final = validar(caminho=caminho_escrito)
        runtime_log.passo(
            "core.controlador",
            "aplicar_codigo_gerado",
            "validação final concluída",
            {
                "arquivo": str(caminho_escrito),
                "valido": validacao_final.valido,
                "etapa": validacao_final.etapa,
            },
        )
        if not validacao_final.valido:
            restaurar(snapshot)
            _registrar_falha(
                arquivo,
                validacao_final.mensagem,
                contexto,
                projeto,
                log,
            )
            return ResultadoEscrita(
                False,
                arquivo,
                "código rejeitado depois da escrita; snapshot restaurado",
                validacao_final,
            )

        classes, funcoes = _simbolos(codigo)
        categoria = Path(relativo).stem
        for classe in classes or [None]:
            indice.registrar(
                categoria=categoria,
                arquivo=str(Path(ALVO_GERADO_ROOT) / relativo),
                classe=classe,
                funcao=funcoes[0] if funcoes else None,
            )

        mensagem = "arquivo gerado aceito"
        commit = registrar_alteracao(
            [arquivo.relative_to(projeto.parent)],
            f"hen-isana: atualizar {ALVO_GERADO_ROOT}/{relativo}",
            diretorio=projeto.parent,
        )
        if commit.criado:
            mensagem += "; commit criado"
        else:
            mensagem += f"; commit não criado: {commit.mensagem}"
        log.registrar(
            acao="escrita_gerado",
            arquivo=str(arquivo),
            sucesso=True,
            mensagem=mensagem,
            contexto=contexto,
        )
        runtime_log.acao(
            "core.controlador",
            "aplicar_codigo_gerado",
            "escrita gerada aceita",
            {
                "arquivo": str(arquivo),
                "commit_criado": commit.criado,
                "mensagem": mensagem,
            },
        )
        return ResultadoEscrita(
            True,
            arquivo,
            mensagem,
            validacao_final,
            commit,
        )
    except Exception as erro:
        runtime_log.falha(
            "core.controlador",
            "aplicar_codigo_gerado",
            str(erro),
            {"etapa": "exceção; restauração solicitada", "arquivo": str(arquivo)},
        )
        restaurar(snapshot)
        _registrar_falha(arquivo, str(erro), contexto, projeto, log)
        return ResultadoEscrita(
            False,
            arquivo,
            f"falha durante escrita; snapshot restaurado: {erro}",
            ResultadoValidacao(False, "escrita", str(erro)),
        )
    finally:
        indice.fechar()
        log.fechar()
