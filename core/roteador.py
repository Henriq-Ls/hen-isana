"""Roteamento interno de informações recebidas pelo hen-isana.

O roteador não grava dados e não executa ações. Ele apenas classifica uma
entrada e informa para qual área lógica ela deve ser encaminhada.
"""

from dataclasses import dataclass
from enum import Enum
import re
from typing import Optional
import unicodedata

from core.normalizador import normalizar_frase


class Categoria(str, Enum):
    """Categorias iniciais reconhecidas pelo núcleo."""

    SAUDACAO = "saudacao"
    PERGUNTA = "pergunta"
    ORDEM = "ordem"
    INFORMACAO = "informacao"
    DESCONHECIDO = "desconhecido"


class Destino(str, Enum):
    """Destinos internos disponíveis nesta etapa."""

    CONHECIMENTO = "conhecimento"
    INTERACAO = "interacao"
    APRENDIZAGEM = "aprendizagem"


class Intencao(str, Enum):
    """Intenções operacionais reconhecidas antes da busca por termos."""

    CONSULTAR_HORA = "consultar_hora"
    CONSULTAR_DATA = "consultar_data"
    CONSULTAR_DATA_HORA = "consultar_data_hora"
    RESPONDER_SAUDACAO = "responder_saudacao"
    PERGUNTAR_ESTADO_SOCIAL = "perguntar_estado_social"
    PERGUNTAR_NOME = "perguntar_nome"
    DESPEDIDA = "despedida"


@dataclass(frozen=True)
class Rota:
    """Resultado imutável de uma decisão de roteamento."""

    categoria: Categoria
    destino: Destino
    confianca: float
    motivo: str
    intencao: Optional[Intencao] = None


_SAUDACOES = (
    "oi",
    "olá",
    "ola",
    "bom dia",
    "boa tarde",
    "boa noite",
)

_INICIO_PERGUNTA = (
    "quem",
    "qual",
    "quais",
    "quando",
    "onde",
    "como",
    "por que",
    "porque",
    "o que",
    "pode",
    "poderia",
)

_INICIO_ORDEM = (
    "faça",
    "faca",
    "faz",
    "crie",
    "cria",
    "mostre",
    "mostra",
    "salve",
    "salva",
    "edite",
    "edita",
    "consulte",
    "consulta",
)


def _remover_acentos(texto: str) -> str:
    """Retorna uma forma comparável entre variantes com e sem acento."""

    normalizado = unicodedata.normalize("NFKD", texto)
    return "".join(
        caractere
        for caractere in normalizado
        if not unicodedata.combining(caractere)
    )


def _normalizar(frase: str) -> str:
    """Normaliza espaços e caixa sem remover acentos."""

    return normalizar_frase(frase)


def _normalizar_para_intencao(frase: str) -> str:
    """Normaliza pontuação, caixa e acentos para reconhecer variações."""

    texto = _remover_acentos(frase.casefold())
    texto = re.sub(r"[^\w\s]", " ", texto, flags=re.UNICODE)
    return " ".join(texto.split())


def _começa_com_expressao(frase: str, expressao: str) -> bool:
    """Evita classificar 'oiara' como se começasse com 'oi'."""

    return frase == expressao or frase.startswith(expressao + " ")


def _reconhecer_intencao(texto: str) -> Optional[Intencao]:
    """Reconhece intenções de consulta usando a frase inteira.

    Esta camada é deliberadamente determinística. Ela não tenta atribuir
    significado a cada palavra isolada; primeiro procura uma forma de pedido
    conhecida e só depois o fluxo pode recorrer ao banco de termos.
    """

    normalizado = _normalizar_para_intencao(texto)
    if not normalizado:
        return None

    saudacoes = {
        "oi",
        "ola",
        "bom dia",
        "boa tarde",
        "boa noite",
        "oi bom dia",
        "ola bom dia",
        "oi boa tarde",
        "ola boa tarde",
        "oi boa noite",
        "ola boa noite",
    }
    if normalizado in saudacoes:
        return Intencao.RESPONDER_SAUDACAO

    if normalizado in {"ate logo", "ate mais", "tchau", "adeus"}:
        return Intencao.DESPEDIDA

    if normalizado == "como voce esta":
        return Intencao.PERGUNTAR_ESTADO_SOCIAL

    if re.search(r"\bqual e o seu nome$", normalizado):
        return Intencao.PERGUNTAR_NOME

    pergunta_data_hora = (
        re.search(r"\bdata\b", normalizado)
        and re.search(r"\bhora\b|\bhoras\b", normalizado)
        and re.search(
            r"\b(qual|que|como|quero|gostaria|pode|diga|diz|informe|"
            r"informar|saber|consultar|consulta)\b",
            normalizado,
        )
    )
    if pergunta_data_hora:
        return Intencao.CONSULTAR_DATA_HORA

    padroes_data = (
        r"\bque dia e hoje\b",
        r"\bqual e a data de hoje\b",
        r"\bqual o dia de hoje\b",
        r"\bdata de hoje\b",
        r"\b(quero|gostaria de|preciso) saber (que )?dia e hoje\b",
        r"\b(quero|gostaria de|preciso) saber a data de hoje\b",
    )
    if any(re.search(padrao, normalizado) for padrao in padroes_data):
        return Intencao.CONSULTAR_DATA

    padroes_hora = (
        r"\bque horas? sao$",
        r"\bqual e a hora agora\b",
        r"\bqual e a hora atual\b",
        r"\bhora atual\b",
        r"\bhoras agora\b",
        r"\bquantas horas$",
        r"\bhorario atual$",
        r"\b(me )?(diga|diz|informe|informar|fale|fala) as horas\b",
        r"\b(quero|gostaria de|preciso) saber "
        r"(?:(que|quantas) )?horas?\b",
        r"\b(quero|gostaria de|preciso) saber o horario\b",
        r"\b(voce sabe|pode) (me )?(dizer|informar) (que )?horas?\b",
        r"\b(voce sabe|pode) (me )?(dizer|informar) o horario\b",
    )
    if any(re.search(padrao, normalizado) for padrao in padroes_hora):
        return Intencao.CONSULTAR_HORA

    return None


def rotear(frase: str, tipo: Optional[str] = None) -> Rota:
    """Classifica uma frase e escolhe um destino lógico.

    ``tipo`` pode ser informado por uma etapa futura que já tenha identificado
    a natureza da entrada. Quando não é informado, a classificação usa apenas
    sinais simples e determinísticos da frase.
    """

    if not isinstance(frase, str):
        raise TypeError("frase deve ser uma string")

    texto = _normalizar(frase)
    if not texto:
        return Rota(
            categoria=Categoria.DESCONHECIDO,
            destino=Destino.APRENDIZAGEM,
            confianca=1.0,
            motivo="entrada vazia",
        )

    tipo_normalizado = tipo.strip().lower() if isinstance(tipo, str) else None
    if tipo_normalizado:
        for categoria in Categoria:
            if tipo_normalizado == categoria.value:
                destino = (
                    Destino.INTERACAO
                    if categoria in (Categoria.SAUDACAO, Categoria.PERGUNTA, Categoria.ORDEM)
                    else Destino.CONHECIMENTO
                )
                return Rota(categoria, destino, 1.0, "categoria informada")

    intencao = _reconhecer_intencao(texto)
    if intencao is not None:
        categoria = (
            Categoria.SAUDACAO
            if intencao
            in (Intencao.RESPONDER_SAUDACAO, Intencao.DESPEDIDA)
            else Categoria.PERGUNTA
        )
        return Rota(
            categoria,
            Destino.INTERACAO,
            0.99,
            "intenção reconhecida na frase completa",
            intencao,
        )

    if texto.endswith("?") or any(_começa_com_expressao(texto, item) for item in _INICIO_PERGUNTA):
        return Rota(Categoria.PERGUNTA, Destino.INTERACAO, 0.95, "sinal de pergunta")

    if any(_começa_com_expressao(texto, item) for item in _INICIO_ORDEM):
        return Rota(Categoria.ORDEM, Destino.INTERACAO, 0.90, "verbo de ação no início")

    if any(_começa_com_expressao(texto, item) for item in _SAUDACOES):
        return Rota(Categoria.SAUDACAO, Destino.INTERACAO, 0.90, "saudação conhecida")

    if re.search(r"\b(é|e|significa|chama-se|chamase)\b", texto):
        return Rota(Categoria.INFORMACAO, Destino.CONHECIMENTO, 0.75, "estrutura informativa")

    return Rota(
        Categoria.DESCONHECIDO,
        Destino.APRENDIZAGEM,
        0.50,
        "nenhum padrão conhecido foi identificado",
    )
