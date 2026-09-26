"""Gerador determinístico usado somente pelos testes do contrato JSON.

Este módulo não pertence ao fluxo de produção. Ele recebe uma descrição
estruturada, ordena somente coleções semânticas e devolve JSON compatível com
``ContratoCadastro``. A validação real continua sendo feita pelo código do
projeto, não por um validador paralelo.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import json
from pathlib import Path
from typing import Any

from aplicacao.cadastro import contrato_de_dict
from bancos.api_conhecimento import _CAMPOS_PERMITIDOS


_RAIZ = {
    "proposta_id",
    "entrada",
    "idempotencia",
    "objetos",
    "evidencias",
    "pendencias",
    "incertezas",
    "estado",
    "ambiguidades",
}
_OBJETO = {
    "objeto_id",
    "tipo",
    "chave",
    "campos",
    "relacoes",
    "pendencias",
    "incertezas",
    "ambiguidades",
}
_CAMPO = {
    "nome",
    "valor",
    "origem",
    "estado",
    "confianca",
    "evidencia_ids",
}
_EVIDENCIA = {
    "evidencia_id",
    "fonte_tipo",
    "fonte_identificador",
    "origem",
    "trecho",
    "referencia",
    "confianca",
    "estado",
    "revisao_necessaria",
}
_RELACAO = {
    "tipo",
    "origem_objeto_id",
    "destino_tipo",
    "destino_chave",
    "ordem",
    "estado",
    "confianca",
    "evidencia_ids",
}


def _objeto(valor: Any, nome: str) -> Mapping[str, Any]:
    if not isinstance(valor, Mapping):
        raise TypeError(f"{nome} deve ser um objeto estruturado")
    if any(not isinstance(chave, str) for chave in valor):
        raise TypeError(f"{nome} contém chave que não é texto")
    return valor


def _chaves(valor: Mapping[str, Any], permitidas: set[str], nome: str) -> None:
    desconhecidas = set(valor) - permitidas
    if desconhecidas:
        nomes = ", ".join(sorted(desconhecidas))
        raise ValueError(f"{nome} contém campos não suportados: {nomes}")


def _lista(valor: Any, nome: str) -> list[Any]:
    if not isinstance(valor, (list, tuple)):
        raise TypeError(f"{nome} deve ser uma lista")
    return list(valor)


def _textos(valor: Any, nome: str) -> list[str]:
    itens = _lista(valor, nome)
    if any(not isinstance(item, str) or not item.strip() for item in itens):
        raise TypeError(f"{nome} deve conter somente textos não vazios")
    return sorted(itens)


def _ids(valor: Any, nome: str) -> list[str]:
    return _textos(valor, nome)


def _campos(valor: Any, tipo: str) -> list[dict[str, Any]]:
    if isinstance(valor, Mapping):
        itens: list[Mapping[str, Any]] = []
        for nome, especificacao in valor.items():
            if not isinstance(nome, str):
                raise TypeError("nome de campo deve ser texto")
            especificacao = _objeto(especificacao, f"campo {nome}")
            item = dict(especificacao)
            item["nome"] = nome
            itens.append(item)
    else:
        itens = [_objeto(item, "campo") for item in _lista(valor, "campos")]

    permitidos = _CAMPOS_PERMITIDOS.get(tipo)
    if permitidos is None:
        raise ValueError(f"tipo de objeto não suportado: {tipo}")

    resultado: list[dict[str, Any]] = []
    nomes: set[str] = set()
    for item in itens:
        _chaves(item, _CAMPO, f"campo de {tipo}")
        nome = item.get("nome")
        if not isinstance(nome, str) or not nome.strip():
            raise ValueError(f"campo de {tipo} precisa de nome")
        if nome not in permitidos:
            raise ValueError(f"campo não suportado para {tipo}: {nome}")
        if nome in nomes:
            raise ValueError(f"campo repetido para {tipo}: {nome}")
        if "valor" not in item or "origem" not in item:
            raise ValueError(f"campo {nome} precisa de valor e origem")
        nomes.add(nome)
        normalizado = dict(item)
        if "evidencia_ids" in normalizado:
            normalizado["evidencia_ids"] = _ids(
                normalizado["evidencia_ids"],
                f"campo {nome}.evidencia_ids",
            )
        resultado.append(normalizado)
    return sorted(resultado, key=lambda item: item["nome"])


def _relacoes(valor: Any) -> list[dict[str, Any]]:
    resultado: list[dict[str, Any]] = []
    for item in _lista(valor, "relacoes"):
        item = dict(_objeto(item, "relacao"))
        _chaves(item, _RELACAO, "relacao")
        if "evidencia_ids" in item:
            item["evidencia_ids"] = _ids(
                item["evidencia_ids"],
                "relacao.evidencia_ids",
            )
        resultado.append(item)
    return sorted(
        resultado,
        key=lambda item: (
            str(item.get("tipo", "")),
            str(item.get("origem_objeto_id", "")),
            str(item.get("destino_tipo", "")),
            str(item.get("destino_chave", "")),
        ),
    )


def _objetos(valor: Any) -> list[dict[str, Any]]:
    resultado: list[dict[str, Any]] = []
    for item in _lista(valor, "objetos"):
        item = dict(_objeto(item, "objeto"))
        _chaves(item, _OBJETO, "objeto")
        for obrigatorio in ("objeto_id", "tipo", "chave"):
            if obrigatorio not in item:
                raise ValueError(f"objeto não contém {obrigatorio}")
        tipo = item["tipo"]
        if tipo not in _CAMPOS_PERMITIDOS:
            raise ValueError(f"tipo de objeto não suportado: {tipo}")
        if "campos" in item:
            item["campos"] = _campos(item["campos"], tipo)
        if "relacoes" in item:
            item["relacoes"] = _relacoes(item["relacoes"])
        for nome in ("pendencias", "incertezas", "ambiguidades"):
            if nome in item:
                item[nome] = _textos(item[nome], f"objeto.{nome}")
        resultado.append(item)
    return sorted(resultado, key=lambda item: str(item["objeto_id"]))


def _evidencias(valor: Any) -> list[dict[str, Any]]:
    resultado: list[dict[str, Any]] = []
    ids: set[str] = set()
    for item in _lista(valor, "evidencias"):
        item = dict(_objeto(item, "evidencia"))
        _chaves(item, _EVIDENCIA, "evidencia")
        if "evidencia_id" not in item:
            raise ValueError("evidencia não contém evidencia_id")
        evidencia_id = item["evidencia_id"]
        if evidencia_id in ids:
            raise ValueError(f"evidencia repetida: {evidencia_id}")
        ids.add(evidencia_id)
        for obrigatorio in (
            "fonte_tipo",
            "fonte_identificador",
            "origem",
            "trecho",
        ):
            if obrigatorio not in item:
                raise ValueError(f"evidencia não contém {obrigatorio}")
        resultado.append(item)
    return sorted(resultado, key=lambda item: str(item["evidencia_id"]))


def _normalizar(descricao: Mapping[str, Any]) -> dict[str, Any]:
    descricao = _objeto(descricao, "descricao")
    _chaves(descricao, _RAIZ, "descricao")
    for obrigatorio in ("proposta_id", "entrada", "idempotencia"):
        if obrigatorio not in descricao:
            raise ValueError(f"descricao não contém {obrigatorio}")

    resultado: dict[str, Any] = {
        nome: descricao[nome]
        for nome in ("proposta_id", "entrada", "idempotencia")
    }
    if "objetos" in descricao:
        resultado["objetos"] = _objetos(descricao["objetos"])
    if "evidencias" in descricao:
        resultado["evidencias"] = _evidencias(descricao["evidencias"])
    for nome in ("pendencias", "incertezas", "ambiguidades"):
        if nome in descricao:
            resultado[nome] = _textos(descricao[nome], nome)
    if "estado" in descricao:
        resultado["estado"] = descricao["estado"]

    # A conversão real rejeita SQL, código e referências físicas em qualquer
    # conteúdo antes de a string JSON sair do gerador de teste.
    contrato_de_dict(resultado)
    return resultado


def gerar_json_teste(descricao: Mapping[str, Any]) -> str:
    """Gera JSON canônico sem acessar banco e sem executar conteúdo."""

    payload = _normalizar(descricao)
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def gerar_arquivo_json_teste(
    descricao: Mapping[str, Any],
    caminho: Path | str,
) -> Path:
    """Escreve somente o JSON gerado em um arquivo indicado pelo teste."""

    destino = Path(caminho)
    destino.write_text(
        gerar_json_teste(descricao),
        encoding="utf-8",
    )
    return destino


__all__ = [
    "gerar_arquivo_json_teste",
    "gerar_json_teste",
]