"""Regras estruturais de segurança do hen-isana."""

from enum import Enum
from pathlib import PurePosixPath
from typing import Optional


class TipoAcao(str, Enum):
    BUSCAR_CONHECIMENTO = "buscar_conhecimento"
    SALVAR_CONHECIMENTO = "salvar_conhecimento"
    SALVAR_RELACAO = "salvar_relacao"
    CONSULTAR_SISTEMA = "consultar_sistema"
    CONSULTAR_INTERNET = "consultar_internet"
    CRIAR_ARQUIVO = "criar_arquivo"
    EDITAR_ARQUIVO = "editar_arquivo"
    BUSCAR_ARQUIVO = "buscar_arquivo"


ALVO_CONHECIMENTO = "aprendizado/bancos/conhecimento"
ALVO_RELACOES = "aprendizado/bancos/relacoes"
ALVO_GERADO_ROOT = "aprendizado/gerado"
ALVO_GERADO_PREFIXO = f"{ALVO_GERADO_ROOT}/"


CAMINHOS_PROTEGIDOS = {
    "core",
    "protocolo",
    "bancos",
    "backup",
    "main.py",
    "aprendizado",
}

ACOES_DE_ARQUIVO = {
    TipoAcao.CRIAR_ARQUIVO,
    TipoAcao.EDITAR_ARQUIVO,
    TipoAcao.BUSCAR_ARQUIVO,
}


def normalizar_alvo(alvo: str) -> Optional[str]:
    """Normaliza um alvo relativo sem permitir travessia de diretório."""

    if not isinstance(alvo, str):
        return None
    texto = alvo.replace("\\", "/").strip()
    if not texto or texto.startswith("/"):
        return None
    caminho = PurePosixPath(texto)
    partes = caminho.parts
    if not partes or ".." in partes:
        return None
    return "/".join(partes)


def caminho_protegido(alvo: str) -> bool:
    normalizado = normalizar_alvo(alvo)
    if normalizado is None:
        return True
    primeiro = normalizado.split("/", 1)[0]
    return primeiro in CAMINHOS_PROTEGIDOS or primeiro.startswith(".")


def acao_permitida(tipo: TipoAcao, alvo: str) -> tuple[bool, str]:
    """Retorna se uma ação pode ser encaminhada para execução."""

    normalizado = normalizar_alvo(alvo)
    if normalizado is None:
        return False, "o alvo precisa ser um caminho relativo seguro"

    if tipo in {
        TipoAcao.BUSCAR_CONHECIMENTO,
        TipoAcao.SALVAR_CONHECIMENTO,
    }:
        if normalizado == ALVO_CONHECIMENTO:
            return True, "ação de conhecimento permitida"
        return False, "a memória deve ser acessada pelo banco de conhecimento"

    if tipo == TipoAcao.SALVAR_RELACAO:
        if normalizado == ALVO_RELACOES:
            return True, "ação de relação permitida"
        return False, "as relações devem ser acessadas pelo banco de relações"

    if tipo == TipoAcao.CONSULTAR_SISTEMA:
        if normalizado == "sistema/data_hora":
            return True, "consulta de data e hora permitida"
        return False, "o sistema só pode consultar data e hora"

    if tipo == TipoAcao.CONSULTAR_INTERNET:
        if normalizado == "internet/consulta":
            return True, "consulta de internet permitida"
        return False, "a internet só pode ser acessada pela ferramenta autorizada"

    if tipo in ACOES_DE_ARQUIVO:
        if not normalizado.startswith(ALVO_GERADO_PREFIXO):
            return False, (
                "ações de arquivo só podem usar "
                "aprendizado/gerado/"
            )
        if not normalizado.endswith(".py"):
            return False, "arquivos gerados precisam ter extensão .py"
        return True, "ação de arquivo gerado permitida"

    if caminho_protegido(normalizado):
        return False, "o alvo pertence a uma área protegida"

    return True, "ação permitida"
