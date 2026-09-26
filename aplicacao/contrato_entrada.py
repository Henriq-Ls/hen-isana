"""Fronteira independente de banco para pacotes de conhecimento.

Este módulo contém somente a conversão segura de dicionário/JSON para
``ContratoCadastro``. Ele não importa a API de banco e não conhece schema
físico, tabelas ou colunas.
"""

from __future__ import annotations

from collections.abc import Mapping
import json
import re
from typing import Any

from core.contratos import ContratoCadastro


_CHAVES_FISICAS = re.compile(
    r"(?:sql|python|exec|comando|tabela|coluna|cursor|conex[aã]o)",
    re.IGNORECASE,
)
_CODIGO_EXECUTAVEL = re.compile(
    r"(?:__import__|eval\s*\(|exec\s*\(|compile\s*\(|"
    r"open\s*\(|os\.system|subprocess|(?:^|\s)import\s+|"
    r"(?:^|\s)from\s+\w+\s+import\s+)",
    re.IGNORECASE,
)
_SQL_EMBUTIDO = re.compile(
    r"\b(?:select\s+.+\s+from|insert\s+into|update\s+\S+\s+set|"
    r"delete\s+from|drop\s+(?:table|index|database)|alter\s+table|"
    r"create\s+table|pragma\s+\w+|attach\s+database)\b",
    re.IGNORECASE | re.DOTALL,
)


def contrato_de_dict(pacote: Mapping[str, Any]) -> ContratoCadastro:
    """Converte apenas dados estruturados; não consulta nem grava banco."""
    _rejeitar_conteudo_ativo(pacote)
    return ContratoCadastro.from_dict(pacote)


def contrato_de_json(texto: str) -> ContratoCadastro:
    """Converte JSON para contrato sem usar ``eval`` ou equivalente."""
    if not isinstance(texto, str) or not texto.strip():
        raise ValueError("o pacote JSON precisa ser texto não vazio")
    try:
        pacote = json.loads(texto)
    except json.JSONDecodeError as erro:
        raise ValueError("pacote JSON inválido") from erro
    if not isinstance(pacote, Mapping):
        raise TypeError("o pacote JSON precisa ser um objeto")
    return contrato_de_dict(pacote)


def _rejeitar_conteudo_ativo(valor: Any, caminho: str = "pacote") -> None:
    """Rejeita instruções, SQL e referências físicas antes do contrato."""
    if isinstance(valor, Mapping):
        for chave, item in valor.items():
            if not isinstance(chave, str):
                raise TypeError(f"{caminho} contém chave que não é texto")
            if _CHAVES_FISICAS.search(chave):
                raise ValueError(
                    f"{caminho}.{chave} contém instrução ou referência física"
                )
            _rejeitar_conteudo_ativo(item, f"{caminho}.{chave}")
        return
    if isinstance(valor, (list, tuple)):
        for indice, item in enumerate(valor):
            _rejeitar_conteudo_ativo(item, f"{caminho}[{indice}]")
        return
    if not isinstance(valor, str):
        return
    if _CODIGO_EXECUTAVEL.search(valor):
        raise ValueError(f"{caminho} contém código executável")
    if _SQL_EMBUTIDO.search(valor):
        raise ValueError(f"{caminho} contém SQL")