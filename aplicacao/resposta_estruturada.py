"""Coordenação da resposta estruturada e fallback explícito para o legado."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Optional

from core.resposta_estruturada import (
    EstruturaRespostaIncompleta,
    PlanoResposta,
    RespostaEstruturada,
    gerar_resposta_estruturada,
)


@dataclass(frozen=True)
class RegistroFallbackResposta:
    """Estado observacional da escolha entre a camada nova e o legado."""

    status: str
    fallback: bool
    motivo: Optional[str]
    origem: str
    idempotencia: str


@dataclass(frozen=True)
class ExecucaoRespostaEstruturada:
    """Resposta efetivamente devolvida e o registro da decisão."""

    resposta: Any
    registro: RegistroFallbackResposta


def gerar_resposta_com_fallback(
    plano: PlanoResposta,
    executar_legado: Callable[[], Any],
    *,
    gerador: Callable[[PlanoResposta], RespostaEstruturada] = (
        gerar_resposta_estruturada
    ),
) -> ExecucaoRespostaEstruturada:
    """Usa a resposta estruturada válida; caso contrário, chama o legado."""

    if not isinstance(plano, PlanoResposta):
        raise TypeError("plano deve ser um PlanoResposta")
    try:
        resposta = gerador(plano)
        if not isinstance(resposta, RespostaEstruturada):
            raise TypeError("o gerador não retornou RespostaEstruturada")
        return ExecucaoRespostaEstruturada(
            resposta=resposta,
            registro=RegistroFallbackResposta(
                status="estruturada",
                fallback=False,
                motivo=None,
                origem="resposta_estruturada",
                idempotencia=plano.idempotencia,
            ),
        )
    except Exception as erro:
        resposta_legada = executar_legado()
        status = (
            "fallback_incompleta"
            if isinstance(erro, EstruturaRespostaIncompleta)
            else "fallback_falha"
        )
        return ExecucaoRespostaEstruturada(
            resposta=resposta_legada,
            registro=RegistroFallbackResposta(
                status=status,
                fallback=True,
                motivo=f"{type(erro).__name__}: {erro}",
                origem="resposta_estruturada",
                idempotencia=plano.idempotencia,
            ),
        )


__all__ = [
    "ExecucaoRespostaEstruturada",
    "RegistroFallbackResposta",
    "gerar_resposta_com_fallback",
]