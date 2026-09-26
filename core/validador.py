"""Validação isolada de código Python.

O validador só analisa e executa o código em um processo separado. Ele não
grava o código recebido e não altera o projeto.
"""

from dataclasses import dataclass
import ast
from pathlib import Path
import subprocess
import sys
from typing import Optional

from _LOGS_ import log as runtime_log

@dataclass(frozen=True)
class ResultadoValidacao:
    """Resultado detalhado de uma tentativa de validação."""

    valido: bool
    etapa: str
    mensagem: str


def _ler_codigo(codigo: Optional[str], caminho: Optional[Path]) -> str:
    if codigo is not None and caminho is not None:
        raise ValueError("informe codigo ou caminho, não os dois")
    if codigo is None and caminho is None:
        raise ValueError("informe codigo ou caminho")
    if codigo is not None:
        if not isinstance(codigo, str):
            raise TypeError("codigo deve ser uma string")
        return codigo
    assert caminho is not None
    return caminho.read_text(encoding="utf-8")


def validar_sintaxe(codigo: Optional[str] = None, caminho: Optional[Path] = None) -> ResultadoValidacao:
    """Valida somente a estrutura sintática do código."""

    try:
        arvore = ast.parse(_ler_codigo(codigo, caminho), mode="exec")
        if not isinstance(arvore, ast.Module):
            return ResultadoValidacao(False, "sintaxe", "o código não produziu um módulo Python")
    except (SyntaxError, OSError, UnicodeError, ValueError, TypeError) as erro:
        return ResultadoValidacao(False, "sintaxe", str(erro))
    return ResultadoValidacao(True, "sintaxe", "sintaxe válida")


def validar_execucao_isolada(
    codigo: Optional[str] = None,
    caminho: Optional[Path] = None,
    timeout_segundos: float = 5.0,
) -> ResultadoValidacao:
    """Executa o módulo em processo isolado sem gravar arquivos.

    O conteúdo é enviado pela entrada padrão ao interpretador filho. O
    processo recebe ``-I`` para evitar configurações e módulos locais do
    ambiente do projeto.
    """

    fonte = _ler_codigo(codigo, caminho)
    runtime_log.passo(
        "core.validador",
        "validar_execucao_isolada",
        "iniciando validação em subprocesso",
        {"origem": str(caminho) if caminho else "texto", "bytes": len(fonte.encode("utf-8"))},
    )
    sintaxe = validar_sintaxe(fonte)
    if not sintaxe.valido:
        runtime_log.falha(
            "core.validador",
            "validar_execucao_isolada",
            sintaxe.mensagem,
            {"etapa": sintaxe.etapa},
        )
        return sintaxe

    programa_teste = (
        "import ast\n"
        "import sys\n"
        "source = sys.stdin.read()\n"
        "tree = ast.parse(source, mode='exec')\n"
        "code = compile(tree, '<hen-isana-validacao>', 'exec')\n"
        "namespace = {'__name__': '__hen_isana_validacao__'}\n"
        "exec(code, namespace, namespace)\n"
    )
    try:
        processo = subprocess.run(
            [sys.executable, "-I", "-c", programa_teste],
            input=fonte,
            text=True,
            capture_output=True,
            timeout=timeout_segundos,
            check=False,
        )
    except subprocess.TimeoutExpired:
        runtime_log.falha(
            "core.validador",
            "validar_execucao_isolada",
            "a execução excedeu o tempo limite",
            {"timeout_segundos": timeout_segundos},
        )
        return ResultadoValidacao(False, "execucao", "a execução excedeu o tempo limite")
    except OSError as erro:
        runtime_log.falha(
            "core.validador",
            "validar_execucao_isolada",
            str(erro),
            {"etapa": "iniciar subprocesso"},
        )
        return ResultadoValidacao(False, "execucao", str(erro))

    if processo.returncode != 0:
        mensagem = (processo.stderr or processo.stdout).strip()
        runtime_log.falha(
            "core.validador",
            "validar_execucao_isolada",
            mensagem or "o processo terminou com erro",
            {"returncode": processo.returncode},
        )
        return ResultadoValidacao(False, "execucao", mensagem or "o processo terminou com erro")
    runtime_log.passo(
        "core.validador",
        "validar_execucao_isolada",
        "subprocesso validado com sucesso",
        {"returncode": processo.returncode},
    )
    return ResultadoValidacao(True, "execucao", "execução isolada válida")


def validar(codigo: Optional[str] = None, caminho: Optional[Path] = None) -> ResultadoValidacao:
    """Executa as validações obrigatórias em ordem."""

    sintaxe = validar_sintaxe(codigo, caminho)
    if not sintaxe.valido:
        return sintaxe
    return validar_execucao_isolada(codigo, caminho)
