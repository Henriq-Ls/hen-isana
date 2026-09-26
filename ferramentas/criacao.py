"""Criação de arquivos em aprendizado/gerado/ mediante autorização."""

from pathlib import Path
from typing import Optional

from _LOGS_ import log as runtime_log
from protocolo.regras import ALVO_GERADO_ROOT, TipoAcao
from protocolo.verificador import Permissao, validar_permissao

from ._caminhos import caminho_gerado_seguro, pasta_gerado as pasta_gerado_padrao


def criar_arquivo_gerado(
    permissao: Permissao,
    caminho_relativo: str,
    conteudo: str,
    pasta_gerado: Optional[Path] = None,
) -> Path:
    """Cria um arquivo novo; não sobrescreve arquivos existentes."""

    pasta = Path(pasta_gerado or pasta_gerado_padrao())
    caminho_normalizado = caminho_relativo.replace("\\", "/")
    alvo = f"{ALVO_GERADO_ROOT}/{caminho_normalizado}"
    verificacao = validar_permissao(permissao, TipoAcao.CRIAR_ARQUIVO, alvo)
    if not verificacao.permitida:
        raise PermissionError(verificacao.mensagem)

    caminho = caminho_gerado_seguro(
        caminho_relativo,
        pasta_gerado_destino=pasta,
    )
    if caminho.exists():
        raise FileExistsError(f"o arquivo já existe: {caminho}")
    if not isinstance(conteudo, str):
        raise TypeError("conteudo deve ser uma string")
    caminho.write_text(conteudo, encoding="utf-8")
    runtime_log.acao(
        "ferramentas.criacao",
        "criar_arquivo_gerado",
        "arquivo gerado criado",
        {"arquivo": str(caminho), "bytes": len(conteudo.encode("utf-8"))},
    )
    return caminho
