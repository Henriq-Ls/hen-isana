"""Fachada compatível para as sessões separadas por responsabilidade."""

from .aprendizagem.sessao import (
    executar_modo_professor,
    imprimir_comandos_propostas,
)
from .conversa.sessao import executar_conversa_pessoal


def _dependencias_do_fluxo():
    """Carrega a API histórica do fluxo sob demanda."""
    from .fluxo import (
        _eh_comando_proposta,
        aprender_termo,
        interpretar_pergunta,
        processar_frase,
        termos_desconhecidos_no_texto,
        tokenizar,
    )

    return (
        _eh_comando_proposta,
        aprender_termo,
        interpretar_pergunta,
        processar_frase,
        termos_desconhecidos_no_texto,
        tokenizar,
    )