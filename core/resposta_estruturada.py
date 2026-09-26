"""Primeira camada determinística de resposta baseada em estrutura.

O gerador recebe um plano já estruturado e somente formata os elementos
fornecidos por ele. Não recebe a frase original, não reinterpreta texto, não
acessa bancos e não executa conteúdo. A seleção entre esta resposta e o legado
é responsabilidade da camada de aplicação.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from core.contratos import (
    IntencaoIntermediaria,
    ProposicaoIntermediaria,
    ResultadoResposta,
)
from core.inferencia_simbolica import (
    ConflitoSimbolico,
    InferenciaSimbolica,
)


ESTADOS_INFORMACAO = (
    "disponivel",
    "parcial",
    "indisponivel",
    "ambiguo",
)
TIPOS_ETAPA_RESPOSTA = (
    "resposta_direta",
    "proposicoes",
    "resultados",
    "evidencias",
    "incertezas",
    "conflitos",
    "inferencias",
    "ausencia",
)
ESTADOS_RESULTADO = (
    "confirmado",
    "candidato",
    "inferido",
    "incerto",
)


def _texto(valor: str, nome: str) -> None:
    if not isinstance(valor, str):
        raise TypeError(f"{nome} deve ser texto")
    if not valor.strip():
        raise ValueError(f"{nome} não pode ser vazio")


def _tupla_textos(valor: tuple[str, ...], nome: str) -> None:
    if not isinstance(valor, tuple):
        raise TypeError(f"{nome} deve ser uma tupla")
    for item in valor:
        _texto(item, nome)


def _opcao(valor: str, opcoes: tuple[str, ...], nome: str) -> None:
    _texto(valor, nome)
    if valor not in opcoes:
        raise ValueError(f"{nome} inválido: {valor}")


@dataclass(frozen=True)
class EvidenciaResposta:
    """Evidência textual recebida pela estrutura, tratada somente como dado."""

    evidencia_id: str
    origem: str
    trecho: str
    referencia: Optional[str] = None

    def __post_init__(self) -> None:
        _texto(self.evidencia_id, "evidencia_id")
        _texto(self.origem, "origem")
        _texto(self.trecho, "trecho")
        if self.referencia is not None:
            _texto(self.referencia, "referencia")


@dataclass(frozen=True)
class ResultadoEstruturado:
    """Resultado já calculado por uma camada confiável."""

    resultado_id: str
    texto: str
    origem: str
    estado: str = "confirmado"
    evidencia_ids: tuple[str, ...] = ()
    proposicao_id: Optional[str] = None

    def __post_init__(self) -> None:
        _texto(self.resultado_id, "resultado_id")
        _texto(self.texto, "texto")
        _texto(self.origem, "origem")
        _opcao(self.estado, ESTADOS_RESULTADO, "estado")
        _tupla_textos(self.evidencia_ids, "evidencia_ids")
        if len(set(self.evidencia_ids)) != len(self.evidencia_ids):
            raise ValueError("evidencia_ids não pode conter repetição")
        if self.proposicao_id is not None:
            _texto(self.proposicao_id, "proposicao_id")


@dataclass(frozen=True)
class EtapaResposta:
    """Uma etapa do plano, com ordem definida pela estrutura recebida."""

    tipo: str
    referencias: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _opcao(self.tipo, TIPOS_ETAPA_RESPOSTA, "tipo")
        _tupla_textos(self.referencias, "referencias")
        if len(set(self.referencias)) != len(self.referencias):
            raise ValueError("referencias não pode conter repetição")
        if self.tipo in {"incertezas", "ausencia"} and self.referencias:
            raise ValueError(
                f"a etapa {self.tipo} não aceita referências nomeadas"
            )


class EstruturaRespostaIncompleta(ValueError):
    """Indica que o plano não permite uma resposta segura."""


@dataclass(frozen=True)
class PlanoResposta:
    """Entrada completa do gerador, sem o texto original da frase."""

    plano_id: str
    intencao: IntencaoIntermediaria
    etapas: tuple[EtapaResposta, ...]
    proposicoes: tuple[ProposicaoIntermediaria, ...] = ()
    resultados: tuple[ResultadoEstruturado, ...] = ()
    evidencias: tuple[EvidenciaResposta, ...] = ()
    incertezas: tuple[str, ...] = ()
    conflitos: tuple[ConflitoSimbolico, ...] = ()
    inferencias: tuple[InferenciaSimbolica, ...] = ()
    estado_informacao: str = "disponivel"
    idempotencia: str = ""
    motivo_ausencia: Optional[str] = None
    requer_esclarecimento: bool = False

    def __post_init__(self) -> None:
        _texto(self.plano_id, "plano_id")
        if not isinstance(self.intencao, IntencaoIntermediaria):
            raise TypeError("intencao deve ser uma IntencaoIntermediaria")
        if not isinstance(self.etapas, tuple) or not self.etapas:
            raise EstruturaRespostaIncompleta(
                "o plano precisa conter ao menos uma etapa"
            )
        if any(not isinstance(etapa, EtapaResposta) for etapa in self.etapas):
            raise TypeError("etapas contém item inválido")
        if any(
            not isinstance(proposicao, ProposicaoIntermediaria)
            for proposicao in self.proposicoes
        ):
            raise TypeError("proposicoes contém item inválido")
        if any(
            not isinstance(resultado, ResultadoEstruturado)
            for resultado in self.resultados
        ):
            raise TypeError("resultados contém item inválido")
        if any(
            not isinstance(evidencia, EvidenciaResposta)
            for evidencia in self.evidencias
        ):
            raise TypeError("evidencias contém item inválido")
        if any(
            not isinstance(conflito, ConflitoSimbolico)
            for conflito in self.conflitos
        ):
            raise TypeError("conflitos contém item inválido")
        if any(
            not isinstance(inferencia, InferenciaSimbolica)
            for inferencia in self.inferencias
        ):
            raise TypeError("inferencias contém item inválido")
        _tupla_textos(self.incertezas, "incertezas")
        _opcao(self.estado_informacao, ESTADOS_INFORMACAO, "estado_informacao")
        _texto(self.idempotencia, "idempotencia")
        if self.motivo_ausencia is not None:
            _texto(self.motivo_ausencia, "motivo_ausencia")
        if not isinstance(self.requer_esclarecimento, bool):
            raise TypeError("requer_esclarecimento deve ser booleano")

        proposicao_ids = {
            proposicao.proposicao_id for proposicao in self.proposicoes
        }
        resultado_ids = {resultado.resultado_id for resultado in self.resultados}
        evidencia_ids = {
            evidencia.evidencia_id for evidencia in self.evidencias
        }
        conflito_ids = {conflito.chave for conflito in self.conflitos}
        inferencia_ids = {
            inferencia.inferencia_id for inferencia in self.inferencias
        }
        if len(proposicao_ids) != len(self.proposicoes):
            raise ValueError("proposicao_id não pode ser repetido")
        if len(resultado_ids) != len(self.resultados):
            raise ValueError("resultado_id não pode ser repetido")
        if len(evidencia_ids) != len(self.evidencias):
            raise ValueError("evidencia_id não pode ser repetido")
        if len(conflito_ids) != len(self.conflitos):
            raise ValueError("conflito.chave não pode ser repetido")
        if len(inferencia_ids) != len(self.inferencias):
            raise ValueError("inferencia_id não pode ser repetido")

        for resultado in self.resultados:
            if not set(resultado.evidencia_ids) <= evidencia_ids:
                raise EstruturaRespostaIncompleta(
                    "resultado referencia evidência ausente"
                )
            if (
                resultado.proposicao_id is not None
                and resultado.proposicao_id not in proposicao_ids
            ):
                raise EstruturaRespostaIncompleta(
                    "resultado referencia proposição ausente"
                )
        for etapa in self.etapas:
            disponiveis = {
                "proposicoes": proposicao_ids,
                "resultados": resultado_ids,
                "resposta_direta": resultado_ids,
                "evidencias": evidencia_ids,
                "conflitos": conflito_ids,
                "inferencias": inferencia_ids,
            }.get(etapa.tipo, set())
            if not set(etapa.referencias) <= disponiveis:
                raise EstruturaRespostaIncompleta(
                    f"etapa {etapa.tipo} referencia estrutura ausente"
                )
        if self.estado_informacao == "indisponivel" and not any(
            etapa.tipo == "ausencia" for etapa in self.etapas
        ):
            raise EstruturaRespostaIncompleta(
                "informação indisponível precisa de uma etapa de ausência"
            )


@dataclass(frozen=True)
class RespostaEstruturada:
    """Resposta renderizada, mantendo as estruturas que a sustentam."""

    plano_id: str
    resultado: ResultadoResposta
    intencao: IntencaoIntermediaria
    estado_informacao: str
    proposicoes: tuple[ProposicaoIntermediaria, ...]
    resultados: tuple[ResultadoEstruturado, ...]
    evidencias: tuple[EvidenciaResposta, ...]
    conflitos: tuple[ConflitoSimbolico, ...]
    inferencias: tuple[InferenciaSimbolica, ...]
    proveniencias: tuple[str, ...]
    idempotencia: str


def _mapa_por_id(itens: tuple[object, ...], atributo: str) -> dict[str, object]:
    return {
        str(getattr(item, atributo)): item
        for item in itens
    }


def _texto_proposicao(proposicao: ProposicaoIntermediaria) -> str:
    return (
        f"Proposição {proposicao.proposicao_id}: "
        f"{proposicao.predicado.tipo}, "
        f"polaridade {proposicao.polaridade}, "
        f"modalidade {proposicao.modalidade}."
    )


def _texto_inferencia(inferencia: InferenciaSimbolica) -> str:
    conclusao = inferencia.conclusao
    premissas = ", ".join(
        premissa.literal.chave
        for premissa in inferencia.premissas
    )
    conflito = (
        f"; conflitos: {', '.join(inferencia.conflitos)}"
        if inferencia.conflitos
        else ""
    )
    incerteza = (
        f"; incertezas: {', '.join(inferencia.incertezas)}"
        if inferencia.incertezas
        else ""
    )
    return (
        f"Conclusão derivada: {conclusao.literal.chave} "
        f"(polaridade {conclusao.literal.polaridade}, "
        f"estado {conclusao.estado}, regra {inferencia.regra_id}, "
        f"premissas: {premissas}, origem: inferencia, "
        f"origem da regra: {inferencia.origem_regra}"
        f"{incerteza}{conflito})."
    )


def _texto_conflito(conflito: ConflitoSimbolico) -> str:
    estados = ", ".join(
        f"{afirmacao.literal.polaridade} ({afirmacao.estado})"
        for afirmacao in conflito.afirmacoes
    )
    return (
        f"Conflito preservado em {conflito.chave}: {estados}; "
        "nenhum lado foi escolhido."
    )


def _proveniencias(plano: PlanoResposta) -> tuple[str, ...]:
    valores = [
        resultado.origem for resultado in plano.resultados
    ]
    valores.extend(evidencia.origem for evidencia in plano.evidencias)
    valores.extend(inferencia.origem_regra for inferencia in plano.inferencias)
    return tuple(dict.fromkeys(valor for valor in valores if valor))


def gerar_resposta_estruturada(plano: PlanoResposta) -> RespostaEstruturada:
    """Gera texto somente a partir do ``PlanoResposta`` recebido."""

    resultados = _mapa_por_id(plano.resultados, "resultado_id")
    proposicoes = _mapa_por_id(plano.proposicoes, "proposicao_id")
    evidencias = _mapa_por_id(plano.evidencias, "evidencia_id")
    conflitos = _mapa_por_id(plano.conflitos, "chave")
    inferencias = _mapa_por_id(plano.inferencias, "inferencia_id")

    partes: list[str] = [
        f"Intenção: {plano.intencao.tipo_ato}; "
        f"objetivo: {plano.intencao.objetivo}."
    ]
    for etapa in plano.etapas:
        if etapa.tipo in {"resposta_direta", "resultados"}:
            for referencia in etapa.referencias:
                resultado = resultados[referencia]
                assert isinstance(resultado, ResultadoEstruturado)
                partes.append(
                    f"{resultado.texto} "
                    f"(origem: {resultado.origem}; estado: {resultado.estado})."
                )
                if resultado.estado == "inferido":
                    partes.append(
                        "Este resultado é inferido e não foi apresentado "
                        "como fato fornecido diretamente."
                    )
        elif etapa.tipo == "proposicoes":
            for referencia in etapa.referencias:
                proposicao = proposicoes[referencia]
                assert isinstance(proposicao, ProposicaoIntermediaria)
                partes.append(_texto_proposicao(proposicao))
        elif etapa.tipo == "evidencias":
            for referencia in etapa.referencias:
                evidencia = evidencias[referencia]
                assert isinstance(evidencia, EvidenciaResposta)
                partes.append(
                    f"Evidência {evidencia.evidencia_id} "
                    f"(origem: {evidencia.origem}): {evidencia.trecho}"
                )
        elif etapa.tipo == "incertezas":
            partes.extend(f"Incerteza: {incerteza}." for incerteza in plano.incertezas)
        elif etapa.tipo == "conflitos":
            for referencia in etapa.referencias:
                conflito = conflitos[referencia]
                assert isinstance(conflito, ConflitoSimbolico)
                partes.append(_texto_conflito(conflito))
        elif etapa.tipo == "inferencias":
            for referencia in etapa.referencias:
                inferencia = inferencias[referencia]
                assert isinstance(inferencia, InferenciaSimbolica)
                partes.append(_texto_inferencia(inferencia))
        elif etapa.tipo == "ausencia":
            motivo = plano.motivo_ausencia or plano.intencao.objetivo
            partes.append(f"Informação não disponível: {motivo}.")

    if not partes[1:]:
        raise EstruturaRespostaIncompleta(
            "o plano não produziu nenhuma parte de resposta"
        )
    if plano.estado_informacao == "parcial":
        partes.append("Estado da informação: parcial.")
    elif plano.estado_informacao == "ambiguo":
        partes.append("Estado da informação: ambíguo; é necessário esclarecimento.")
    elif plano.estado_informacao == "indisponivel":
        partes.append("Estado da informação: indisponível.")
    else:
        partes.append("Estado da informação: disponível.")

    texto = "\n".join(partes)
    resultado = ResultadoResposta(
        texto=texto,
        incertezas=plano.incertezas,
        requer_esclarecimento=(
            plano.requer_esclarecimento
            or plano.estado_informacao == "ambiguo"
        ),
    )
    return RespostaEstruturada(
        plano_id=plano.plano_id,
        resultado=resultado,
        intencao=plano.intencao,
        estado_informacao=plano.estado_informacao,
        proposicoes=plano.proposicoes,
        resultados=plano.resultados,
        evidencias=plano.evidencias,
        conflitos=plano.conflitos,
        inferencias=plano.inferencias,
        proveniencias=_proveniencias(plano),
        idempotencia=plano.idempotencia,
    )


__all__ = [
    "ESTADOS_INFORMACAO",
    "ESTADOS_RESULTADO",
    "TIPOS_ETAPA_RESPOSTA",
    "EvidenciaResposta",
    "EtapaResposta",
    "EstruturaRespostaIncompleta",
    "PlanoResposta",
    "RespostaEstruturada",
    "ResultadoEstruturado",
    "gerar_resposta_estruturada",
]