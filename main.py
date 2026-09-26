"""Ponto de entrada terminal e fachada compatível do hen-isana."""

from __future__ import annotations

import functools
import inspect

from aplicacao import fluxo as _fluxo
from aplicacao import sessao as _sessao
from aplicacao import terminal as _terminal
from aplicacao.aprendizagem import sessao as _sessao_aprendizagem
from aplicacao.conversa import sessao as _sessao_conversa
from aplicacao.terminal import executar_terminal


def __getattr__(nome: str):
    """Encaminha a API histórica para o fluxo sem duplicar implementações.

    A sincronização temporária de nomes também mantém funcionais os testes e
    consumidores que substituem dependências com ``patch("main.nome")``.
    """
    alvo = None
    for modulo in (_fluxo, _terminal, _sessao):
        if hasattr(modulo, nome):
            alvo = getattr(modulo, nome)
            break
    if alvo is None:
        raise AttributeError(
            f"module {__name__!r} has no attribute {nome!r}"
        )

    if not inspect.isfunction(alvo):
        return alvo

    @functools.wraps(alvo)
    def encaminhar(*args, **kwargs):
        destinos = tuple(
            dict.fromkeys(
                (
                    _fluxo,
                    _terminal,
                    _sessao,
                    _sessao_conversa,
                    _sessao_aprendizagem,
                )
            )
        )
        substituicoes = {
            modulo: {
                nome_modulo: valor
                for nome_modulo, valor in globals().items()
                if nome_modulo in vars(modulo)
            }
            for modulo in destinos
        }
        anteriores = {
            modulo: {
                nome_modulo: vars(modulo)[nome_modulo]
                for nome_modulo in valores
            }
            for modulo, valores in substituicoes.items()
        }
        try:
            for modulo, valores in substituicoes.items():
                vars(modulo).update(valores)
            return alvo(*args, **kwargs)
        finally:
            for modulo, valores in anteriores.items():
                vars(modulo).update(valores)

    return encaminhar


def __dir__() -> list[str]:
    return sorted(
        set(globals())
        | set(dir(_fluxo))
        | set(dir(_terminal))
        | set(dir(_sessao))
    )


__all__ = [
    nome for nome in dir(_fluxo) if not nome.startswith("_")
] + ["executar_terminal"]


if __name__ == "__main__":
    executar_terminal()