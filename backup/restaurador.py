"""Restauração de arquivos a partir de snapshots."""

from pathlib import Path

from _LOGS_ import log as runtime_log
from .snapshot import Snapshot


def restaurar(snapshot: Snapshot) -> None:
    """Restaura o estado anterior ao snapshot."""

    arquivo = Path(snapshot.arquivo)
    runtime_log.acao(
        "backup.restaurador",
        "restaurar",
        "restaurar snapshot",
        {
            "arquivo": str(arquivo),
            "existia_antes": snapshot.existia,
            "copia": str(snapshot.copia),
        },
    )
    if snapshot.existia:
        arquivo.parent.mkdir(parents=True, exist_ok=True)
        arquivo.write_bytes(snapshot.copia.read_bytes())
    elif arquivo.exists():
        if arquivo.is_dir():
            raise IsADirectoryError(f"não é possível remover diretório: {arquivo}")
        arquivo.unlink()
    runtime_log.passo(
        "backup.restaurador",
        "restaurar",
        "snapshot restaurado",
        {"arquivo": str(arquivo)},
    )
