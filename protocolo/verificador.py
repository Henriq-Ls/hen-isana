"""Verificação de ações antes de qualquer execução de ferramenta."""

import ast
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Optional
from uuid import uuid4

from _LOGS_ import log as runtime_log
from .regras import (
    ALVO_GERADO_ROOT,
    TipoAcao,
    acao_permitida,
    normalizar_alvo,
)


@dataclass(frozen=True)
class ResultadoVerificacao:
    permitida: bool
    mensagem: str
    alvo: Optional[str] = None


@dataclass(frozen=True)
class Permissao:
    """Autorização opaca emitida para uma operação específica."""

    tipo: TipoAcao
    alvo: str
    token: str


def _registrar_bloqueio(tipo: TipoAcao, alvo: str, mensagem: str) -> None:
    runtime_log.falha(
        "protocolo.verificador",
        "verificar_acao",
        mensagem,
        {"tipo": tipo.value, "alvo": alvo, "bloqueado": True},
    )
    try:
        from backup.diagnostico import DiagnosticoDB

        with DiagnosticoDB() as diagnostico:
            diagnostico.registrar(
                acao=tipo.value,
                alvo=alvo,
                erro=mensagem,
                contexto="protocolo",
            )
    except (OSError, RuntimeError):
        # A ação continua bloqueada mesmo se o registro do diagnóstico falhar.
        pass


def verificar_acao(
    tipo: TipoAcao,
    alvo: str,
) -> ResultadoVerificacao:
    """Verifica uma ação e registra toda tentativa bloqueada."""

    if not isinstance(tipo, TipoAcao):
        try:
            tipo = TipoAcao(str(tipo))
        except ValueError:
            mensagem = "tipo de ação desconhecido"
            _registrar_bloqueio(TipoAcao.BUSCAR_ARQUIVO, alvo, mensagem)
            return ResultadoVerificacao(False, mensagem)

    permitida, mensagem = acao_permitida(tipo, alvo)
    normalizado = normalizar_alvo(alvo)
    resultado = ResultadoVerificacao(permitida, mensagem, normalizado)
    if not permitida:
        _registrar_bloqueio(tipo, alvo, mensagem)
    else:
        runtime_log.passo(
            "protocolo.verificador",
            "verificar_acao",
            "ação autorizada pelo protocolo",
            {"tipo": tipo.value, "alvo": normalizado},
        )
    return resultado


def emitir_permissao(tipo: TipoAcao, alvo: str) -> Permissao:
    """Emite uma autorização somente depois de verificar a ação."""

    resultado = verificar_acao(tipo, alvo)
    if not resultado.permitida or resultado.alvo is None:
        raise PermissionError(resultado.mensagem)
    runtime_log.acao(
        "protocolo.verificador",
        "emitir_permissao",
        "permissão emitida",
        {"tipo": tipo.value, "alvo": resultado.alvo},
    )
    return Permissao(tipo, resultado.alvo, uuid4().hex)


def validar_permissao(
    permissao: object,
    tipo: TipoAcao,
    alvo: str,
) -> ResultadoVerificacao:
    """Confere que uma ferramenta recebeu autorização para exatamente a ação."""

    if not isinstance(permissao, Permissao):
        mensagem = "permissão ausente ou inválida"
        _registrar_bloqueio(tipo, alvo, mensagem)
        return ResultadoVerificacao(False, mensagem)

    atual = verificar_acao(tipo, alvo)
    if not atual.permitida or atual.alvo is None:
        return atual

    if permissao.tipo != tipo or permissao.alvo != atual.alvo:
        mensagem = "a permissão não corresponde à ação solicitada"
        _registrar_bloqueio(tipo, alvo, mensagem)
        return ResultadoVerificacao(False, mensagem)

    return ResultadoVerificacao(True, "permissão válida", atual.alvo)


class _VisitanteCodigoGerado(ast.NodeVisitor):
    """Impede acessos estruturais ao núcleo protegido."""

    def __init__(self) -> None:
        self.erro: Optional[str] = None

    def _bloquear(self, mensagem: str) -> None:
        if self.erro is None:
            self.erro = mensagem

    def visit_Import(self, node: ast.Import) -> None:
        for nome in node.names:
            if nome.name == "core" or nome.name.startswith("core."):
                self._bloquear("código gerado não pode importar core")
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        modulo = node.module or ""
        if modulo == "core" or modulo.startswith("core."):
            self._bloquear("código gerado não pode importar core")
        if any(
            nome.name == "core" or nome.name.startswith("core.")
            for nome in node.names
        ):
            self._bloquear("código gerado não pode referenciar core")
        self.generic_visit(node)

    def visit_Name(self, node: ast.Name) -> None:
        if node.id == "core":
            self._bloquear("código gerado não pode referenciar core")
        if node.id in {"__import__", "eval", "exec"}:
            self._bloquear("código gerado não pode usar carregamento dinâmico")
        self.generic_visit(node)

    def visit_Attribute(self, node: ast.Attribute) -> None:
        if node.attr in {"__import__", "import_module", "eval", "exec"}:
            self._bloquear("código gerado não pode usar carregamento dinâmico")
        self.generic_visit(node)

    def visit_Constant(self, node: ast.Constant) -> None:
        if isinstance(node.value, str):
            texto = node.value.strip().lower().replace("\\", "/")
            if (
                texto == "core"
                or texto.startswith("core/")
                or texto.startswith("core.")
            ):
                self._bloquear("código gerado não pode apontar para core")
            if texto in {"__import__", "import_module", "eval", "exec"}:
                self._bloquear("código gerado não pode usar carregamento dinâmico")
        self.generic_visit(node)


def validar_codigo_gerado(codigo: str) -> ResultadoVerificacao:
    """Valida sintaxe e isolamento do código em aprendizado/gerado/."""

    if not isinstance(codigo, str):
        return ResultadoVerificacao(False, "o código precisa ser texto")

    try:
        arvore = ast.parse(codigo, mode="exec")
    except SyntaxError as erro:
        mensagem = f"sintaxe inválida: {erro}"
        _registrar_bloqueio(TipoAcao.CRIAR_ARQUIVO, ALVO_GERADO_ROOT, mensagem)
        return ResultadoVerificacao(False, mensagem)

    visitante = _VisitanteCodigoGerado()
    visitante.visit(arvore)
    if visitante.erro:
        _registrar_bloqueio(
            TipoAcao.CRIAR_ARQUIVO,
            ALVO_GERADO_ROOT,
            visitante.erro,
        )
        return ResultadoVerificacao(False, visitante.erro)

    return ResultadoVerificacao(True, "código gerado estruturalmente permitido")
