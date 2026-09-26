"""Versionamento seguro das alterações aprovadas pelo núcleo."""

from dataclasses import dataclass
from pathlib import Path
import subprocess
from typing import Iterable, Optional


@dataclass(frozen=True)
class ResultadoCommit:
    """Resultado de uma tentativa de commit."""

    criado: bool
    mensagem: str


def _executar_git(
    argumentos: Iterable[str],
    diretorio: Path,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *argumentos],
        cwd=diretorio,
        text=True,
        capture_output=True,
        check=False,
    )


def repositorio_git_valido(diretorio: Path) -> bool:
    """Informa se ``diretorio`` está dentro de um repositório Git."""

    try:
        resultado = _executar_git(("rev-parse", "--is-inside-work-tree"), diretorio)
    except OSError:
        return False
    return resultado.returncode == 0 and resultado.stdout.strip() == "true"


def registrar_alteracao(
    arquivos: Iterable[Path],
    mensagem: str,
    diretorio: Optional[Path] = None,
) -> ResultadoCommit:
    """Adiciona arquivos e cria um commit, sem esconder falhas.

    O commit é recusado quando o diretório não é um repositório Git ou quando
    não há arquivos informados. Nenhuma falha é convertida em sucesso.
    """

    caminhos = [Path(arquivo) for arquivo in arquivos]
    if not caminhos:
        return ResultadoCommit(False, "nenhum arquivo foi informado")
    if not isinstance(mensagem, str) or not mensagem.strip():
        return ResultadoCommit(False, "a mensagem do commit não pode ser vazia")

    raiz = Path(diretorio) if diretorio is not None else Path.cwd()
    if not repositorio_git_valido(raiz):
        return ResultadoCommit(False, "o diretório não é um repositório Git")

    try:
        adicionar = _executar_git(
            ("add", "--", *(str(caminho) for caminho in caminhos)),
            raiz,
        )
        if adicionar.returncode != 0:
            erro = (adicionar.stderr or adicionar.stdout).strip()
            return ResultadoCommit(False, erro or "git add falhou")

        commit = _executar_git(("commit", "-m", mensagem.strip()), raiz)
    except OSError as erro:
        return ResultadoCommit(False, str(erro))

    if commit.returncode != 0:
        erro = (commit.stderr or commit.stdout).strip()
        return ResultadoCommit(False, erro or "git commit falhou")
    return ResultadoCommit(True, commit.stdout.strip() or "commit criado")
