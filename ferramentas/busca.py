"""Consultas de conhecimento autorizadas pelo protocolo."""

from typing import Optional

from _LOGS_ import log as runtime_log
from bancos.conhecimento import (
    ConhecimentoDB,
    EntradaConhecimento,
    FatoConhecimento,
)
from protocolo.regras import ALVO_CONHECIMENTO, TipoAcao
from protocolo.verificador import verificar_acao


def buscar_conhecimento(
    banco: ConhecimentoDB,
    termo: str,
    contexto: Optional[str] = None,
) -> list[EntradaConhecimento]:
    verificacao = verificar_acao(
        TipoAcao.BUSCAR_CONHECIMENTO,
        ALVO_CONHECIMENTO,
    )
    if not verificacao.permitida:
        raise PermissionError(verificacao.mensagem)
    resultados = banco.buscar_termo(termo, contexto)
    runtime_log.acao(
        "ferramentas.busca",
        "buscar_conhecimento",
        "conhecimento consultado",
        {"termo": termo, "contexto": contexto, "resultados": len(resultados)},
    )
    return resultados


def buscar_conhecimento_confirmado(
    banco: ConhecimentoDB,
    termo: str,
    contexto: Optional[str] = None,
) -> list[EntradaConhecimento]:
    """Busca somente campos sustentados por evidências confirmadas."""
    verificacao = verificar_acao(
        TipoAcao.BUSCAR_CONHECIMENTO,
        ALVO_CONHECIMENTO,
    )
    if not verificacao.permitida:
        raise PermissionError(verificacao.mensagem)
    resultados = banco.buscar_termo_confirmado(termo, contexto)
    runtime_log.acao(
        "ferramentas.busca",
        "buscar_conhecimento_confirmado",
        "conhecimento confirmado consultado",
        {"termo": termo, "contexto": contexto, "resultados": len(resultados)},
    )
    return resultados


def listar_conhecimento_confirmado(
    banco: ConhecimentoDB,
) -> list[EntradaConhecimento]:
    """Lista termos com os campos não confirmados removidos."""
    verificacao = verificar_acao(
        TipoAcao.BUSCAR_CONHECIMENTO,
        ALVO_CONHECIMENTO,
    )
    if not verificacao.permitida:
        raise PermissionError(verificacao.mensagem)
    resultados = banco.listar_termos_confirmados()
    runtime_log.acao(
        "ferramentas.busca",
        "listar_conhecimento_confirmado",
        "conhecimento confirmado listado",
        {"resultados": len(resultados)},
    )
    return resultados


def buscar_conhecimento_por_id_confirmado(
    banco: ConhecimentoDB,
    termo_id: int,
) -> Optional[EntradaConhecimento]:
    """Busca uma entrada por ID ocultando valores não confirmados."""
    verificacao = verificar_acao(
        TipoAcao.BUSCAR_CONHECIMENTO,
        ALVO_CONHECIMENTO,
    )
    if not verificacao.permitida:
        raise PermissionError(verificacao.mensagem)
    resultado = banco.buscar_termo_por_id_confirmado(termo_id)
    runtime_log.acao(
        "ferramentas.busca",
        "buscar_conhecimento_por_id_confirmado",
        "entrada confirmada consultada por ID",
        {"termo_id": termo_id, "resultado": resultado is not None},
    )
    return resultado


def buscar_fatos_confirmados(
    banco: ConhecimentoDB,
    contexto: Optional[str] = None,
) -> list[FatoConhecimento]:
    """Busca fatos confirmados pelo protocolo de leitura de conhecimento."""
    verificacao = verificar_acao(
        TipoAcao.BUSCAR_CONHECIMENTO,
        ALVO_CONHECIMENTO,
    )
    if not verificacao.permitida:
        raise PermissionError(verificacao.mensagem)
    fatos = banco.buscar_fatos_confirmados(contexto)
    runtime_log.acao(
        "ferramentas.busca",
        "buscar_fatos_confirmados",
        "fatos confirmados consultados",
        {"contexto": contexto, "resultados": len(fatos)},
    )
    return fatos


def identificar_lacunas(
    banco: ConhecimentoDB,
    termo: str,
    contexto: Optional[str] = None,
) -> list[str]:
    verificacao = verificar_acao(
        TipoAcao.BUSCAR_CONHECIMENTO,
        ALVO_CONHECIMENTO,
    )
    if not verificacao.permitida:
        raise PermissionError(verificacao.mensagem)
    lacunas = banco.identificar_lacunas(termo, contexto)
    runtime_log.passo(
        "ferramentas.busca",
        "identificar_lacunas",
        "lacunas consultadas",
        {"termo": termo, "contexto": contexto, "lacunas": lacunas},
    )
    return lacunas
