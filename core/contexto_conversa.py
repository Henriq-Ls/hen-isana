"""Contexto curto e não persistente para a conversa atual."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import datetime
import re
from typing import Optional


@dataclass(frozen=True)
class _PerfilPronome:
    numero: Optional[str] = None
    genero: Optional[str] = None


_PERFIS_PRONOMES = {
    "ele": _PerfilPronome("singular", "masculino"),
    "ela": _PerfilPronome("singular", "feminino"),
    "eles": _PerfilPronome("plural", "masculino"),
    "elas": _PerfilPronome("plural", "feminino"),
    "esse": _PerfilPronome("singular"),
    "essa": _PerfilPronome("singular"),
    "este": _PerfilPronome("singular"),
    "esta": _PerfilPronome("singular"),
    "aquele": _PerfilPronome("singular", "masculino"),
    "aquela": _PerfilPronome("singular", "feminino"),
    "esses": _PerfilPronome("plural"),
    "essas": _PerfilPronome("plural"),
    "estes": _PerfilPronome("plural"),
    "estas": _PerfilPronome("plural"),
    "aqueles": _PerfilPronome("plural", "masculino"),
    "aquelas": _PerfilPronome("plural", "feminino"),
    "isso": _PerfilPronome(genero="neutro"),
    "isto": _PerfilPronome(genero="neutro"),
    "aquilo": _PerfilPronome(genero="neutro"),
    "dele": _PerfilPronome("singular", "masculino"),
    "dela": _PerfilPronome("singular", "feminino"),
    "deles": _PerfilPronome("plural", "masculino"),
    "delas": _PerfilPronome("plural", "feminino"),
}


@dataclass(frozen=True)
class Mencao:
    """Entidade mencionada em uma frase da sessão atual."""

    texto_original: str
    forma_normalizada: str
    tipo_lexical_conhecido: Optional[str] = None
    numero_e_genero: Optional[str] = None
    posicao_na_frase: int = 0
    turno_em_que_apareceu: int = 0
    saliencia: float = 0.0
    eh_sujeito: bool = False


@dataclass(frozen=True)
class ResolucaoPronome:
    """Resultado da tentativa de resolver um pronome."""

    pronome: str
    mencao: Optional[Mencao] = None
    candidatos: tuple[Mencao, ...] = ()

    @property
    def resolvida(self) -> bool:
        return self.mencao is not None

    @property
    def ambigua(self) -> bool:
        return self.mencao is None and len(self.candidatos) > 1


@dataclass(frozen=True)
class ResultadoResolucao:
    """Frase com as referências resolvidas, quando isso foi possível."""

    frase_original: str
    frase_resolvida: str
    resolucoes: tuple[ResolucaoPronome, ...] = ()

    @property
    def ambiguidades(self) -> tuple[ResolucaoPronome, ...]:
        return tuple(
            resolucao
            for resolucao in self.resolucoes
            if resolucao.ambigua
        )


@dataclass(frozen=True)
class DesambiguacaoPendente:
    """Referência curta para concluir uma escolha de sentido na sessão."""

    consulta: str
    termo: str
    campo: Optional[str]
    candidato_ids: tuple[int, ...]


@dataclass(frozen=True)
class CorrecaoDigitacaoPendente:
    """Sugestão lexical temporária que exige confirmação do usuário."""

    frase_original: str
    trecho_digitado: str
    candidatos: tuple[str, ...]


@dataclass
class ContextoConversa:
    """Mantém apenas o contexto necessário para a conversa atual."""

    limite_de_turnos: int = 5
    turnos_recentes: list[str] = field(default_factory=list)
    ultima_frase_normalizada: str = ""
    entidades_ativas: list[Mencao] = field(default_factory=list)
    topico_atual: Optional[str] = None
    desambiguacao_pendente: Optional[DesambiguacaoPendente] = None
    correcao_digitacao_pendente: Optional[CorrecaoDigitacaoPendente] = None
    criado_em: datetime = field(default_factory=datetime.now)
    pergunta_pendente: Optional[str] = None
    nome_interlocutor: Optional[str] = None
    _numero_do_turno: int = field(default=0, init=False, repr=False)

    def registrar_turno(
        self,
        frase_normalizada: str,
        mencoes: list[Mencao] | tuple[Mencao, ...] = (),
        *,
        topico: Optional[str] = None,
    ) -> None:
        """Registra um turno e descarta o que excede o limite da sessão."""
        if not isinstance(frase_normalizada, str):
            raise TypeError("frase_normalizada deve ser texto")
        if self.limite_de_turnos < 1:
            raise ValueError("limite_de_turnos deve ser positivo")

        self._numero_do_turno += 1
        turno = self._numero_do_turno
        self.turnos_recentes.append(frase_normalizada)
        self.turnos_recentes = self.turnos_recentes[-self.limite_de_turnos :]
        novas_mencoes = [
            replace(
                mencao,
                turno_em_que_apareceu=turno,
                saliencia=float(turno),
            )
            for mencao in mencoes
        ]
        menor_turno = max(1, turno - self.limite_de_turnos + 1)
        self.entidades_ativas = [
            mencao
            for mencao in self.entidades_ativas
            if mencao.turno_em_que_apareceu >= menor_turno
        ]
        self.entidades_ativas.extend(novas_mencoes)
        self.ultima_frase_normalizada = frase_normalizada
        if topico is not None:
            self.topico_atual = topico
        elif novas_mencoes:
            self.topico_atual = next(
                (
                    mencao.forma_normalizada
                    for mencao in novas_mencoes
                    if mencao.eh_sujeito
                ),
                novas_mencoes[0].forma_normalizada,
            )

    def resolver_pronome(self, pronome: str) -> ResolucaoPronome:
        """Resolve um pronome usando somente as entidades desta sessão."""
        normalizado = " ".join(pronome.casefold().split())
        perfil = _PERFIS_PRONOMES.get(normalizado)
        if perfil is None:
            return ResolucaoPronome(normalizado)

        candidatos = tuple(
            mencao
            for mencao in self.entidades_ativas
            if self._combina_com_perfil(mencao, perfil)
        )
        if not candidatos:
            return ResolucaoPronome(normalizado)

        turno_mais_recente = max(
            mencao.turno_em_que_apareceu for mencao in candidatos
        )
        candidatos_recentes = tuple(
            mencao
            for mencao in candidatos
            if mencao.turno_em_que_apareceu == turno_mais_recente
        )
        sujeitos = tuple(
            mencao for mencao in candidatos_recentes if mencao.eh_sujeito
        )
        if len(sujeitos) == 1:
            return ResolucaoPronome(normalizado, sujeitos[0], candidatos)
        if len(sujeitos) > 1:
            return ResolucaoPronome(normalizado, candidatos=candidatos)
        if len(candidatos_recentes) == 1:
            return ResolucaoPronome(
                normalizado,
                candidatos_recentes[0],
                candidatos,
            )
        return ResolucaoPronome(normalizado, candidatos=candidatos)

    def resolver_frase(self, frase: str) -> ResultadoResolucao:
        """Substitui referências resolvidas sem alterar o texto persistido."""
        if not isinstance(frase, str):
            raise TypeError("frase deve ser texto")

        resolucoes: list[ResolucaoPronome] = []

        def mencao_ja_aparece_em_outro_trecho(
            match_pronome: re.Match[str],
            mencao: Mencao,
        ) -> bool:
            padrao = re.compile(
                rf"\b{re.escape(mencao.forma_normalizada)}\b",
                flags=re.IGNORECASE | re.UNICODE,
            )
            return any(
                ocorrencia.start() != match_pronome.start()
                for ocorrencia in padrao.finditer(frase)
            )

        def substituir(match: re.Match[str]) -> str:
            palavra = match.group(0)
            resolucao = self.resolver_pronome(palavra)
            pronome_repetido = (
                resolucao.resolvida
                and mencao_ja_aparece_em_outro_trecho(
                    match,
                    resolucao.mencao,
                )
            )
            if palavra.casefold() in _PERFIS_PRONOMES:
                resolucoes.append(
                    ResolucaoPronome(resolucao.pronome)
                    if pronome_repetido
                    else resolucao
                )
            if resolucao.resolvida and not pronome_repetido:
                return resolucao.mencao.forma_normalizada
            return palavra

        frase_resolvida = re.sub(
            r"\b[\wÀ-ÿ]+\b",
            substituir,
            frase,
            flags=re.UNICODE,
        )
        return ResultadoResolucao(
            frase_original=frase,
            frase_resolvida=frase_resolvida,
            resolucoes=tuple(resolucoes),
        )

    @staticmethod
    def _combina_com_perfil(
        mencao: Mencao,
        perfil: _PerfilPronome,
    ) -> bool:
        informacao = (mencao.numero_e_genero or "").casefold()
        if perfil.numero and informacao:
            if perfil.numero not in informacao:
                return False
        if perfil.genero and informacao:
            if perfil.genero not in informacao:
                return False
        return True