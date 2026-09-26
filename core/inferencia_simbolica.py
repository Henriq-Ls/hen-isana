"""Primeira camada determinística de inferência simbólica.

O motor trabalha somente com afirmações e regras explícitas em memória. Ele não
abre SQLite, não executa conteúdo textual e não transforma conclusões derivadas
em fatos confirmados. Cada conclusão mantém as premissas, a regra, as
evidências e a origem que explicam sua produção.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional


POLARIDADES = ("positiva", "negativa")
ESTADOS_AFIRMACAO = ("confirmada", "incerta", "inferida")
ESTADOS_INFERENCIA = ("derivada", "incerta")
ORIGEM_INFERENCIA = "inferencia"
_ESTADOS_ATIVOS = frozenset(("confirmada", "inferida"))


def _texto(valor: str, nome: str) -> None:
    if not isinstance(valor, str):
        raise TypeError(f"{nome} deve ser texto")
    if not valor.strip():
        raise ValueError(f"{nome} não pode ser vazio")


def _tupla_textos(valor: tuple[str, ...], nome: str) -> None:
    if not isinstance(valor, tuple):
        raise TypeError(f"{nome} deve ser uma tupla imutável")
    for item in valor:
        _texto(item, nome)
    if len(set(valor)) != len(valor):
        raise ValueError(f"{nome} não pode conter valores repetidos")


@dataclass(frozen=True)
class LiteralSimbolico:
    """Identidade lógica de uma afirmação, sem representar sua verdade."""

    chave: str
    polaridade: str = "positiva"

    def __post_init__(self) -> None:
        _texto(self.chave, "chave")
        if self.polaridade not in POLARIDADES:
            raise ValueError(
                "polaridade deve ser 'positiva' ou 'negativa'"
            )

    @property
    def oposta(self) -> "LiteralSimbolico":
        return LiteralSimbolico(
            self.chave,
            "negativa" if self.polaridade == "positiva" else "positiva",
        )


@dataclass(frozen=True)
class AfirmacaoSimbolica:
    """Premissa ou conclusão com estado e proveniência explícitos."""

    literal: LiteralSimbolico
    estado: str = "confirmada"
    origem: str = "usuario"
    evidencia_ids: tuple[str, ...] = ()
    referencia: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.literal, LiteralSimbolico):
            raise TypeError("literal deve ser um LiteralSimbolico")
        if self.estado not in ESTADOS_AFIRMACAO:
            raise ValueError(
                "estado deve ser 'confirmada', 'incerta' ou 'inferida'"
            )
        _texto(self.origem, "origem")
        _tupla_textos(self.evidencia_ids, "evidencia_ids")
        if self.referencia is not None:
            _texto(self.referencia, "referencia")
        if self.estado == "inferida" and self.origem != ORIGEM_INFERENCIA:
            raise ValueError(
                "afirmação inferida precisa ter origem 'inferencia'"
            )
        if self.origem == ORIGEM_INFERENCIA and not self.referencia:
            raise ValueError(
                "afirmação de inferência precisa referenciar sua derivação"
            )

    @property
    def chave(self) -> str:
        return self.literal.chave

    @property
    def polaridade(self) -> str:
        return self.literal.polaridade


@dataclass(frozen=True)
class RegraSimbolica:
    """Regra de uma etapa: uma premissa explícita implica uma conclusão."""

    regra_id: str
    antecedente: LiteralSimbolico
    consequente: LiteralSimbolico
    origem: str = "sistema"
    evidencia_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _texto(self.regra_id, "regra_id")
        if not isinstance(self.antecedente, LiteralSimbolico):
            raise TypeError("antecedente deve ser um LiteralSimbolico")
        if not isinstance(self.consequente, LiteralSimbolico):
            raise TypeError("consequente deve ser um LiteralSimbolico")
        if self.antecedente == self.consequente:
            raise ValueError("regra não pode concluir o próprio antecedente")
        _texto(self.origem, "origem")
        _tupla_textos(self.evidencia_ids, "evidencia_ids")


@dataclass(frozen=True)
class ConflitoSimbolico:
    """Afirmações opostas preservadas sem resolução automática."""

    chave: str
    afirmacoes: tuple[AfirmacaoSimbolica, ...]
    resolvido: bool = False

    def __post_init__(self) -> None:
        _texto(self.chave, "chave")
        if not isinstance(self.afirmacoes, tuple) or not self.afirmacoes:
            raise ValueError("conflito precisa preservar suas afirmações")
        if any(
            not isinstance(afirmacao, AfirmacaoSimbolica)
            for afirmacao in self.afirmacoes
        ):
            raise TypeError("conflito contém afirmação inválida")
        if self.resolvido:
            raise ValueError(
                "a primeira camada não permite resolução automática"
            )


@dataclass(frozen=True)
class BloqueioInferencia:
    """Motivo explícito para uma regra não produzir conclusão."""

    regra_id: str
    antecedente: LiteralSimbolico
    motivo: str

    def __post_init__(self) -> None:
        _texto(self.regra_id, "regra_id")
        if not isinstance(self.antecedente, LiteralSimbolico):
            raise TypeError("antecedente deve ser um LiteralSimbolico")
        _texto(self.motivo, "motivo")


@dataclass(frozen=True)
class InferenciaSimbolica:
    """Registro auditável de uma conclusão derivada."""

    inferencia_id: str
    regra_id: str
    premissas: tuple[AfirmacaoSimbolica, ...]
    conclusao: AfirmacaoSimbolica
    origem_regra: str
    evidencia_regra_ids: tuple[str, ...] = ()
    incertezas: tuple[str, ...] = ()
    conflitos: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _texto(self.inferencia_id, "inferencia_id")
        _texto(self.regra_id, "regra_id")
        if not isinstance(self.premissas, tuple) or not self.premissas:
            raise ValueError("inferência precisa preservar suas premissas")
        if any(
            not isinstance(premissa, AfirmacaoSimbolica)
            for premissa in self.premissas
        ):
            raise TypeError("inferência contém premissa inválida")
        if not isinstance(self.conclusao, AfirmacaoSimbolica):
            raise TypeError("conclusao deve ser uma AfirmacaoSimbolica")
        if self.conclusao.origem != ORIGEM_INFERENCIA:
            raise ValueError("conclusão precisa ter origem 'inferencia'")
        if self.conclusao.referencia != self.inferencia_id:
            raise ValueError(
                "conclusão precisa referenciar a própria inferência"
            )
        _texto(self.origem_regra, "origem_regra")
        _tupla_textos(self.evidencia_regra_ids, "evidencia_regra_ids")
        _tupla_textos(self.incertezas, "incertezas")
        _tupla_textos(self.conflitos, "conflitos")

    @property
    def estado(self) -> str:
        return (
            "incerta"
            if self.conclusao.estado == "incerta"
            else "derivada"
        )

    @property
    def proveniencia(self) -> str:
        return ORIGEM_INFERENCIA


@dataclass(frozen=True)
class ResultadoInferencia:
    """Saída completa, incluindo derivação, bloqueios e conflitos."""

    afirmacoes_iniciais: tuple[AfirmacaoSimbolica, ...]
    inferencias: tuple[InferenciaSimbolica, ...]
    bloqueios: tuple[BloqueioInferencia, ...] = ()
    conflitos: tuple[ConflitoSimbolico, ...] = ()

    @property
    def conclusoes(self) -> tuple[AfirmacaoSimbolica, ...]:
        return tuple(inferencia.conclusao for inferencia in self.inferencias)

    @property
    def resolucoes_de_conflito(self) -> tuple[str, ...]:
        """A fase 3.4 não escolhe um lado; o resultado é sempre vazio."""

        return ()


class MotorInferenciaSimbolica:
    """Motor pequeno de encadeamento explícito e determinístico."""

    def __init__(self, regras: Iterable[RegraSimbolica] = ()):
        regras_tupla = tuple(regras)
        if any(not isinstance(regra, RegraSimbolica) for regra in regras_tupla):
            raise TypeError("todas as regras devem ser RegraSimbolica")
        ids = tuple(regra.regra_id for regra in regras_tupla)
        if len(set(ids)) != len(ids):
            raise ValueError("regra_id não pode ser repetido")
        self._regras = regras_tupla

    @property
    def regras(self) -> tuple[RegraSimbolica, ...]:
        return self._regras

    def inferir(
        self,
        afirmacoes: Iterable[AfirmacaoSimbolica],
    ) -> ResultadoInferencia:
        """Calcula derivações sem alterar entrada, banco ou estado persistente."""

        iniciais = tuple(afirmacoes)
        if any(
            not isinstance(afirmacao, AfirmacaoSimbolica)
            for afirmacao in iniciais
        ):
            raise TypeError("todas as afirmações devem ser AfirmacaoSimbolica")
        iniciais = tuple(
            sorted(
                set(iniciais),
                key=self._chave_afirmacao,
            )
        )
        todas = list(iniciais)
        inferencias: dict[tuple[str, LiteralSimbolico], InferenciaSimbolica] = {}
        bloqueios: dict[
            tuple[str, LiteralSimbolico, str], BloqueioInferencia
        ] = {}

        alterou = True
        while alterou:
            alterou = False
            conflitos = self._conflitos(todas)
            conflitos_por_chave = {
                conflito.chave: conflito for conflito in conflitos
            }
            for regra in self._regras:
                conflito = conflitos_por_chave.get(regra.antecedente.chave)
                if conflito is not None:
                    self._registrar_bloqueio(
                        bloqueios,
                        regra,
                        "premissa em conflito",
                    )
                    continue
                premissa, motivo = self._selecionar_premissa(
                    todas,
                    regra.antecedente,
                )
                if premissa is None:
                    self._registrar_bloqueio(bloqueios, regra, motivo)
                    continue
                estado_conclusao = (
                    "incerta"
                    if premissa.estado == "incerta"
                    else "inferida"
                )
                inferencia_id = (
                    f"inferencia:{regra.regra_id}:"
                    f"{regra.consequente.chave}:"
                    f"{regra.consequente.polaridade}"
                )
                conclusao = AfirmacaoSimbolica(
                    literal=regra.consequente,
                    estado=estado_conclusao,
                    origem=ORIGEM_INFERENCIA,
                    evidencia_ids=tuple(
                        dict.fromkeys(
                            premissa.evidencia_ids + regra.evidencia_ids
                        )
                    ),
                    referencia=inferencia_id,
                )
                chave_inferencia = (regra.regra_id, regra.consequente)
                anterior = inferencias.get(chave_inferencia)
                if anterior is not None and not self._mais_forte(
                    conclusao,
                    anterior.conclusao,
                ):
                    continue
                incertezas = (
                    ("premissa incerta",)
                    if premissa.estado == "incerta"
                    else ()
                )
                inferencia = InferenciaSimbolica(
                    inferencia_id=inferencia_id,
                    regra_id=regra.regra_id,
                    premissas=(premissa,),
                    conclusao=conclusao,
                    origem_regra=regra.origem,
                    evidencia_regra_ids=regra.evidencia_ids,
                    incertezas=incertezas,
                )
                if anterior == inferencia:
                    continue
                inferencias[chave_inferencia] = inferencia
                if conclusao not in todas:
                    todas.append(conclusao)
                    alterou = True

        conflitos = self._conflitos(todas)
        conflitos_por_chave = {
            conflito.chave: conflito for conflito in conflitos
        }
        inferencias_finais = tuple(
            self._anexar_conflitos(inferencia, conflitos_por_chave)
            for inferencia in self._ordenar_inferencias(inferencias)
        )
        return ResultadoInferencia(
            afirmacoes_iniciais=iniciais,
            inferencias=inferencias_finais,
            bloqueios=tuple(bloqueios.values()),
            conflitos=conflitos,
        )

    @staticmethod
    def _chave_afirmacao(
        afirmacao: AfirmacaoSimbolica,
    ) -> tuple[object, ...]:
        return (
            afirmacao.literal.chave,
            afirmacao.literal.polaridade,
            afirmacao.estado,
            afirmacao.origem,
            afirmacao.evidencia_ids,
            afirmacao.referencia or "",
        )

    @staticmethod
    def _mais_forte(
        nova: AfirmacaoSimbolica,
        anterior: AfirmacaoSimbolica,
    ) -> bool:
        pesos = {"incerta": 0, "inferida": 1}
        return pesos[nova.estado] > pesos[anterior.estado]

    @staticmethod
    def _selecionar_premissa(
        afirmacoes: list[AfirmacaoSimbolica],
        literal: LiteralSimbolico,
    ) -> tuple[Optional[AfirmacaoSimbolica], str]:
        opostas_ativas = [
            afirmacao
            for afirmacao in afirmacoes
            if afirmacao.literal == literal.oposta
            and afirmacao.estado in _ESTADOS_ATIVOS
        ]
        if opostas_ativas:
            return None, "premissa negada"
        correspondentes = [
            afirmacao
            for afirmacao in afirmacoes
            if afirmacao.literal == literal
        ]
        if not correspondentes:
            return None, "premissa ausente"
        return max(
            correspondentes,
            key=lambda afirmacao: (
                1 if afirmacao.estado in _ESTADOS_ATIVOS else 0,
                MotorInferenciaSimbolica._chave_afirmacao(afirmacao),
            ),
        ), ""

    @staticmethod
    def _conflitos(
        afirmacoes: list[AfirmacaoSimbolica],
    ) -> tuple[ConflitoSimbolico, ...]:
        por_chave: dict[str, list[AfirmacaoSimbolica]] = {}
        for afirmacao in afirmacoes:
            por_chave.setdefault(afirmacao.chave, []).append(afirmacao)
        conflitos = []
        for chave, itens in sorted(por_chave.items()):
            ativos = tuple(
                item for item in itens if item.estado in _ESTADOS_ATIVOS
            )
            polaridades = {item.polaridade for item in ativos}
            if polaridades == set(POLARIDADES):
                conflitos.append(
                    ConflitoSimbolico(
                        chave=chave,
                        afirmacoes=tuple(
                            sorted(ativos, key=MotorInferenciaSimbolica._chave_afirmacao)
                        ),
                    )
                )
        return tuple(conflitos)

    @staticmethod
    def _registrar_bloqueio(
        bloqueios: dict[
            tuple[str, LiteralSimbolico, str], BloqueioInferencia
        ],
        regra: RegraSimbolica,
        motivo: str,
    ) -> None:
        bloqueio = BloqueioInferencia(
            regra_id=regra.regra_id,
            antecedente=regra.antecedente,
            motivo=motivo,
        )
        bloqueios[(regra.regra_id, regra.antecedente, motivo)] = bloqueio

    @staticmethod
    def _ordenar_inferencias(
        inferencias: dict[
            tuple[str, LiteralSimbolico], InferenciaSimbolica
        ],
    ) -> tuple[InferenciaSimbolica, ...]:
        return tuple(
            sorted(
                inferencias.values(),
                key=lambda inferencia: (
                    inferencia.regra_id,
                    inferencia.conclusao.literal.chave,
                    inferencia.conclusao.literal.polaridade,
                ),
            )
        )

    @staticmethod
    def _anexar_conflitos(
        inferencia: InferenciaSimbolica,
        conflitos: dict[str, ConflitoSimbolico],
    ) -> InferenciaSimbolica:
        if inferencia.conclusao.chave not in conflitos:
            return inferencia
        return InferenciaSimbolica(
            inferencia_id=inferencia.inferencia_id,
            regra_id=inferencia.regra_id,
            premissas=inferencia.premissas,
            conclusao=inferencia.conclusao,
            origem_regra=inferencia.origem_regra,
            evidencia_regra_ids=inferencia.evidencia_regra_ids,
            incertezas=inferencia.incertezas,
            conflitos=(inferencia.conclusao.chave,),
        )
