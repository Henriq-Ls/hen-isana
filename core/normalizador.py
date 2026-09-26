"""Normalização determinística de entradas antes do roteamento.

Esta camada não tenta interpretar significado. Ela apenas expande abreviações
explicitamente aprovadas e identifica vocativos que podem ser ignorados quando
aparecem antes de um assunto real.
"""

from __future__ import annotations

import re
import unicodedata

from core.linguagem import ABREVIACOES, VOCATIVOS


_PALAVRAS_COM_ACENTO_SEMANTICO = frozenset(
    {"por", "pôr", "esta", "está", "sabia", "sábia"}
)


def normalizar_termo_estrito(termo: str) -> str:
    """Normaliza caixa e pontuação sem remover distinções de acento."""

    if not isinstance(termo, str):
        raise TypeError("termo deve ser uma string")
    texto = unicodedata.normalize("NFKC", termo).casefold()
    return " ".join(re.findall(r"\w+", texto, flags=re.UNICODE))


def normalizar_termo_chave(termo: str) -> str:
    """Gera uma chave de busca sem caixa, pontuação ou acentos não ambíguos.

    Algumas palavras preservam os acentos porque distinguem sentidos
    diferentes. A forma original nunca é substituída por esta chave.
    """

    if not isinstance(termo, str):
        raise TypeError("termo deve ser uma string")
    texto = unicodedata.normalize("NFKC", termo).casefold()
    palavras = re.findall(r"\w+", texto, flags=re.UNICODE)
    resultado = []
    for palavra in palavras:
        if palavra in _PALAVRAS_COM_ACENTO_SEMANTICO:
            resultado.append(palavra)
            continue
        decomposta = unicodedata.normalize("NFKD", palavra)
        resultado.append(
            "".join(
                caractere
                for caractere in decomposta
                if not unicodedata.combining(caractere)
            )
        )
    return " ".join(resultado)


def normalizar_frase(frase: str) -> str:
    """Expande abreviações conhecidas sem alterar a ordem da frase."""

    if not isinstance(frase, str):
        raise TypeError("frase deve ser uma string")

    texto = " ".join(frase.casefold().strip().split())

    def substituir(match: re.Match[str]) -> str:
        palavra = match.group(0)
        return ABREVIACOES.get(palavra, palavra)

    return re.sub(r"\b[\wÀ-ÿ]+\b", substituir, texto, flags=re.UNICODE)


def eh_vocativo(termo: str) -> bool:
    """Indica se uma unidade é um tratamento informal conhecido."""

    return " ".join(termo.casefold().strip().split()) in VOCATIVOS