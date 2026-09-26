"""Composição de respostas simbólicas a partir de dados recuperados."""

import re
from typing import Iterable, Optional

from bancos.conhecimento import EntradaConhecimento, FatoConhecimento


def _extrair_repllica_dialogo(exemplo_uso: Optional[str]) -> Optional[str]:
    """Extrai a fala de B de um exemplo simples em formato de diálogo."""
    if not exemplo_uso:
        return None

    correspondencia = re.search(
        r"(?:^|\s)B\s*:\s*(.+)",
        exemplo_uso.strip(),
        flags=re.IGNORECASE | re.DOTALL,
    )
    if correspondencia is None:
        return None

    resposta = correspondencia.group(1).strip()
    resposta = re.split(
        r"\s+[AB]\s*:\s*",
        resposta,
        maxsplit=1,
        flags=re.IGNORECASE,
    )[0].strip()
    return resposta or None


def entrada_eh_conversacional(
    frase: str,
    entrada: EntradaConhecimento,
    expressoes_conversacionais: Iterable[str] = (),
) -> bool:
    """Identifica uma entrada curta que deve receber resposta natural.

    A lista linguística evita transformar qualquer termo solto em saudação.
    Um exemplo com fala de B também é suficiente para reconhecer uma
    expressão dialogal aprendida explicitamente.
    """
    normalizar = lambda texto: " ".join(
        re.findall(r"\w+", texto.casefold(), flags=re.UNICODE)
    )
    frase_normalizada = normalizar(frase)
    termo_normalizado = normalizar(entrada.termo)
    lista_normalizada = {normalizar(item) for item in expressoes_conversacionais}
    return (
        frase_normalizada == termo_normalizado
        and (
            termo_normalizado in lista_normalizada
            or _extrair_repllica_dialogo(entrada.exemplo_uso) is not None
            or bool(
                entrada.resposta_padrao
                and "?" in entrada.resposta_padrao
            )
        )
    )


def compor_resposta_conversacional(
    entrada: EntradaConhecimento,
    nome_interlocutor: Optional[str] = None,
) -> Optional[str]:
    """Retorna uma réplica curta sem reutilizar nomes de exemplos.

    Nomes apresentados pela fala A do exemplo pertencem àquela conversa
    armazenada, não necessariamente à sessão atual.
    """
    replica = _extrair_repllica_dialogo(entrada.exemplo_uso)
    if replica:
        return _neutralizar_nome_de_exemplo(
            entrada.exemplo_uso or "",
            replica,
            nome_interlocutor,
        )
    if entrada.resposta_padrao:
        return _neutralizar_nome_de_exemplo(
            entrada.exemplo_uso or "",
            entrada.resposta_padrao,
            nome_interlocutor,
        )
    return None


def _neutralizar_nome_de_exemplo(
    exemplo_uso: str,
    resposta: str,
    nome_interlocutor: Optional[str],
) -> str:
    falas_a = re.findall(
        r"(?:^|\s)A\s*:\s*(.*?)(?=\s+[AB]\s*:\s*|$)",
        exemplo_uso.strip(),
        flags=re.IGNORECASE | re.DOTALL,
    )
    nomes: list[str] = []
    marcador_nome = re.compile(
        r"\b(?:meu\s+nome\s+(?:é|e)|me\s+chamo|eu\s+me\s+chamo|"
        r"eu\s+sou|sou)\s+",
        flags=re.IGNORECASE,
    )
    palavra = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*", re.UNICODE)
    for fala in falas_a:
        marcador = marcador_nome.search(fala)
        if marcador is None:
            continue
        restante = fala[marcador.end():]
        primeiro = palavra.match(restante)
        if primeiro is None:
            continue
        nome = primeiro.group(0)
        restante = restante[primeiro.end():]
        segundo = palavra.match(restante.lstrip())
        if segundo is not None and segundo.group(0)[:1].isupper():
            nome += " " + segundo.group(0)
        if nome.casefold() not in {item.casefold() for item in nomes}:
            nomes.append(nome)

    resultado = resposta
    for nome in nomes:
        if not re.search(rf"\b{re.escape(nome)}\b", resultado, re.IGNORECASE):
            continue
        substituto = nome_interlocutor or ""
        resultado = re.sub(
            rf"(?i),?\s*\b{re.escape(nome)}\b",
            lambda _match: (
                f", {substituto}" if substituto else ""
            ),
            resultado,
        )
    resultado = re.sub(r"\s{2,}", " ", resultado)
    resultado = re.sub(r"\s+([,.!?;:])", r"\1", resultado)
    return resultado.strip()


def compor_resposta_explicativa(
    entrada: EntradaConhecimento,
) -> Optional[str]:
    """Formata o conhecimento para uma pergunta explícita do usuário."""
    partes: list[str] = []
    if entrada.significado:
        partes.append(f"significado: {entrada.significado}")
    if entrada.contexto_uso:
        partes.append(f"contexto de uso: {entrada.contexto_uso}")
    if entrada.exemplo_uso:
        partes.append(f"exemplo de uso: {entrada.exemplo_uso}")
    if not partes:
        return None
    return f"{entrada.termo}: " + "; ".join(partes)


def compor_resposta_dinamica(
    entradas: list[EntradaConhecimento],
    fatos: list[FatoConhecimento],
    relacionadas: list[EntradaConhecimento],
) -> Optional[str]:
    """Compõe uma resposta apenas com conhecimento fornecido pelos chamadores."""
    partes: list[str] = []
    for entrada in entradas:
        informacoes = []
        if entrada.tipo:
            informacoes.append(f"categoria: {entrada.tipo}")
        if entrada.significado:
            informacoes.append(entrada.significado)
        if entrada.contexto_uso:
            informacoes.append(
                f"contexto de uso: {entrada.contexto_uso}"
            )
        if entrada.exemplo_uso:
            informacoes.append(f"exemplo: {entrada.exemplo_uso}")
        if informacoes:
            partes.append(f"{entrada.termo}: " + "; ".join(informacoes))

    partes.extend(
        f"{fato.afirmacao} (contexto: {fato.contexto})"
        for fato in fatos
    )
    if relacionadas:
        partes.append(
            "Relações registradas: "
            + ", ".join(entrada.termo for entrada in relacionadas)
        )
    return "; ".join(partes) if partes else None