"""Modo sombra determinístico da Fase 3.5.

Esta camada observa uma operação nova e a operação legada correspondente sem
substituir a saída legada. O registro fica em memória nesta fase: não há
alteração de schema, migração, escrita nos bancos legados ou persistência de
inferências.

O adaptador concreto desta fase compara a representação lexical produzida pelo
núcleo simbólico com a tokenização que o fluxo legado usa. A geração e a
comparação de respostas estruturadas pertencem à Fase 3.6.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from dataclasses import dataclass
from enum import Enum
from hashlib import sha256
import json
import math
from pathlib import Path
import re
from typing import Any, Callable, Optional

from core.contratos import ContextoAnalise
from core.nucleo_simbolico import (
    analisar_morfologia,
    parsear,
    representar_semantica,
    resolver_referencias,
    tokenizar_enunciado,
)
from core.normalizador import normalizar_frase, normalizar_termo_chave
from core.roteador import rotear
from core.resposta_estruturada import PlanoResposta
from aplicacao.resposta_estruturada import (
    ExecucaoRespostaEstruturada,
    gerar_resposta_com_fallback,
)


class StatusComparacao(str, Enum):
    """Estados observacionais possíveis para uma execução em sombra."""

    EQUIVALENTE = "equivalente"
    DIFERENTE = "diferente"
    SEM_SUPORTE = "sem_suporte"
    FALHA_NOVO = "falha_novo"
    INCOMPLETO = "incompleto"
    AMBIGUO = "ambiguo"
    FALHA_LEGADO = "falha_legado"


@dataclass(frozen=True)
class ObservacaoFluxo:
    """Saída de um adaptador, com o valor e sua representação comparável."""

    resultado: Any
    representacao: Any = None
    suportado: bool = True
    completo: bool = True
    ambiguidades: tuple[str, ...] = ()
    motivo: Optional[str] = None
    origem: str = "fluxo"

    def __post_init__(self) -> None:
        if not isinstance(self.suportado, bool):
            raise TypeError("suportado deve ser booleano")
        if not isinstance(self.completo, bool):
            raise TypeError("completo deve ser booleano")
        if not isinstance(self.ambiguidades, tuple) or any(
            not isinstance(item, str) or not item.strip()
            for item in self.ambiguidades
        ):
            raise TypeError("ambiguidades deve ser uma tupla de textos não vazios")
        if not isinstance(self.origem, str) or not self.origem.strip():
            raise ValueError("origem não pode ser vazia")
        if self.motivo is not None and (
            not isinstance(self.motivo, str) or not self.motivo.strip()
        ):
            raise ValueError("motivo deve ser texto não vazio ou None")

    @property
    def valor_comparavel(self) -> Any:
        """Usa a projeção comum quando o adaptador fornece uma."""

        return self.resultado if self.representacao is None else self.representacao


@dataclass(frozen=True)
class RegistroSombra:
    """Registro auditável e imutável de uma comparação em memória."""

    entrada: str
    operacao: str
    origem: str
    resultado_novo: str
    resultado_legado: str
    representacao_nova: str
    representacao_legado: str
    status: str
    diferencas: tuple[str, ...]
    fallback: bool
    chave_idempotencia: str
    erro_novo: Optional[str] = None
    erro_legado: Optional[str] = None


@dataclass(frozen=True)
class ExecucaoSombra:
    """Resultado exposto ao chamador: a saída legada e seu registro."""

    resultado: Any
    registro: RegistroSombra


def _forma_erro(erro: BaseException) -> dict[str, str]:
    """Representa uma exceção sem guardar traceback ou objetos mutáveis."""

    return {
        "tipo": type(erro).__name__,
        "mensagem": str(erro),
    }


def _canonico(valor: Any) -> Any:
    """Converte valores suportados em uma forma JSON determinística."""

    if valor is None or isinstance(valor, (str, bool, int)):
        return valor
    if isinstance(valor, float):
        if not math.isfinite(valor):
            raise ValueError("valores numéricos não finitos não são comparáveis")
        return valor
    if isinstance(valor, Enum):
        return _canonico(valor.value)
    if isinstance(valor, Path):
        return str(valor)
    if is_dataclass(valor) and not isinstance(valor, type):
        return {
            campo.name: _canonico(getattr(valor, campo.name))
            for campo in fields(valor)
        }
    if isinstance(valor, Mapping):
        if any(not isinstance(chave, str) for chave in valor):
            raise TypeError("mapas comparáveis precisam de chaves textuais")
        return {
            chave: _canonico(valor[chave])
            for chave in sorted(valor)
        }
    if isinstance(valor, (tuple, list)):
        return [_canonico(item) for item in valor]
    if isinstance(valor, (set, frozenset)):
        itens = [_canonico(item) for item in valor]
        return sorted(
            itens,
            key=lambda item: json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
    raise TypeError(
        "resultado não suportado para comparação determinística: "
        + type(valor).__name__
    )


def _serializar(valor: Any) -> str:
    return json.dumps(
        _canonico(valor),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _diferencas(novo: Any, legado: Any, caminho: str = "$") -> tuple[str, ...]:
    """Aponta caminhos estáveis onde as representações divergem."""

    if type(novo) is not type(legado):
        return (caminho,)
    if isinstance(novo, dict):
        diferencas: list[str] = []
        for chave in sorted(set(novo) | set(legado)):
            if chave not in novo or chave not in legado:
                diferencas.append(f"{caminho}.{chave}")
            else:
                diferencas.extend(
                    _diferencas(novo[chave], legado[chave], f"{caminho}.{chave}")
                )
        return tuple(diferencas)
    if isinstance(novo, list):
        diferencas = []
        for indice in range(max(len(novo), len(legado))):
            local = f"{caminho}[{indice}]"
            if indice >= len(novo) or indice >= len(legado):
                diferencas.append(local)
            else:
                diferencas.extend(_diferencas(novo[indice], legado[indice], local))
        return tuple(diferencas)
    return () if novo == legado else (caminho,)


def _chave_idempotencia(
    entrada: str,
    operacao: str,
    origem: str,
    contexto: Any,
) -> str:
    material = _serializar(
        {
            "entrada": entrada,
            "operacao": operacao,
            "origem": origem,
            "contexto": contexto,
        }
    )
    return sha256(material.encode("utf-8")).hexdigest()


class HistoricoSombra:
    """Armazena comparações somente em memória e sem duplicação lógica."""

    def __init__(self) -> None:
        self._registros: dict[str, RegistroSombra] = {}

    def registrar(self, registro: RegistroSombra) -> RegistroSombra:
        anterior = self._registros.get(registro.chave_idempotencia)
        if anterior is not None:
            if anterior != registro:
                raise RuntimeError(
                    "a mesma operação de sombra produziu registros diferentes"
                )
            return anterior
        self._registros[registro.chave_idempotencia] = registro
        return registro

    def listar(self) -> tuple[RegistroSombra, ...]:
        return tuple(
            self._registros[chave]
            for chave in sorted(self._registros)
        )


def _coagir_observacao(valor: Any, origem: str) -> ObservacaoFluxo:
    if isinstance(valor, ObservacaoFluxo):
        return valor
    return ObservacaoFluxo(resultado=valor, origem=origem)


class ModoSombra:
    """Executa o novo fluxo para observação e sempre conserva o legado."""

    def __init__(self, historico: Optional[HistoricoSombra] = None) -> None:
        self.historico = historico or HistoricoSombra()

    def executar(
        self,
        entrada: str,
        executar_novo: Callable[[str], Any],
        executar_legado: Callable[[str], Any],
        *,
        operacao: str = "operacao",
        origem: str = "modo_sombra",
        contexto: Any = None,
    ) -> ExecucaoSombra:
        if not isinstance(entrada, str) or not entrada.strip():
            raise ValueError("entrada deve ser texto não vazio")
        if not isinstance(operacao, str) or not operacao.strip():
            raise ValueError("operacao não pode ser vazia")
        if not isinstance(origem, str) or not origem.strip():
            raise ValueError("origem não pode ser vazia")

        chave = _chave_idempotencia(entrada, operacao, origem, contexto)
        erro_novo: Optional[BaseException] = None
        try:
            novo = _coagir_observacao(
                executar_novo(entrada),
                "fluxo_novo",
            )
        except Exception as erro:
            erro_novo = erro
            novo = ObservacaoFluxo(
                resultado=_forma_erro(erro),
                representacao=None,
                suportado=False,
                completo=False,
                motivo="exceção no fluxo novo",
                origem="fluxo_novo",
            )

        try:
            legado = _coagir_observacao(
                executar_legado(entrada),
                "fluxo_legado",
            )
        except Exception as erro:
            registro = self._montar_registro(
                entrada=entrada,
                operacao=operacao,
                origem=origem,
                novo=novo,
                legado=ObservacaoFluxo(
                    resultado=_forma_erro(erro),
                    suportado=False,
                    completo=False,
                    origem="fluxo_legado",
                ),
                status=StatusComparacao.FALHA_LEGADO,
                diferencas=("fluxo legado falhou",),
                fallback=False,
                chave=chave,
                erro_novo=erro_novo,
                erro_legado=erro,
            )
            self.historico.registrar(registro)
            raise

        if erro_novo is not None:
            status = StatusComparacao.FALHA_NOVO
            fallback = True
            diferencas = ("fluxo novo falhou",)
        else:
            status, fallback, diferencas = self._classificar(novo, legado)
        registro = self._montar_registro(
            entrada=entrada,
            operacao=operacao,
            origem=origem,
            novo=novo,
            legado=legado,
            status=status,
            diferencas=diferencas,
            fallback=fallback,
            chave=chave,
            erro_novo=erro_novo,
        )
        registro = self.historico.registrar(registro)
        return ExecucaoSombra(resultado=legado.resultado, registro=registro)

    @staticmethod
    def _classificar(
        novo: ObservacaoFluxo,
        legado: ObservacaoFluxo,
    ) -> tuple[StatusComparacao, bool, tuple[str, ...]]:
        if not novo.suportado:
            motivo = novo.motivo or "fluxo novo sem suporte"
            return (
                StatusComparacao.SEM_SUPORTE,
                True,
                (motivo,),
            )
        if novo.ambiguidades:
            return (
                StatusComparacao.AMBIGUO,
                True,
                tuple(novo.ambiguidades),
            )
        if not novo.completo:
            motivo = novo.motivo or "fluxo novo produziu resultado incompleto"
            return (
                StatusComparacao.INCOMPLETO,
                True,
                (motivo,),
            )

        representacao_nova = _canonico(novo.valor_comparavel)
        representacao_legado = _canonico(legado.valor_comparavel)
        diferencas = _diferencas(representacao_nova, representacao_legado)
        if diferencas:
            return StatusComparacao.DIFERENTE, True, diferencas
        return StatusComparacao.EQUIVALENTE, True, ()

    @staticmethod
    def _montar_registro(
        *,
        entrada: str,
        operacao: str,
        origem: str,
        novo: ObservacaoFluxo,
        legado: ObservacaoFluxo,
        status: StatusComparacao,
        diferencas: tuple[str, ...],
        fallback: bool,
        chave: str,
        erro_novo: Optional[BaseException] = None,
        erro_legado: Optional[BaseException] = None,
    ) -> RegistroSombra:
        return RegistroSombra(
            entrada=entrada,
            operacao=operacao,
            origem=origem,
            resultado_novo=_serializar(novo.resultado),
            resultado_legado=_serializar(legado.resultado),
            representacao_nova=_serializar(novo.valor_comparavel),
            representacao_legado=_serializar(legado.valor_comparavel),
            status=status.value,
            diferencas=tuple(dict.fromkeys(diferencas)),
            fallback=fallback,
            chave_idempotencia=chave,
            erro_novo=(
                _serializar(_forma_erro(erro_novo))
                if erro_novo is not None
                else None
            ),
            erro_legado=(
                _serializar(_forma_erro(erro_legado))
                if erro_legado is not None
                else None
            ),
        )


_COMANDOS_FORA_DO_ESCOPO = re.compile(
    r"^\s*(?:termo|fato|proposta-termo|proposta-fato|"
    r"proposta-correcao-fato|aprovar-proposta|recusar-proposta|"
    r"aplicar-proposta|reverter-proposta|listar-propostas)\s*:",
    flags=re.IGNORECASE,
)


def executar_analise_nova(frase: str) -> ObservacaoFluxo:
    """Executa somente as camadas simbólicas já existentes, em memória."""

    if not isinstance(frase, str) or not frase.strip():
        raise ValueError("frase deve ser texto não vazio")
    if _COMANDOS_FORA_DO_ESCOPO.match(frase):
        return ObservacaoFluxo(
            resultado={"entrada": frase},
            suportado=False,
            completo=False,
            motivo="comando explícito continua sob coordenação do legado",
            origem="fluxo_novo",
        )

    texto_analisado = normalizar_frase(frase)
    rota = rotear(texto_analisado)
    lexical = tokenizar_enunciado(texto_analisado)
    tokens = tuple(
        token for token in lexical.enunciado.tokens if token.pontuacao is None
    )
    projecao = {
        "tokens": tuple(token.normalizado for token in tokens),
    }
    if rota.intencao is not None:
        return ObservacaoFluxo(
            resultado={
                "entrada_original": frase,
                "texto_analisado": texto_analisado,
                "intencao_legada": rota.intencao.value,
                "lexico": lexical,
            },
            representacao=projecao,
            suportado=False,
            completo=False,
            motivo=(
                "intenção operacional ainda não possui resposta estruturada "
                "no fluxo novo"
            ),
            origem="fluxo_novo",
        )
    if not tokens:
        return ObservacaoFluxo(
            resultado={"entrada_original": frase, "lexico": lexical},
            representacao=projecao,
            suportado=False,
            completo=False,
            motivo="não há unidade lexical para comparar",
            origem="fluxo_novo",
        )

    morfologia = analisar_morfologia(lexical)
    parser = parsear(lexical, morfologia)
    semantica = representar_semantica(lexical, parser)
    referencias = resolver_referencias(
        lexical,
        ContextoAnalise(sessao_id="modo-sombra", turno=1),
    )
    ambiguidades = [
        "análise morfológica possui alternativas"
        for alternativa in morfologia
        if len(alternativa.alternativas) > 1
    ]
    if len(parser.estruturas) > 1:
        ambiguidades.append("parser possui mais de uma estrutura candidata")
    ambiguidades.extend(referencias.pendencias)
    resultado = {
        "entrada_original": frase,
        "texto_analisado": texto_analisado,
        "lexico": lexical,
        "morfologia": morfologia,
        "parser": parser,
        "semantica": semantica,
        "referencias": referencias,
    }
    return ObservacaoFluxo(
        resultado=resultado,
        representacao=projecao,
        ambiguidades=tuple(dict.fromkeys(ambiguidades)),
        origem="fluxo_novo",
    )


def observar_tokenizacao_legada(
    frase: str,
    tokens: list[str] | tuple[str, ...],
) -> ObservacaoFluxo:
    """Adapta a tokenização existente para a representação comum da sombra."""

    return ObservacaoFluxo(
        resultado={"tokens": tuple(tokens)},
        representacao={
            "tokens": tuple(normalizar_termo_chave(token) for token in tokens)
        },
        origem="fluxo_legado",
    )


def processar_frase_em_modo_sombra(
    frase: str,
    banco: Any,
    perguntar: Callable[[str], str] = input,
    *,
    sombra: Optional[ModoSombra] = None,
    relacoes: Any = None,
    projeto_dir: Path | None = None,
    origem_resposta: str = "usuario",
    usar_internet: bool = False,
    modo_aprendizagem: bool = True,
    permissao_memoria: Any = None,
    permissao_relacao: Any = None,
    contexto: Any = None,
    propostas: Any = None,
    ao_aceitar_sugestao: Optional[Callable[[str], None]] = None,
) -> ExecucaoSombra:
    """Executa o legado normalmente e observa a fronteira lexical nova.

    A função é opt-in. ``aplicacao.fluxo.processar_frase`` permanece intocado e
    continua sendo a entrada padrão. O retorno desta função expõe a resposta
    legada para deixar o fallback explícito ao chamador.
    """

    from aplicacao.fluxo import processar_frase, tokenizar

    comparador = sombra or ModoSombra()

    def executar_novo(_entrada: str) -> ObservacaoFluxo:
        return executar_analise_nova(frase)

    def executar_legado(_entrada: str) -> ObservacaoFluxo:
        resposta = processar_frase(
            frase,
            banco,
            perguntar,
            relacoes=relacoes,
            **(
                {"projeto_dir": projeto_dir}
                if projeto_dir is not None
                else {}
            ),
            origem_resposta=origem_resposta,
            usar_internet=usar_internet,
            modo_aprendizagem=modo_aprendizagem,
            permissao_memoria=permissao_memoria,
            permissao_relacao=permissao_relacao,
            contexto=contexto,
            propostas=propostas,
            ao_aceitar_sugestao=ao_aceitar_sugestao,
        )
        texto_legado = normalizar_frase(frase)
        tokens = tokenizar(
            texto_legado,
            banco.listar_expressoes_compostas(),
        )
        observacao = observar_tokenizacao_legada(frase, tokens)
        return ObservacaoFluxo(
            resultado=resposta,
            representacao=observacao.representacao,
            origem=observacao.origem,
        )

    return comparador.executar(
        frase,
        executar_novo,
        executar_legado,
        operacao="analise_lexica",
        origem="aplicacao.fluxo",
    )


def processar_frase_com_plano_estruturado(
    frase: str,
    banco: Any,
    plano: PlanoResposta,
    perguntar: Callable[[str], str] = input,
    *,
    relacoes: Any = None,
    projeto_dir: Path | None = None,
    origem_resposta: str = "usuario",
    usar_internet: bool = False,
    modo_aprendizagem: bool = True,
    permissao_memoria: Any = None,
    permissao_relacao: Any = None,
    contexto: Any = None,
    propostas: Any = None,
    ao_aceitar_sugestao: Optional[Callable[[str], None]] = None,
) -> ExecucaoRespostaEstruturada:
    """Executa um plano já estruturado com fallback explícito para o legado.

    O ``frase`` é usado somente pela chamada legada. O gerador novo recebe
    apenas ``plano`` e não tem acesso ao texto original. Esta entrada é
    opt-in; ``processar_frase`` e ``processar_frase_em_modo_sombra`` não são
    alterados.
    """

    from aplicacao.fluxo import processar_frase

    def executar_legado() -> Any:
        return processar_frase(
            frase,
            banco,
            perguntar,
            relacoes=relacoes,
            **(
                {"projeto_dir": projeto_dir}
                if projeto_dir is not None
                else {}
            ),
            origem_resposta=origem_resposta,
            usar_internet=usar_internet,
            modo_aprendizagem=modo_aprendizagem,
            permissao_memoria=permissao_memoria,
            permissao_relacao=permissao_relacao,
            contexto=contexto,
            propostas=propostas,
            ao_aceitar_sugestao=ao_aceitar_sugestao,
        )

    return gerar_resposta_com_fallback(plano, executar_legado)


__all__ = [
    "ExecucaoSombra",
    "HistoricoSombra",
    "ModoSombra",
    "ObservacaoFluxo",
    "RegistroSombra",
    "StatusComparacao",
    "executar_analise_nova",
    "observar_tokenizacao_legada",
    "processar_frase_com_plano_estruturado",
    "processar_frase_em_modo_sombra",
]