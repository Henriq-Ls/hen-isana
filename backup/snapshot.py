"""Cópias de segurança antes de alterações em aprendizado/gerado/."""

from dataclasses import dataclass
from pathlib import Path
import time

from _LOGS_ import log as runtime_log

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_SNAPSHOT_DIR = BASE_DIR / "backup" / "snapshots"


@dataclass(frozen=True)
class Snapshot:
    arquivo: Path
    copia: Path
    existia: bool


def _nome_seguro(arquivo: Path) -> str:
    relativo = arquivo.name or "arquivo"
    return "".join(
        caractere if caractere.isalnum() or caractere in "._-" else "_"
        for caractere in relativo
    )


def criar_snapshot(
    arquivo: Path,
    pasta_snapshots: Path = DEFAULT_SNAPSHOT_DIR,
) -> Snapshot:
    """Copia o arquivo atual ou registra que ele ainda não existia."""

    caminho = Path(arquivo)
    runtime_log.acao(
        "backup.snapshot",
        "criar_snapshot",
        "preparar snapshot",
        {"arquivo": str(caminho)},
    )
    pasta = Path(pasta_snapshots)
    pasta.mkdir(parents=True, exist_ok=True)
    copia = pasta / f"{time.time_ns()}_{_nome_seguro(caminho)}.snapshot"

    if caminho.exists():
        if not caminho.is_file():
            raise IsADirectoryError(f"o alvo não é um arquivo: {caminho}")
        copia.write_bytes(caminho.read_bytes())
        runtime_log.passo(
            "backup.snapshot",
            "criar_snapshot",
            "snapshot de arquivo existente concluído",
            {"arquivo": str(caminho), "copia": str(copia), "existia": True},
        )
        return Snapshot(caminho, copia, True)

    copia.write_bytes(b"")
    runtime_log.passo(
        "backup.snapshot",
        "criar_snapshot",
        "snapshot de arquivo novo concluído",
        {"arquivo": str(caminho), "copia": str(copia), "existia": False},
    )
    return Snapshot(caminho, copia, False)
