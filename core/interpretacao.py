"""Interpretação determinística de perguntas sobre conhecimento."""

import re
from typing import Optional


def interpretar_pergunta(frase: str) -> Optional[tuple[str, str]]:
    """Identifica perguntas simples e o campo de conhecimento solicitado."""
    if not isinstance(frase, str):
        return None

    texto = " ".join(frase.strip().split())
    padroes = (
        (
            "tipo",
            (
                r"^qual\s+(?:é|e)\s+o\s+tipo\s+ou\s+categoria\s+de\s+(.+?)[?.!]*$",
                r"^qual\s+(?:é|e)\s+o\s+tipo\s+de\s+(.+?)[?.!]*$",
                r"^qual\s+a\s+categoria\s+de\s+(.+?)[?.!]*$",
            ),
        ),
        (
            "significado",
            (
                r"^o\s+que\s+(.+?)\s+significa[?.!]*$",
                r"^o\s+que\s+significa\s+(.+?)[?.!]*$",
                r"^o\s+que\s+(?:é|e)\s+(.+?)[?.!]*$",
                r"^qual\s+(?:é|e)\s+o\s+significado\s+de\s+(.+?)[?.!]*$",
                r"^qual\s+(?:é|e\s+)?o\s+significado\s+de\s+(.+?)[?.!]*$",
            ),
        ),
        (
            "contexto_uso",
            (
                r"^em\s+que\s+contexto\s+(.+?)\s+(?:é|e)\s+usado[?.!]*$",
                r"^onde\s+(.+?)\s+(?:é|e)\s+usado[?.!]*$",
                r"^como\s+usar\s+(.+?)[?.!]*$",
            ),
        ),
        (
            "resposta_padrao",
            (
                r"^qual\s+resposta\s+devo\s+dar\s+quando\s+(.+?)\s+aparecer[?.!]*$",
                r"^como\s+devo\s+responder\s+a\s+(.+?)[?.!]*$",
            ),
        ),
    )

    for campo, expressoes in padroes:
        for expressao in expressoes:
            encontrado = re.match(expressao, texto, flags=re.IGNORECASE)
            if encontrado:
                termo = encontrado.group(1).strip()
                termo = termo.strip("'\"“”‘’ \t\r\n?!.:;")
                termo = re.sub(
                    r"^(?:um|uma|o|a)\s+",
                    "",
                    termo,
                    flags=re.IGNORECASE,
                )
                if termo:
                    return campo, termo
    return None


def parece_pergunta(frase: str) -> bool:
    """Indica se a entrada parece uma pergunta em linguagem natural."""
    if interpretar_pergunta(frase) is not None:
        return True
    texto = " ".join(frase.strip().split()).casefold()
    return texto.endswith("?") or texto.startswith(
        (
            "o que ",
            "qual ",
            "quais ",
            "como ",
            "quando ",
            "onde ",
            "por que ",
            "porque ",
        )
    )