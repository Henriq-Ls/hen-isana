"""Contratos de dados entre interpretação, recuperação e composição.

Os objetos deste módulo transportam dados; não abrem bancos, não executam
ferramentas e não concedem permissões. O fluxo confiável continua responsável
por validar origem, confirmação e uso das evidências.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from math import isfinite
from typing import Any, Optional


def _texto_obrigatorio(valor: str, nome: str) -> None:
    if not isinstance(valor, str):
        raise TypeError(f"{nome} deve ser texto")
    if not valor.strip():
        raise ValueError(f"{nome} não pode ser vazio")


def _texto_opcional(valor: Optional[str], nome: str) -> None:
    if valor is not None:
        _texto_obrigatorio(valor, nome)


def _tupla_de(valor: tuple, tipo: type, nome: str) -> None:
    if not isinstance(valor, tuple):
        raise TypeError(f"{nome} deve ser uma tupla imutável")
    if any(not isinstance(item, tipo) for item in valor):
        raise TypeError(f"{nome} contém item de tipo inválido")


def _tupla_de_textos(valor: tuple[str, ...], nome: str) -> None:
    if not isinstance(valor, tuple):
        raise TypeError(f"{nome} deve ser uma tupla imutável")
    for item in valor:
        _texto_obrigatorio(item, nome)


def _ids_positivos(valor: tuple[int, ...], nome: str) -> None:
    if not isinstance(valor, tuple):
        raise TypeError(f"{nome} deve ser uma tupla imutável")
    if any(
        not isinstance(item, int) or isinstance(item, bool) or item < 1
        for item in valor
    ):
        raise ValueError(f"{nome} deve conter somente IDs inteiros positivos")


@dataclass(frozen=True)
class ItemInterpretado:
    """Entidade ou slot extraído sem implicar que seja um fato confirmado."""

    nome: str
    valor: str

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.nome, "nome")
        _texto_obrigatorio(self.valor, "valor")


@dataclass(frozen=True)
class ReferenciaTurno:
    """Referência a um turno anterior da sessão; nunca é um ID persistente."""

    turno: int
    trecho: str
    alvo: Optional[str] = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.turno, int)
            or isinstance(self.turno, bool)
            or self.turno < 1
        ):
            raise ValueError("turno deve ser um inteiro positivo")
        _texto_obrigatorio(self.trecho, "trecho")
        _texto_opcional(self.alvo, "alvo")


@dataclass(frozen=True)
class Interpretacao:
    """Saída estruturada de uma implementação de interpretação."""

    intencao: str
    expressao_candidata: Optional[str] = None
    entidades: tuple[ItemInterpretado, ...] = ()
    slots: tuple[ItemInterpretado, ...] = ()
    referencias_turnos: tuple[ReferenciaTurno, ...] = ()
    confianca: Optional[float] = None
    requer_esclarecimento: bool = False

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.intencao, "intencao")
        _texto_opcional(self.expressao_candidata, "expressao_candidata")
        _tupla_de(self.entidades, ItemInterpretado, "entidades")
        _tupla_de(self.slots, ItemInterpretado, "slots")
        _tupla_de(self.referencias_turnos, ReferenciaTurno, "referencias_turnos")
        if self.confianca is not None:
            if (
                not isinstance(self.confianca, (int, float))
                or isinstance(self.confianca, bool)
                or not 0.0 <= self.confianca <= 1.0
            ):
                raise ValueError("confianca deve estar entre 0 e 1 ou ser None")
        if not isinstance(self.requer_esclarecimento, bool):
            raise TypeError("requer_esclarecimento deve ser booleano")


@dataclass(frozen=True)
class ReferenciaRegistro:
    """Identidade de um registro sem expor uma conexão ou objeto SQLite."""

    tipo_registro: str
    registro_id: int

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.tipo_registro, "tipo_registro")
        if (
            not isinstance(self.registro_id, int)
            or isinstance(self.registro_id, bool)
            or self.registro_id < 1
        ):
            raise ValueError("registro_id deve ser um inteiro positivo")


@dataclass(frozen=True)
class CampoRecuperado:
    """Valor recuperado com proveniência e estado de confirmação explícitos."""

    registro: ReferenciaRegistro
    nome: str
    valor: str
    origem: str
    estado_confirmacao: str
    evidencia_ids: tuple[int, ...] = ()
    contexto: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.registro, ReferenciaRegistro):
            raise TypeError("registro deve ser uma ReferenciaRegistro")
        _texto_obrigatorio(self.nome, "nome")
        _texto_obrigatorio(self.valor, "valor")
        _texto_obrigatorio(self.origem, "origem")
        _texto_obrigatorio(self.estado_confirmacao, "estado_confirmacao")
        _ids_positivos(self.evidencia_ids, "evidencia_ids")
        _texto_opcional(self.contexto, "contexto")


@dataclass(frozen=True)
class ResultadoRecuperacao:
    """Candidatos, campos recuperados e contexto relevante para um turno."""

    candidatos: tuple[ReferenciaRegistro, ...] = ()
    campos: tuple[CampoRecuperado, ...] = ()
    contexto_relevante: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _tupla_de(self.candidatos, ReferenciaRegistro, "candidatos")
        _tupla_de(self.campos, CampoRecuperado, "campos")
        _tupla_de_textos(self.contexto_relevante, "contexto_relevante")
        candidatos = set(self.candidatos)
        if any(campo.registro not in candidatos for campo in self.campos):
            raise ValueError("cada campo deve pertencer a um candidato recuperado")


@dataclass(frozen=True)
class EvidenciaUsada:
    """Referência auditável a evidências que sustentam uma resposta."""

    registro: ReferenciaRegistro
    campo: str
    evidencia_ids: tuple[int, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.registro, ReferenciaRegistro):
            raise TypeError("registro deve ser uma ReferenciaRegistro")
        _texto_obrigatorio(self.campo, "campo")
        _ids_positivos(self.evidencia_ids, "evidencia_ids")
        if not self.evidencia_ids:
            raise ValueError("evidencia_ids não pode ser vazio")


@dataclass(frozen=True)
class ResultadoResposta:
    """Texto final, evidências utilizadas e incertezas do turno."""

    texto: str
    evidencias_usadas: tuple[EvidenciaUsada, ...] = ()
    incertezas: tuple[str, ...] = ()
    requer_esclarecimento: bool = False

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.texto, "texto")
        _tupla_de(self.evidencias_usadas, EvidenciaUsada, "evidencias_usadas")
        _tupla_de_textos(self.incertezas, "incertezas")
        if not isinstance(self.requer_esclarecimento, bool):
            raise TypeError("requer_esclarecimento deve ser booleano")


def _inteiro_nao_negativo(valor: int, nome: str) -> None:
    if not isinstance(valor, int) or isinstance(valor, bool) or valor < 0:
        raise ValueError(f"{nome} deve ser um inteiro não negativo")


def _inteiro_positivo(valor: int, nome: str) -> None:
    if not isinstance(valor, int) or isinstance(valor, bool) or valor < 1:
        raise ValueError(f"{nome} deve ser um inteiro positivo")


def _confianca(valor: float, nome: str = "confianca") -> None:
    if (
        not isinstance(valor, (int, float))
        or isinstance(valor, bool)
        or not 0.0 <= valor <= 1.0
    ):
        raise ValueError(f"{nome} deve estar entre 0 e 1")


def _opcao(valor: str, opcoes: tuple[str, ...], nome: str) -> None:
    _texto_obrigatorio(valor, nome)
    if valor not in opcoes:
        esperadas = ", ".join(opcoes)
        raise ValueError(f"{nome} deve ser uma destas opções: {esperadas}")


@dataclass(frozen=True)
class SpanTexto:
    """Intervalo de caracteres do texto original, com fim exclusivo."""

    inicio: int
    fim: int

    def __post_init__(self) -> None:
        _inteiro_nao_negativo(self.inicio, "inicio")
        _inteiro_nao_negativo(self.fim, "fim")
        if self.fim < self.inicio:
            raise ValueError("fim não pode ser menor que inicio")


@dataclass(frozen=True)
class CandidatoLexical:
    """Hipótese de ligação de um token a um lexema, sem escolher o sentido."""

    forma: str
    lema: str
    lexema: Optional[ReferenciaRegistro] = None
    confianca: float = 0.5

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.forma, "forma")
        _texto_obrigatorio(self.lema, "lema")
        if self.lexema is not None and not isinstance(
            self.lexema, ReferenciaRegistro
        ):
            raise TypeError("lexema deve ser uma ReferenciaRegistro ou None")
        _confianca(self.confianca)


@dataclass(frozen=True)
class Token:
    """Unidade textual com span e candidatos preservados."""

    texto: str
    span: SpanTexto
    normalizado: str
    pontuacao: Optional[str] = None
    candidatos: tuple[CandidatoLexical, ...] = ()
    expressao_candidata: Optional[str] = None

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.texto, "texto")
        if not isinstance(self.span, SpanTexto):
            raise TypeError("span deve ser um SpanTexto")
        _texto_obrigatorio(self.normalizado, "normalizado")
        _tupla_de(self.candidatos, CandidatoLexical, "candidatos")
        _texto_opcional(self.pontuacao, "pontuacao")
        _texto_opcional(self.expressao_candidata, "expressao_candidata")


@dataclass(frozen=True)
class AnaliseMorfologica:
    """Uma análise morfológica candidata para uma forma lexical."""

    token_span: SpanTexto
    forma: str
    lema: str
    classe_gramatical: str
    genero: Optional[str] = None
    numero: Optional[str] = None
    pessoa: Optional[str] = None
    tempo: Optional[str] = None
    modo: Optional[str] = None
    aspecto: Optional[str] = None
    voz: Optional[str] = None
    confianca: float = 0.5
    regra: Optional[str] = None

    def __post_init__(self) -> None:
        if not isinstance(self.token_span, SpanTexto):
            raise TypeError("token_span deve ser um SpanTexto")
        for valor, nome in (
            (self.forma, "forma"),
            (self.lema, "lema"),
            (self.classe_gramatical, "classe_gramatical"),
        ):
            _texto_obrigatorio(valor, nome)
        for valor, nome in (
            (self.genero, "genero"),
            (self.numero, "numero"),
            (self.pessoa, "pessoa"),
            (self.tempo, "tempo"),
            (self.modo, "modo"),
            (self.aspecto, "aspecto"),
            (self.voz, "voz"),
            (self.regra, "regra"),
        ):
            _texto_opcional(valor, nome)
        _confianca(self.confianca)


@dataclass(frozen=True)
class AnaliseMorfologicaAlternativa:
    """Alternativas morfológicas de um mesmo token, sem descarte implícito."""

    token_span: SpanTexto
    alternativas: tuple[AnaliseMorfologica, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.token_span, SpanTexto):
            raise TypeError("token_span deve ser um SpanTexto")
        _tupla_de(
            self.alternativas, AnaliseMorfologica, "alternativas"
        )
        if not self.alternativas:
            raise ValueError("alternativas não pode ser vazia")


@dataclass(frozen=True)
class NoSintatico:
    """Nó de uma estrutura sintática candidata."""

    no_id: int
    categoria: str
    span: SpanTexto
    cabeca_id: Optional[int] = None
    funcao: Optional[str] = None

    def __post_init__(self) -> None:
        _inteiro_positivo(self.no_id, "no_id")
        _texto_obrigatorio(self.categoria, "categoria")
        if not isinstance(self.span, SpanTexto):
            raise TypeError("span deve ser um SpanTexto")
        if self.cabeca_id is not None:
            _inteiro_positivo(self.cabeca_id, "cabeca_id")
        _texto_opcional(self.funcao, "funcao")
        if self.cabeca_id == self.no_id:
            raise ValueError("um nó não pode ser a própria cabeça")


@dataclass(frozen=True)
class DependenciaSintatica:
    """Relação dirigida entre dois nós sintáticos locais."""

    governador_id: int
    dependente_id: int
    funcao: str

    def __post_init__(self) -> None:
        _inteiro_positivo(self.governador_id, "governador_id")
        _inteiro_positivo(self.dependente_id, "dependente_id")
        _texto_obrigatorio(self.funcao, "funcao")
        if self.governador_id == self.dependente_id:
            raise ValueError("dependência não pode ligar um nó a ele mesmo")


@dataclass(frozen=True)
class EstruturaSintatica:
    """Estrutura sintática candidata, com alternativas e justificativa."""

    nos: tuple[NoSintatico, ...]
    dependencias: tuple[DependenciaSintatica, ...] = ()
    alternativas: tuple[str, ...] = ()
    custo: Optional[float] = None
    justificativa: Optional[str] = None

    def __post_init__(self) -> None:
        _tupla_de(self.nos, NoSintatico, "nos")
        _tupla_de(self.dependencias, DependenciaSintatica, "dependencias")
        _tupla_de_textos(self.alternativas, "alternativas")
        if self.custo is not None:
            if not isinstance(self.custo, (int, float)) or self.custo < 0:
                raise ValueError("custo deve ser um número não negativo")
        _texto_opcional(self.justificativa, "justificativa")
        ids = {no.no_id for no in self.nos}
        if any(
            dependencia.governador_id not in ids
            or dependencia.dependente_id not in ids
            for dependencia in self.dependencias
        ):
            raise ValueError("dependência aponta para nó inexistente")


@dataclass(frozen=True)
class AlvoSemantico:
    """Alvo local de um argumento semântico."""

    tipo: str
    identificador: str

    def __post_init__(self) -> None:
        _opcao(
            self.tipo,
            ("conceito", "sentido", "entidade", "proposicao", "fato"),
            "tipo",
        )
        _texto_obrigatorio(self.identificador, "identificador")


@dataclass(frozen=True)
class PredicadoSemantico:
    """Predicado separado de sua realização linguística e de seus argumentos."""

    tipo: str
    conceito: Optional[AlvoSemantico] = None
    sentido: Optional[AlvoSemantico] = None
    forma_verbal: Optional[str] = None
    tempo: Optional[str] = None
    aspecto: Optional[str] = None

    def __post_init__(self) -> None:
        _opcao(
            self.tipo,
            ("propriedade", "evento", "estado", "relacao", "operador"),
            "tipo",
        )
        for valor, nome in (
            (self.conceito, "conceito"),
            (self.sentido, "sentido"),
        ):
            if valor is not None and not isinstance(valor, AlvoSemantico):
                raise TypeError(f"{nome} deve ser um AlvoSemantico ou None")
        if self.conceito is None and self.sentido is None:
            raise ValueError("predicado precisa de conceito ou sentido")
        if self.conceito is not None and self.conceito.tipo != "conceito":
            raise ValueError("conceito deve ter tipo conceito")
        if self.sentido is not None and self.sentido.tipo != "sentido":
            raise ValueError("sentido deve ter tipo sentido")
        _texto_opcional(self.forma_verbal, "forma_verbal")
        _texto_opcional(self.tempo, "tempo")
        _texto_opcional(self.aspecto, "aspecto")


@dataclass(frozen=True)
class ArgumentoSemantico:
    """Participante de um predicado com papel semântico explícito."""

    papel: str
    alvo: AlvoSemantico
    ordem: int
    funcao_sintatica: Optional[str] = None
    confianca: float = 0.5

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.papel, "papel")
        if not isinstance(self.alvo, AlvoSemantico):
            raise TypeError("alvo deve ser um AlvoSemantico")
        _inteiro_positivo(self.ordem, "ordem")
        _texto_opcional(self.funcao_sintatica, "funcao_sintatica")
        _confianca(self.confianca)


@dataclass(frozen=True)
class ProposicaoIntermediaria:
    """Conteúdo semântico; não representa automaticamente um fato."""

    proposicao_id: str
    predicado: PredicadoSemantico
    argumentos: tuple[ArgumentoSemantico, ...] = ()
    polaridade: str = "afirmativa"
    modalidade: str = "assertiva"
    escopo_id: Optional[str] = None
    proposicoes_encaixadas: tuple[str, ...] = ()
    confianca: float = 0.5

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.proposicao_id, "proposicao_id")
        if not isinstance(self.predicado, PredicadoSemantico):
            raise TypeError("predicado deve ser um PredicadoSemantico")
        _tupla_de(self.argumentos, ArgumentoSemantico, "argumentos")
        _opcao(
            self.polaridade,
            ("afirmativa", "negativa", "interrogativa"),
            "polaridade",
        )
        _opcao(
            self.modalidade,
            (
                "assertiva",
                "epistemica",
                "deontica",
                "desejo",
                "hipotetica",
                "citada",
                "condicional",
            ),
            "modalidade",
        )
        _texto_opcional(self.escopo_id, "escopo_id")
        _tupla_de_textos(self.proposicoes_encaixadas, "proposicoes_encaixadas")
        _confianca(self.confianca)
        if self.escopo_id == self.proposicao_id:
            raise ValueError("uma proposição não pode estar em seu próprio escopo")
        if self.proposicao_id in self.proposicoes_encaixadas:
            raise ValueError("proposição não pode encaixar a si mesma")


@dataclass(frozen=True)
class EntidadeDiscursiva:
    """Entidade temporária de uma análise; não implica persistência global."""

    entidade_id: str
    tipo: str
    mencoes: tuple[SpanTexto, ...]
    conceito_candidato: Optional[AlvoSemantico] = None
    saliencia: float = 0.5
    origem: str = "analise"

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.entidade_id, "entidade_id")
        _texto_obrigatorio(self.tipo, "tipo")
        _tupla_de(self.mencoes, SpanTexto, "mencoes")
        if not self.mencoes:
            raise ValueError("entidade precisa de ao menos uma menção")
        if self.conceito_candidato is not None and not isinstance(
            self.conceito_candidato, AlvoSemantico
        ):
            raise TypeError("conceito_candidato deve ser um AlvoSemantico ou None")
        if self.conceito_candidato is not None and self.conceito_candidato.tipo != "conceito":
            raise ValueError("conceito_candidato deve ter tipo conceito")
        _confianca(self.saliencia, "saliencia")
        _texto_obrigatorio(self.origem, "origem")


@dataclass(frozen=True)
class HipoteseAnalise:
    """Alternativa de análise com confiança, evidências e estado explícitos."""

    hipotese_id: str
    descricao: str
    confianca: float
    evidencias: tuple[SpanTexto, ...] = ()
    alternativas: tuple[str, ...] = ()
    motivo: Optional[str] = None
    status: str = "candidata"

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.hipotese_id, "hipotese_id")
        _texto_obrigatorio(self.descricao, "descricao")
        _confianca(self.confianca)
        _tupla_de(self.evidencias, SpanTexto, "evidencias")
        _tupla_de_textos(self.alternativas, "alternativas")
        _texto_opcional(self.motivo, "motivo")
        _opcao(
            self.status,
            ("candidata", "selecionada", "rejeitada", "pendente"),
            "status",
        )


@dataclass(frozen=True)
class IntencaoIntermediaria:
    """Ato de fala e objetivo provisórios, separados da execução de ações."""

    tipo_ato: str
    objetivo: str
    parametros: tuple[ItemInterpretado, ...] = ()
    proposicao_ids: tuple[str, ...] = ()
    confianca: float = 0.5
    requer_esclarecimento: bool = False

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.tipo_ato, "tipo_ato")
        _texto_obrigatorio(self.objetivo, "objetivo")
        _tupla_de(self.parametros, ItemInterpretado, "parametros")
        _tupla_de_textos(self.proposicao_ids, "proposicao_ids")
        _confianca(self.confianca)
        if not isinstance(self.requer_esclarecimento, bool):
            raise TypeError("requer_esclarecimento deve ser booleano")


@dataclass(frozen=True)
class ContextoAnalise:
    """Contexto de sessão em memória, sem ID de banco ou persistência implícita."""

    sessao_id: str
    turno: int
    topico: Optional[str] = None
    entidades: tuple[EntidadeDiscursiva, ...] = ()
    referencias: tuple[ReferenciaTurno, ...] = ()
    pendencias: tuple[str, ...] = ()
    saliencia: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.sessao_id, "sessao_id")
        _inteiro_positivo(self.turno, "turno")
        _texto_opcional(self.topico, "topico")
        _tupla_de(self.entidades, EntidadeDiscursiva, "entidades")
        _tupla_de(self.referencias, ReferenciaTurno, "referencias")
        _tupla_de_textos(self.pendencias, "pendencias")
        _tupla_de_textos(self.saliencia, "saliencia")


@dataclass(frozen=True)
class Enunciado:
    """Entrada completa que reúne texto, tokens e análises sem persistir nada."""

    texto_original: str
    texto_normalizado: str
    idioma: str
    variante: Optional[str] = None
    spans: tuple[SpanTexto, ...] = ()
    tokens: tuple[Token, ...] = ()
    hipoteses: tuple[HipoteseAnalise, ...] = ()
    intencao: Optional[IntencaoIntermediaria] = None
    contexto: Optional[ContextoAnalise] = None
    estado_processamento: str = "recebido"
    origem: str = "entrada"

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.texto_original, "texto_original")
        _texto_obrigatorio(self.texto_normalizado, "texto_normalizado")
        _texto_obrigatorio(self.idioma, "idioma")
        _texto_opcional(self.variante, "variante")
        _tupla_de(self.spans, SpanTexto, "spans")
        _tupla_de(self.tokens, Token, "tokens")
        _tupla_de(self.hipoteses, HipoteseAnalise, "hipoteses")
        if self.intencao is not None and not isinstance(
            self.intencao, IntencaoIntermediaria
        ):
            raise TypeError("intencao deve ser uma IntencaoIntermediaria ou None")
        if self.contexto is not None and not isinstance(
            self.contexto, ContextoAnalise
        ):
            raise TypeError("contexto deve ser um ContextoAnalise ou None")
        _opcao(
            self.estado_processamento,
            ("recebido", "lexical", "morfologico", "sintatico", "semantico", "concluido"),
            "estado_processamento",
        )
        _texto_obrigatorio(self.origem, "origem")


# Contrato lógico da Parte 3. Ele representa uma proposta de conhecimento,
# não uma cópia das tabelas físicas e não contém conexão, cursor ou permissão.
TIPOS_OBJETO_CADASTRO = (
    "lexema",
    "forma_lexical",
    "analise_morfologica",
    "sentido",
    "conceito",
    "expressao",
    "proposicao",
    "argumento",
    "fato",
    "relacao_semantica",
)
ORIGENS_INFORMACAO = ("usuario", "professor", "llama", "internet", "sistema")
ENTRADAS_CADASTRO = ("manual", "json", "professor", "llama")
ESTADOS_CADASTRO = (
    "proposta",
    "em_revisao",
    "autorizada",
    "recusada",
    "persistida",
)
ESTADOS_CAMPO = ("fornecida", "proposta", "inferida", "confirmada", "rejeitada")
TIPOS_FONTE_CADASTRO = (
    "manual",
    "professor",
    "llama",
    "agente",
    "internet",
    "legado",
    "sistema",
)
TIPOS_LIGACAO_SENTIDO_CONCEITO = (
    "principal",
    "relacionado",
    "equivalente",
    "instanciacao",
)


def _chaves_mapa(
    valor: Mapping[str, Any],
    nome: str,
    obrigatorias: tuple[str, ...],
    opcionais: tuple[str, ...] = (),
) -> None:
    if not isinstance(valor, Mapping):
        raise TypeError(f"{nome} deve ser um objeto estruturado")
    permitidas = set(obrigatorias) | set(opcionais)
    desconhecidas = set(valor) - permitidas
    if desconhecidas:
        nomes = ", ".join(sorted(str(chave) for chave in desconhecidas))
        raise ValueError(f"{nome} contém campos desconhecidos: {nomes}")
    ausentes = set(obrigatorias) - set(valor)
    if ausentes:
        nomes = ", ".join(sorted(ausentes))
        raise ValueError(f"{nome} não contém campos obrigatórios: {nomes}")


def _valor_cadastro(valor: Any, nome: str) -> None:
    """Aceita apenas escalares JSON; estruturas têm classes próprias."""

    if valor is None or isinstance(valor, (str, int, bool)):
        return
    if isinstance(valor, float):
        if not isfinite(valor):
            raise ValueError(f"{nome} não pode conter NaN ou infinito")
        return
    raise TypeError(f"{nome} deve ser um valor escalar JSON")


def _ids_texto_unicos(valor: tuple[str, ...], nome: str) -> None:
    _tupla_de_textos(valor, nome)
    if len(set(valor)) != len(valor):
        raise ValueError(f"{nome} não pode conter IDs repetidos")


@dataclass(frozen=True)
class EvidenciaCadastro:
    """Evidência de uma proposta, separada da informação confirmada."""

    evidencia_id: str
    fonte_tipo: str
    fonte_identificador: str
    origem: str
    trecho: str
    referencia: Optional[str] = None
    confianca: float = 0.5
    estado: str = "candidato"
    revisao_necessaria: bool = True

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.evidencia_id, "evidencia_id")
        _opcao(self.fonte_tipo, TIPOS_FONTE_CADASTRO, "fonte_tipo")
        _texto_obrigatorio(self.fonte_identificador, "fonte_identificador")
        _texto_obrigatorio(self.origem, "origem")
        _texto_obrigatorio(self.trecho, "trecho")
        _texto_opcional(self.referencia, "referencia")
        _confianca(self.confianca)
        _opcao(
            self.estado,
            ("candidato", "aprovado", "recusado", "revertido"),
            "estado",
        )
        if not isinstance(self.revisao_necessaria, bool):
            raise TypeError("revisao_necessaria deve ser booleano")

    @classmethod
    def from_dict(cls, valor: Mapping[str, Any]) -> "EvidenciaCadastro":
        _chaves_mapa(
            valor,
            "evidencia",
            (
                "evidencia_id",
                "fonte_tipo",
                "fonte_identificador",
                "origem",
                "trecho",
            ),
            ("referencia", "confianca", "estado", "revisao_necessaria"),
        )
        return cls(
            evidencia_id=valor["evidencia_id"],
            fonte_tipo=valor["fonte_tipo"],
            fonte_identificador=valor["fonte_identificador"],
            origem=valor["origem"],
            trecho=valor["trecho"],
            referencia=valor.get("referencia"),
            confianca=valor.get("confianca", 0.5),
            estado=valor.get("estado", "candidato"),
            revisao_necessaria=valor.get("revisao_necessaria", True),
        )

    def to_dict(self) -> dict[str, Any]:
        resultado: dict[str, Any] = {
            "evidencia_id": self.evidencia_id,
            "fonte_tipo": self.fonte_tipo,
            "fonte_identificador": self.fonte_identificador,
            "origem": self.origem,
            "trecho": self.trecho,
            "confianca": self.confianca,
            "estado": self.estado,
            "revisao_necessaria": self.revisao_necessaria,
        }
        if self.referencia is not None:
            resultado["referencia"] = self.referencia
        return resultado


@dataclass(frozen=True)
class CampoCadastro:
    """Campo lógico com origem, estado e evidências explícitos."""

    nome: str
    valor: Any
    origem: str
    estado: str = "proposta"
    confianca: float = 0.5
    evidencia_ids: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.nome, "nome")
        _valor_cadastro(self.valor, "valor")
        _opcao(self.origem, ORIGENS_INFORMACAO, "origem")
        _opcao(self.estado, ESTADOS_CAMPO, "estado")
        _confianca(self.confianca)
        _ids_texto_unicos(self.evidencia_ids, "evidencia_ids")
        if self.estado == "confirmada" and not self.evidencia_ids:
            raise ValueError("campo confirmado precisa de ao menos uma evidência")

    @classmethod
    def from_dict(cls, valor: Mapping[str, Any]) -> "CampoCadastro":
        _chaves_mapa(
            valor,
            "campo",
            ("nome", "valor", "origem"),
            ("estado", "confianca", "evidencia_ids"),
        )
        return cls(
            nome=valor["nome"],
            valor=valor["valor"],
            origem=valor["origem"],
            estado=valor.get("estado", "proposta"),
            confianca=valor.get("confianca", 0.5),
            evidencia_ids=tuple(valor.get("evidencia_ids", ())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "nome": self.nome,
            "valor": self.valor,
            "origem": self.origem,
            "estado": self.estado,
            "confianca": self.confianca,
            "evidencia_ids": list(self.evidencia_ids),
        }


@dataclass(frozen=True)
class RelacaoCadastro:
    """Relação lógica entre objetos, sem IDs físicos de tabela."""

    tipo: str
    origem_objeto_id: str
    destino_tipo: str
    destino_chave: str
    ordem: int = 1
    estado: str = "proposta"
    confianca: float = 0.5
    evidencia_ids: tuple[str, ...] = ()
    tipo_ligacao: Optional[str] = None

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.tipo, "tipo")
        _texto_obrigatorio(self.origem_objeto_id, "origem_objeto_id")
        _opcao(self.destino_tipo, TIPOS_OBJETO_CADASTRO, "destino_tipo")
        _texto_obrigatorio(self.destino_chave, "destino_chave")
        _inteiro_positivo(self.ordem, "ordem")
        _opcao(self.estado, ESTADOS_CADASTRO, "estado")
        _confianca(self.confianca)
        _ids_texto_unicos(self.evidencia_ids, "evidencia_ids")
        if self.tipo == "sentido_conceito":
            _opcao(
                self.tipo_ligacao,
                TIPOS_LIGACAO_SENTIDO_CONCEITO,
                "tipo_ligacao",
            )
        elif self.tipo_ligacao is not None:
            raise ValueError(
                "tipo_ligacao só pode ser usada em sentido_conceito"
            )

    @classmethod
    def from_dict(cls, valor: Mapping[str, Any]) -> "RelacaoCadastro":
        _chaves_mapa(
            valor,
            "relacao",
            (
                "tipo",
                "origem_objeto_id",
                "destino_tipo",
                "destino_chave",
            ),
            ("ordem", "estado", "confianca", "evidencia_ids", "tipo_ligacao"),
        )
        return cls(
            tipo=valor["tipo"],
            origem_objeto_id=valor["origem_objeto_id"],
            destino_tipo=valor["destino_tipo"],
            destino_chave=valor["destino_chave"],
            ordem=valor.get("ordem", 1),
            estado=valor.get("estado", "proposta"),
            confianca=valor.get("confianca", 0.5),
            evidencia_ids=tuple(valor.get("evidencia_ids", ())),
            tipo_ligacao=valor.get("tipo_ligacao"),
        )

    def to_dict(self) -> dict[str, Any]:
        resultado = {
            "tipo": self.tipo,
            "origem_objeto_id": self.origem_objeto_id,
            "destino_tipo": self.destino_tipo,
            "destino_chave": self.destino_chave,
            "ordem": self.ordem,
            "estado": self.estado,
            "confianca": self.confianca,
            "evidencia_ids": list(self.evidencia_ids),
        }
        if self.tipo_ligacao is not None:
            resultado["tipo_ligacao"] = self.tipo_ligacao
        return resultado


@dataclass(frozen=True)
class ObjetoCadastro:
    """Objeto de conhecimento identificado, ainda independente do SQLite."""

    objeto_id: str
    tipo: str
    chave: str
    campos: tuple[CampoCadastro, ...] = ()
    relacoes: tuple[RelacaoCadastro, ...] = ()
    pendencias: tuple[str, ...] = ()
    incertezas: tuple[str, ...] = ()
    ambiguidades: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.objeto_id, "objeto_id")
        _opcao(self.tipo, TIPOS_OBJETO_CADASTRO, "tipo")
        _texto_obrigatorio(self.chave, "chave")
        _tupla_de(self.campos, CampoCadastro, "campos")
        _tupla_de(self.relacoes, RelacaoCadastro, "relacoes")
        _tupla_de_textos(self.pendencias, "pendencias")
        _tupla_de_textos(self.incertezas, "incertezas")
        _tupla_de_textos(self.ambiguidades, "ambiguidades")

    @classmethod
    def from_dict(cls, valor: Mapping[str, Any]) -> "ObjetoCadastro":
        _chaves_mapa(
            valor,
            "objeto",
            ("objeto_id", "tipo", "chave"),
            ("campos", "relacoes", "pendencias", "incertezas", "ambiguidades"),
        )
        return cls(
            objeto_id=valor["objeto_id"],
            tipo=valor["tipo"],
            chave=valor["chave"],
            campos=tuple(
                CampoCadastro.from_dict(campo)
                for campo in valor.get("campos", ())
            ),
            relacoes=tuple(
                RelacaoCadastro.from_dict(relacao)
                for relacao in valor.get("relacoes", ())
            ),
            pendencias=tuple(valor.get("pendencias", ())),
            incertezas=tuple(valor.get("incertezas", ())),
            ambiguidades=tuple(valor.get("ambiguidades", ())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "objeto_id": self.objeto_id,
            "tipo": self.tipo,
            "chave": self.chave,
            "campos": [campo.to_dict() for campo in self.campos],
            "relacoes": [relacao.to_dict() for relacao in self.relacoes],
            "pendencias": list(self.pendencias),
            "incertezas": list(self.incertezas),
            "ambiguidades": list(self.ambiguidades),
        }


@dataclass(frozen=True)
class ContratoCadastro:
    """Contrato comum para manual, JSON e professor/IA.

    A estrutura pode estar incompleta e em revisão. Nenhum estado desta classe
    autoriza sozinho a persistência; a API confiável deve exigir autorização.
    """

    proposta_id: str
    entrada: str
    objetos: tuple[ObjetoCadastro, ...] = ()
    evidencias: tuple[EvidenciaCadastro, ...] = ()
    pendencias: tuple[str, ...] = ()
    incertezas: tuple[str, ...] = ()
    estado: str = "proposta"
    idempotencia: str = ""
    ambiguidades: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _texto_obrigatorio(self.proposta_id, "proposta_id")
        _opcao(self.entrada, ENTRADAS_CADASTRO, "entrada")
        _tupla_de(self.objetos, ObjetoCadastro, "objetos")
        _tupla_de(self.evidencias, EvidenciaCadastro, "evidencias")
        _tupla_de_textos(self.pendencias, "pendencias")
        _tupla_de_textos(self.incertezas, "incertezas")
        _tupla_de_textos(self.ambiguidades, "ambiguidades")
        _opcao(self.estado, ESTADOS_CADASTRO, "estado")
        _texto_obrigatorio(self.idempotencia, "idempotencia")

        objeto_ids = tuple(objeto.objeto_id for objeto in self.objetos)
        _ids_texto_unicos(objeto_ids, "objeto_id")
        evidencia_ids = tuple(
            evidencia.evidencia_id for evidencia in self.evidencias
        )
        _ids_texto_unicos(evidencia_ids, "evidencia_id")
        evidencias_disponiveis = set(evidencia_ids)

        if not self.objetos and not self.pendencias:
            raise ValueError(
                "contrato sem objetos precisa registrar uma pendência"
            )

        for objeto in self.objetos:
            for campo in objeto.campos:
                if not set(campo.evidencia_ids) <= evidencias_disponiveis:
                    raise ValueError(
                        "campo referencia evidência inexistente"
                    )
            for relacao in objeto.relacoes:
                if relacao.origem_objeto_id not in objeto_ids:
                    raise ValueError(
                        "relação referencia objeto de origem inexistente"
                    )
                if not set(relacao.evidencia_ids) <= evidencias_disponiveis:
                    raise ValueError(
                        "relação referencia evidência inexistente"
                    )

    @classmethod
    def from_dict(cls, valor: Mapping[str, Any]) -> "ContratoCadastro":
        _chaves_mapa(
            valor,
            "contrato",
            ("proposta_id", "entrada", "idempotencia"),
            (
                "objetos",
                "evidencias",
                "pendencias",
                "incertezas",
                "estado",
                "ambiguidades",
            ),
        )
        return cls(
            proposta_id=valor["proposta_id"],
            entrada=valor["entrada"],
            objetos=tuple(
                ObjetoCadastro.from_dict(objeto)
                for objeto in valor.get("objetos", ())
            ),
            evidencias=tuple(
                EvidenciaCadastro.from_dict(evidencia)
                for evidencia in valor.get("evidencias", ())
            ),
            pendencias=tuple(valor.get("pendencias", ())),
            incertezas=tuple(valor.get("incertezas", ())),
            estado=valor.get("estado", "proposta"),
            idempotencia=valor["idempotencia"],
            ambiguidades=tuple(valor.get("ambiguidades", ())),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposta_id": self.proposta_id,
            "entrada": self.entrada,
            "objetos": [objeto.to_dict() for objeto in self.objetos],
            "evidencias": [
                evidencia.to_dict() for evidencia in self.evidencias
            ],
            "pendencias": list(self.pendencias),
            "incertezas": list(self.incertezas),
            "estado": self.estado,
            "idempotencia": self.idempotencia,
            "ambiguidades": list(self.ambiguidades),
        }