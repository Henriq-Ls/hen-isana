"""Carregamento das regras linguísticas editáveis do hen-isana.

Estas listas são dados de inicialização, não conhecimento aprendido. Termos
fora delas, como ``dev``, continuam disponíveis para aprendizagem contextual.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


CAMINHO_LINGUAGEM = (
    Path(__file__).resolve().parents[1] / "data" / "linguagem.json"
)


def _ler_lista(dados: dict[str, Any], nome: str) -> frozenset[str]:
    valores = dados.get(nome)
    if not isinstance(valores, list) or not valores:
        raise ValueError(
            f"linguagem.json precisa conter uma lista não vazia: {nome}"
        )
    resultado: set[str] = set()
    for valor in valores:
        if not isinstance(valor, str) or not valor.strip():
            raise ValueError(
                f"linguagem.json contém valor inválido em {nome}: {valor!r}"
            )
        resultado.add(valor.casefold().strip())
    return frozenset(resultado)


def carregar_regras_linguisticas(
    caminho: Path = CAMINHO_LINGUAGEM,
) -> dict[str, frozenset[str]]:
    """Lê e valida as listas linguísticas; falha explicitamente se inválidas."""
    try:
        with caminho.open("r", encoding="utf-8") as arquivo:
            dados = json.load(arquivo)
    except (OSError, json.JSONDecodeError) as erro:
        raise RuntimeError(
            f"não foi possível carregar as regras linguísticas: {caminho}"
        ) from erro
    if not isinstance(dados, dict):
        raise ValueError("linguagem.json deve conter um objeto JSON")
    return {
        "palavras_funcionais": _ler_lista(dados, "palavras_funcionais"),
        "palavras_ignoradas_ao_aprender_resposta": _ler_lista(
            dados,
            "palavras_ignoradas_ao_aprender_resposta",
        ),
        "expressoes_conversacionais": _ler_lista(
            dados,
            "expressoes_conversacionais",
        ),
        "abreviacoes": _ler_lista(dados, "abreviacoes"),
        "vocativos": _ler_lista(dados, "vocativos"),
    }


REGRAS_LINGUISTICAS = carregar_regras_linguisticas()
PALAVRAS_FUNCIONAIS = REGRAS_LINGUISTICAS["palavras_funcionais"]
PALAVRAS_IGNORADAS_AO_APRENDER_RESPOSTA = REGRAS_LINGUISTICAS[
    "palavras_ignoradas_ao_aprender_resposta"
]
EXPRESSOES_CONVERSACIONAIS = REGRAS_LINGUISTICAS[
    "expressoes_conversacionais"
]
ABREVIACOES = {
    item.split("=", 1)[0].strip(): item.split("=", 1)[1].strip()
    for item in REGRAS_LINGUISTICAS["abreviacoes"]
}
VOCATIVOS = REGRAS_LINGUISTICAS["vocativos"]