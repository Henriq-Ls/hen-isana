"""Núcleo linguístico simbólico isolado do fluxo legado.

As funções deste módulo analisam texto em memória. Elas não abrem SQLite, não
criam fatos e não executam ações. O subconjunto gramatical é deliberadamente
explícito e preserva alternativas quando a heurística não é suficiente.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Mapping, Optional

from core.contratos import (
    AlvoSemantico,
    AnaliseMorfologica,
    AnaliseMorfologicaAlternativa,
    ArgumentoSemantico,
    CandidatoLexical,
    ContextoAnalise,
    DependenciaSintatica,
    EntidadeDiscursiva,
    Enunciado,
    EstruturaSintatica,
    HipoteseAnalise,
    NoSintatico,
    PredicadoSemantico,
    ProposicaoIntermediaria,
    ReferenciaTurno,
    SpanTexto,
    Token,
)
from core.normalizador import normalizar_frase, normalizar_termo_chave


_TOKEN_RE = re.compile(r"\w+|[^\w\s]", flags=re.UNICODE)
_PRONOMES = frozenset(
    {
        "ele",
        "ela",
        "eles",
        "elas",
        "isso",
        "isto",
        "aquilo",
        "esse",
        "essa",
        "este",
        "esta",
        "aquele",
        "aquela",
    }
)
_FUNCIONAIS = frozenset(
    {
        "a",
        "as",
        "ao",
        "aos",
        "com",
        "de",
        "do",
        "dos",
        "e",
        "em",
        "entre",
        "mas",
        "na",
        "nas",
        "no",
        "nos",
        "o",
        "os",
        "para",
        "por",
        "que",
        "se",
        "um",
        "uma",
        "uns",
        "umas",
    }
)
_VERBOS_IRREGULARES = frozenset(
    {
        "é",
        "e",
        "ser",
        "está",
        "estao",
        "estão",
        "foi",
        "vai",
        "vem",
        "tem",
        "pode",
        "deve",
        "quer",
        "viu",
        "faz",
        "dorme",
        "leia",
    }
)
_SUFIXOS_VERBAIS = (
    "ariam",
    "eriam",
    "iriam",
    "assem",
    "essem",
    "issem",
    "ando",
    "endo",
    "indo",
    "aram",
    "eram",
    "iram",
    "ava",
    "iam",
    "ou",
    "eu",
    "iu",
    "ar",
    "er",
    "ir",
)


@dataclass(frozen=True)
class ResultadoLexico:
    """Enunciado tokenizado, candidatos preservados e palavras desconhecidas."""

    enunciado: Enunciado
    desconhecidos: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResultadoParser:
    """Uma ou mais estruturas sintáticas candidatas."""

    estruturas: tuple[EstruturaSintatica, ...]
    verbo_por_estrutura: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.estruturas:
            raise ValueError("o parser precisa produzir ao menos uma estrutura")
        if len(self.estruturas) != len(self.verbo_por_estrutura):
            raise ValueError("cada estrutura precisa de um verbo associado")


@dataclass(frozen=True)
class ResultadoSemantico:
    """Entidades e proposições produzidas sem fatos persistentes."""

    entidades: tuple[EntidadeDiscursiva, ...]
    proposicoes: tuple[ProposicaoIntermediaria, ...]
    hipoteses: tuple[HipoteseAnalise, ...] = ()


@dataclass(frozen=True)
class ResolucaoReferenciaSimbolica:
    pronome: str
    entidade_id: Optional[str] = None
    candidatos: tuple[str, ...] = ()

    @property
    def resolvida(self) -> bool:
        return self.entidade_id is not None

    @property
    def ambigua(self) -> bool:
        return self.entidade_id is None and len(self.candidatos) > 1


@dataclass(frozen=True)
class ResultadoReferenciasSimbolicas:
    resolucoes: tuple[ResolucaoReferenciaSimbolica, ...]
    contexto_atual: ContextoAnalise
    pendencias: tuple[str, ...] = ()


def _lema_por_sufixo(palavra: str) -> str:
    for sufixo in _SUFIXOS_VERBAIS:
        if palavra.endswith(sufixo) and len(palavra) - len(sufixo) >= 3:
            base = palavra[: -len(sufixo)]
            if sufixo in {"ando", "endo", "indo"}:
                return base + "ar" if sufixo == "ando" else base + "er"
            if sufixo in {"ou", "ava", "aram", "eu", "eram", "iram", "iu"}:
                return base + "ar"
            return base
    return palavra


def _classe_morfologica(palavra: str) -> str:
    if palavra in _PRONOMES:
        return "pronome"
    if palavra in _FUNCIONAIS:
        return "palavra_funcional"
    if palavra in _VERBOS_IRREGULARES or any(
        palavra.endswith(sufixo) for sufixo in _SUFIXOS_VERBAIS
    ):
        return "verbo"
    if palavra.endswith(("mente",)):
        return "adverbio"
    if palavra.endswith(("ção", "ções", "dade", "dades", "mento", "mentos")):
        return "substantivo"
    return "substantivo"


def tokenizar_enunciado(
    texto: str,
    candidatos_por_forma: Mapping[str, tuple[CandidatoLexical, ...]] | None = None,
) -> ResultadoLexico:
    """Tokeniza preservando spans do texto original e candidatos lexicais."""

    if not isinstance(texto, str) or not texto.strip():
        raise ValueError("texto deve ser uma string não vazia")
    candidatos_por_forma = candidatos_por_forma or {}
    tokens: list[Token] = []
    desconhecidos: list[str] = []
    for match in _TOKEN_RE.finditer(texto):
        trecho = match.group(0)
        span = SpanTexto(match.start(), match.end())
        if trecho.isalnum() or "_" in trecho:
            normalizado = normalizar_termo_chave(trecho)
            candidatos = tuple(
                candidatos_por_forma.get(normalizado)
                or candidatos_por_forma.get(trecho.casefold(), ())
            )
            if not candidatos:
                candidatos = (CandidatoLexical(trecho, _lema_por_sufixo(normalizado)),)
                desconhecidos.append(trecho.casefold())
            tokens.append(Token(trecho, span, normalizado, candidatos=candidatos))
        else:
            tokens.append(Token(trecho, span, trecho, pontuacao=trecho))

    enunciado = Enunciado(
        texto_original=texto,
        texto_normalizado=normalizar_frase(texto),
        idioma="pt-BR",
        spans=tuple(token.span for token in tokens),
        tokens=tuple(tokens),
        estado_processamento="lexical",
    )
    return ResultadoLexico(enunciado, tuple(dict.fromkeys(desconhecidos)))


def analisar_morfologia(
    resultado_lexico: ResultadoLexico,
) -> tuple[AnaliseMorfologicaAlternativa, ...]:
    """Gera análises candidatas simples, mantendo ambiguidades locais."""

    alternativas: list[AnaliseMorfologicaAlternativa] = []
    for token in resultado_lexico.enunciado.tokens:
        if token.pontuacao is not None:
            continue
        analises: list[AnaliseMorfologica] = []
        candidatos = token.candidatos or (
            CandidatoLexical(token.texto, token.normalizado),
        )
        for candidato in candidatos:
            classe = _classe_morfologica(token.normalizado)
            analises.append(
                AnaliseMorfologica(
                    token_span=token.span,
                    forma=token.texto,
                    lema=candidato.lema,
                    classe_gramatical=classe,
                    numero="plural"
                    if token.normalizado.endswith("s") and classe == "substantivo"
                    else "singular"
                    if classe == "substantivo"
                    else None,
                    confianca=candidato.confianca,
                )
            )
        if token.normalizado == "banco":
            analises.append(
                AnaliseMorfologica(
                    token_span=token.span,
                    forma=token.texto,
                    lema="bancar",
                    classe_gramatical="verbo",
                    confianca=0.35,
                )
            )
        alternativas.append(
            AnaliseMorfologicaAlternativa(token.span, tuple(analises))
        )
    return tuple(alternativas)


def _palavras_do_enunciado(resultado_lexico: ResultadoLexico) -> tuple[Token, ...]:
    return tuple(
        token
        for token in resultado_lexico.enunciado.tokens
        if token.pontuacao is None
    )


def parsear(
    resultado_lexico: ResultadoLexico,
    morfologias: tuple[AnaliseMorfologicaAlternativa, ...],
) -> ResultadoParser:
    """Produz dependências para o subconjunto sujeito-verbo-objeto."""

    tokens = _palavras_do_enunciado(resultado_lexico)
    classes = {
        alternativa.token_span: alternativa.alternativas[0].classe_gramatical
        for alternativa in morfologias
    }
    verbos = tuple(
        indice
        for indice, token in enumerate(tokens)
        if classes.get(token.span) == "verbo"
    )
    if not verbos:
        no = NoSintatico(1, "enunciado_nominal", tokens[0].span)
        return ResultadoParser(
            (EstruturaSintatica((no,), alternativas=("nominal",)),),
            (-1,),
        )

    estruturas: list[EstruturaSintatica] = []
    for verbo_indice in verbos:
        verbo = tokens[verbo_indice]
        nos = tuple(
            NoSintatico(
                indice + 1,
                "predicado" if indice == verbo_indice else classes.get(
                    token.span, "constituinte"
                ),
                token.span,
            )
            for indice, token in enumerate(tokens)
        )
        sujeito = next(
            (
                indice
                for indice in range(verbo_indice)
                if classes.get(tokens[indice].span) in {"substantivo", "pronome"}
            ),
            None,
        )
        objeto = next(
            (
                indice
                for indice in range(verbo_indice + 1, len(tokens))
                if classes.get(tokens[indice].span) in {"substantivo", "pronome"}
            ),
            None,
        )
        dependencias: list[DependenciaSintatica] = []
        if sujeito is not None:
            dependencias.append(
                DependenciaSintatica(verbo_indice + 1, sujeito + 1, "sujeito")
            )
        if objeto is not None:
            dependencias.append(
                DependenciaSintatica(verbo_indice + 1, objeto + 1, "objeto")
            )
        estrutura_alternativas = (
            ("predicado-" + verbo.normalizado,)
            if len(verbos) == 1
            else tuple(f"predicado-{tokens[indice].normalizado}" for indice in verbos)
        )
        estruturas.append(
            EstruturaSintatica(
                nos=nos,
                dependencias=tuple(dependencias),
                alternativas=estrutura_alternativas,
            )
        )
    return ResultadoParser(tuple(estruturas), verbos)


def representar_semantica(
    resultado_lexico: ResultadoLexico,
    resultado_parser: ResultadoParser,
) -> ResultadoSemantico:
    """Converte estruturas do subconjunto aprovado em proposições locais."""

    tokens = _palavras_do_enunciado(resultado_lexico)
    entidades: dict[str, EntidadeDiscursiva] = {}
    proposicoes: list[ProposicaoIntermediaria] = []
    for estrutura_numero, (estrutura, verbo_indice) in enumerate(
        zip(
            resultado_parser.estruturas,
            resultado_parser.verbo_por_estrutura,
        ),
        start=1,
    ):
        if verbo_indice < 0:
            continue
        verbo = tokens[verbo_indice]
        verbo_id = verbo_indice + 1
        predicado = PredicadoSemantico(
            tipo="evento",
            sentido=AlvoSemantico(
                "sentido", f"local-sentido-{verbo.normalizado}"
            ),
            forma_verbal=verbo.texto,
        )
        argumentos: list[ArgumentoSemantico] = []
        for dependencia in estrutura.dependencias:
            if dependencia.governador_id != verbo_id:
                continue
            alvo_token = tokens[dependencia.dependente_id - 1]
            entidade_id = f"entidade-{dependencia.dependente_id}"
            entidade = EntidadeDiscursiva(
                entidade_id=entidade_id,
                tipo="mencao",
                mencoes=(alvo_token.span,),
                origem="nucleo_simbolico",
            )
            entidades[entidade_id] = entidade
            argumentos.append(
                ArgumentoSemantico(
                    papel=dependencia.funcao,
                    alvo=AlvoSemantico("entidade", entidade_id),
                    ordem=len(argumentos) + 1,
                    funcao_sintatica=dependencia.funcao,
                )
            )
        antes_do_verbo = {token.normalizado for token in tokens[:verbo_indice]}
        polaridade = "negativa" if "não" in antes_do_verbo or "nao" in antes_do_verbo else "afirmativa"
        modalidade = (
            "epistemica"
            if "talvez" in antes_do_verbo
            else "deontica"
            if "deve" in antes_do_verbo
            else "condicional"
            if "se" in antes_do_verbo
            else "assertiva"
        )
        proposicoes.append(
            ProposicaoIntermediaria(
                proposicao_id=f"p-{estrutura_numero}",
                predicado=predicado,
                argumentos=tuple(argumentos),
                polaridade=polaridade,
                modalidade=modalidade,
            )
        )
    hipoteses = tuple(
        HipoteseAnalise(
            hipotese_id=f"parser-{indice}",
            descricao=alternativa,
            confianca=0.5,
        )
        for indice, estrutura in enumerate(resultado_parser.estruturas, start=1)
        for alternativa in estrutura.alternativas
    )
    return ResultadoSemantico(tuple(entidades.values()), tuple(proposicoes), hipoteses)


def resolver_referencias(
    resultado_lexico: ResultadoLexico,
    contexto: ContextoAnalise,
) -> ResultadoReferenciasSimbolicas:
    """Resolve pronomes somente contra entidades temporárias da sessão."""

    resolucoes: list[ResolucaoReferenciaSimbolica] = []
    pendencias: list[str] = []
    entidades_recentes = tuple(reversed(contexto.entidades))
    for token in _palavras_do_enunciado(resultado_lexico):
        if token.normalizado not in _PRONOMES:
            continue
        candidatos = tuple(entidade.entidade_id for entidade in entidades_recentes)
        if len(candidatos) == 1:
            resolucoes.append(
                ResolucaoReferenciaSimbolica(
                    token.texto, candidatos[0], candidatos
                )
            )
        elif len(candidatos) > 1:
            resolucoes.append(
                ResolucaoReferenciaSimbolica(token.texto, candidatos=candidatos)
            )
            pendencias.append(f"referência ambígua: {token.texto}")
        else:
            resolucoes.append(ResolucaoReferenciaSimbolica(token.texto))
            pendencias.append(f"referência sem antecedente: {token.texto}")

    referencias = contexto.referencias + tuple(
        ReferenciaTurno(
            contexto.turno,
            resolucao.pronome,
            resolucao.entidade_id,
        )
        for resolucao in resolucoes
    )
    contexto_atual = ContextoAnalise(
        sessao_id=contexto.sessao_id,
        turno=contexto.turno,
        topico=contexto.topico,
        entidades=contexto.entidades,
        referencias=referencias,
        pendencias=contexto.pendencias + tuple(pendencias),
        saliencia=contexto.saliencia,
    )
    return ResultadoReferenciasSimbolicas(
        tuple(resolucoes), contexto_atual, tuple(pendencias)
    )