"""Caminhos canônicos e validações locais das ferramentas."""

from pathlib import Path


BASE_DIR = Path(__file__).resolve().parents[1]
APRENDIZADO_DIR = BASE_DIR / "aprendizado"


def pasta_aprendizado(projeto_dir: Path | None = None) -> Path:
    """Retorna a raiz dos artefatos aprendidos de um projeto."""
    return Path(projeto_dir or BASE_DIR) / "aprendizado"


def pasta_gerado(projeto_dir: Path | None = None) -> Path:
    """Retorna a pasta dos módulos Python gerados pela aprendizagem."""
    return pasta_aprendizado(projeto_dir) / "gerado"


def pasta_bancos_aprendizado(projeto_dir: Path | None = None) -> Path:
    """Retorna a pasta dos bancos que acompanham o aprendizado."""
    return pasta_aprendizado(projeto_dir) / "bancos"


def caminho_dentro_de(caminho: Path, pasta: Path) -> bool:
    try:
        caminho.resolve().relative_to(pasta.resolve())
        return True
    except ValueError:
        return False


def caminho_gerado_seguro(
    caminho_relativo: str,
    pasta_gerado_destino: Path | None = None,
) -> Path:
    pasta = Path(pasta_gerado_destino or pasta_gerado())
    caminho = pasta / Path(caminho_relativo)
    pasta.mkdir(parents=True, exist_ok=True)
    if not caminho_dentro_de(caminho, pasta):
        raise PermissionError(
            "o caminho precisa permanecer dentro de aprendizado/gerado/"
        )
    return caminho
