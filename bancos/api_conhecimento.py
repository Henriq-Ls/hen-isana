"""API lógica de conhecimento da Fase 3.1.

Este módulo é a única camada desta fase que conhece o mapeamento entre os
objetos lógicos e o schema de ``aprendizado/bancos/linguagem.db``. Adaptadores
de entrada recebem e devolvem ``ContratoCadastro``; eles não recebem conexão,
cursor, nome de tabela ou nome de coluna.

A fase 3.1 não persiste propostas. A conexão é aberta em modo somente leitura
e as propostas registradas ficam exclusivamente em memória até que uma fase
posterior autorize a persistência transacional.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any, Optional

from core.contratos import (
    ContratoCadastro,
    TIPOS_OBJETO_CADASTRO,
)


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DB = ROOT / "aprendizado" / "bancos" / "linguagem.db"

TIPOS_CONSULTA = TIPOS_OBJETO_CADASTRO + ("fonte", "evidencia")
ESTADOS_PROPOSTA = ("proposta", "em_revisao", "autorizada")
_TIPOS_SEMANTICOS = {"conceito", "sentido", "proposicao", "fato"}
_TIPOS_RELACAO_TEMATICA = {"expressao"}


@dataclass(frozen=True)
class CampoConhecimento:
    """Campo lógico retornado pela consulta, sem expor o nome físico."""

    nome: str
    valor: Any


@dataclass(frozen=True)
class RegistroConhecimento:
    """Registro persistido exposto como resultado lógico de consulta."""

    tipo: str
    registro_id: int
    chave: str
    estado: Optional[str]
    confianca: Optional[float]
    campos: tuple[CampoConhecimento, ...]


@dataclass(frozen=True)
class ResultadoValidacao:
    """Resultado reproduzível da validação sem alterar estado externo."""

    proposta_id: str
    valido: bool
    pendencias: tuple[str, ...] = ()
    erros: tuple[str, ...] = ()
    conflitos: tuple[str, ...] = ()
    ambigua: bool = False

    @property
    def incompleta(self) -> bool:
        return bool(self.pendencias)

    @property
    def pode_autorizar(self) -> bool:
        return (
            self.valido
            and not self.incompleta
            and not self.conflitos
            and not self.ambigua
        )


@dataclass(frozen=True)
class PropostaConhecimento:
    """Proposta registrada em memória, nunca uma linha do SQLite."""

    contrato: ContratoCadastro
    validacao: ResultadoValidacao
    estado: str = "proposta"
    revisado_por: Optional[str] = None
    autorizador: Optional[str] = None


@dataclass(frozen=True)
class _ConsultaFisica:
    tabela: str
    coluna_chave: str
    campos: tuple[tuple[str, str], ...]
    coluna_estado: Optional[str] = "estado"
    coluna_confianca: Optional[str] = "confianca"


# Somente este mapa contém nomes físicos. Ele não é exportado como parte do
# contrato e não é aceito como entrada de nenhum adaptador.
_CONSULTAS: dict[str, _ConsultaFisica] = {
    "fonte": _ConsultaFisica(
        "fontes",
        "identificador",
        (
            ("tipo", "tipo"),
            ("identificador", "identificador"),
            ("origem", "origem"),
            ("descricao", "descricao"),
        ),
        coluna_confianca="confiabilidade",
    ),
    "lexema": _ConsultaFisica(
        "lexemas",
        "lema",
        (("lema", "lema"), ("categoria_lexical", "categoria_lexical"), ("descricao", "descricao")),
        coluna_confianca=None,
    ),
    "forma_lexical": _ConsultaFisica(
        "formas_lexicais",
        "normalizada",
        (("forma", "forma"), ("normalizada", "normalizada"), ("tipo_forma", "tipo_forma")),
        coluna_confianca=None,
    ),
    "analise_morfologica": _ConsultaFisica(
        "analises_morfologicas",
        "id",
        (
            ("classe_gramatical", "classe_gramatical"),
            ("genero", "genero"),
            ("numero", "numero"),
            ("pessoa", "pessoa"),
            ("tempo", "tempo"),
            ("modo", "modo"),
            ("aspecto", "aspecto"),
            ("voz", "voz"),
        ),
        coluna_estado=None,
    ),
    "sentido": _ConsultaFisica(
        "sentidos",
        "id",
        (("definicao", "definicao"), ("contexto_uso", "contexto_uso"), ("classe_gramatical", "classe_gramatical"), ("dominio", "dominio")),
    ),
    "conceito": _ConsultaFisica(
        "conceitos",
        "chave",
        (("chave", "chave"), ("rotulo", "rotulo"), ("descricao", "descricao"), ("tipo", "tipo")),
    ),
    "expressao": _ConsultaFisica(
        "expressoes",
        "normalizada",
        (("forma", "forma"), ("normalizada", "normalizada"), ("tipo", "tipo"), ("fixidez", "fixidez")),
    ),
    "proposicao": _ConsultaFisica(
        "proposicoes",
        "id",
        (
            ("predicado_sentido", "predicado_sentido_id"),
            ("predicado_conceito", "predicado_conceito_id"),
            ("tipo_predicado", "tipo_predicado"),
            ("polaridade", "polaridade"),
            ("modalidade", "modalidade"),
            ("tempo_referencia", "tempo_referencia"),
            ("escopo", "escopo_id"),
        ),
    ),
    "argumento": _ConsultaFisica(
        "proposicao_argumentos",
        "id",
        (
            ("proposicao", "proposicao_id"),
            ("ordem", "ordem"),
            ("papel", "papel"),
            ("alvo_tipo", "alvo_tipo"),
            ("alvo_id", "alvo_id"),
            ("funcao_sintatica", "funcao_sintatica"),
        ),
        coluna_estado=None,
    ),
    "fato": _ConsultaFisica(
        "fatos",
        "id",
        (
            ("proposicao", "proposicao_id"),
            ("validade_inicio", "validade_inicio"),
            ("validade_fim", "validade_fim"),
            ("contexto", "contexto"),
        ),
    ),
    "relacao_semantica": _ConsultaFisica(
        "relacoes_semanticas",
        "id",
        (
            ("tipo_relacao", "tipo_relacao"),
            ("origem_tipo", "origem_tipo"),
            ("origem_id", "origem_id"),
            ("destino_tipo", "destino_tipo"),
            ("destino_id", "destino_id"),
            ("direcao", "direcao"),
            ("contexto", "contexto"),
        ),
    ),
    "evidencia": _ConsultaFisica(
        "evidencias",
        "id",
        (
            ("fonte", "fonte_id"),
            ("alvo_tipo", "alvo_tipo"),
            ("alvo", "alvo_id"),
            ("trecho", "trecho"),
            ("referencia", "referencia"),
            ("data", "data_evidencia"),
        ),
    ),
}


_CAMPOS_PERMITIDOS: dict[str, frozenset[str]] = {
    "lexema": frozenset({"lema", "categoria_lexical", "descricao"}),
    "forma_lexical": frozenset({"forma", "normalizada", "tipo_forma", "lexema"}),
    "analise_morfologica": frozenset(
        {"classe_gramatical", "genero", "numero", "pessoa", "tempo", "modo", "aspecto", "voz", "forma_lexical"}
    ),
    "sentido": frozenset({"definicao", "contexto_uso", "classe_gramatical", "dominio", "lexema"}),
    "conceito": frozenset({"chave", "rotulo", "descricao", "tipo"}),
    "expressao": frozenset({"forma", "normalizada", "tipo", "fixidez"}),
    "proposicao": frozenset(
        {"predicado_sentido", "predicado_conceito", "tipo_predicado", "polaridade", "modalidade", "tempo_referencia", "escopo"}
    ),
    "argumento": frozenset(
        {"proposicao", "ordem", "papel", "alvo_tipo", "alvo_chave", "funcao_sintatica"}
    ),
    "fato": frozenset(
        {"proposicao", "estado", "validade_inicio", "validade_fim", "fonte", "confianca", "contexto"}
    ),
    "relacao_semantica": frozenset(
        {"tipo_relacao", "origem_tipo", "origem_chave", "destino_tipo", "destino_chave", "direcao", "contexto"}
    ),
}

_CAMPOS_OBRIGATORIOS: dict[str, tuple[str, ...]] = {
    "lexema": ("lema", "categoria_lexical"),
    "forma_lexical": ("forma", "normalizada"),
    "analise_morfologica": ("classe_gramatical",),
    "sentido": ("definicao",),
    "conceito": ("chave", "rotulo", "tipo"),
    "expressao": ("forma", "normalizada", "tipo"),
    "proposicao": ("tipo_predicado",),
    "argumento": ("proposicao", "papel", "alvo_tipo", "alvo_chave"),
    "fato": ("proposicao", "fonte"),
    "relacao_semantica": ("tipo_relacao", "origem_tipo", "origem_chave", "destino_tipo", "destino_chave"),
}


class ConhecimentoAPI:
    """Consulta o banco novo e controla propostas somente em memória."""

    def __init__(self, caminho_db: Path | str = DEFAULT_DB):
        self.caminho_db = Path(caminho_db)
        if not self.caminho_db.exists():
            raise FileNotFoundError(f"banco linguístico não encontrado: {self.caminho_db}")
        uri = f"file:{self.caminho_db.resolve()}?mode=ro"
        self._conn = sqlite3.connect(uri, uri=True)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        self._propostas: dict[str, PropostaConhecimento] = {}
        self._idempotencias: dict[str, str] = {}

    def consultar(
        self,
        tipo: str,
        chave: Optional[str] = None,
    ) -> tuple[RegistroConhecimento, ...]:
        """Consulta registros existentes sem devolver linhas ou cursores."""
        if tipo not in TIPOS_CONSULTA:
            raise ValueError(f"tipo de consulta não suportado: {tipo}")
        configuracao = _CONSULTAS[tipo]
        colunas = ["id"]
        if configuracao.coluna_estado:
            colunas.append(configuracao.coluna_estado)
        if configuracao.coluna_confianca:
            colunas.append(configuracao.coluna_confianca)
        colunas.extend(coluna for _, coluna in configuracao.campos if coluna not in colunas)
        sql = (
            "SELECT "
            + ", ".join(colunas)
            + f" FROM {configuracao.tabela}"
        )
        parametros: tuple[Any, ...] = ()
        if chave is not None:
            if not isinstance(chave, str) or not chave.strip():
                raise ValueError("chave de consulta não pode ser vazia")
            if configuracao.coluna_chave == "id":
                try:
                    chave_id = int(chave)
                except (TypeError, ValueError) as erro:
                    raise ValueError("a chave numérica da consulta é inválida") from erro
                sql += " WHERE id = ?"
                parametros = (chave_id,)
            else:
                sql += f" WHERE {configuracao.coluna_chave} = ? COLLATE NOCASE"
                parametros = (chave.strip(),)
        sql += " ORDER BY id"
        linhas = self._conn.execute(sql, parametros).fetchall()
        registros = []
        for linha in linhas:
            campos = tuple(
                CampoConhecimento(nome, linha[coluna])
                for nome, coluna in configuracao.campos
            )
            confianca = (
                float(linha[configuracao.coluna_confianca])
                if configuracao.coluna_confianca
                and linha[configuracao.coluna_confianca] is not None
                else None
            )
            chave_registro = (
                str(linha[configuracao.coluna_chave])
                if configuracao.coluna_chave != "id"
                else str(linha["id"])
            )
            registros.append(
                RegistroConhecimento(
                    tipo=tipo,
                    registro_id=int(linha["id"]),
                    chave=chave_registro,
                    estado=(
                        str(linha[configuracao.coluna_estado])
                        if configuracao.coluna_estado
                        else None
                    ),
                    confianca=confianca,
                    campos=campos,
                )
            )
        return tuple(registros)

    def validar(self, contrato: ContratoCadastro) -> ResultadoValidacao:
        """Valida sem persistir e transforma lacunas em pendências explícitas."""
        if not isinstance(contrato, ContratoCadastro):
            raise TypeError("validar espera um ContratoCadastro")
        erros: list[str] = []
        pendencias = list(contrato.pendencias)
        conflitos: list[str] = []
        evidencias = {evidencia.evidencia_id for evidencia in contrato.evidencias}
        objeto_ids = {objeto.objeto_id for objeto in contrato.objetos}

        for objeto in contrato.objetos:
            permitidos = _CAMPOS_PERMITIDOS[objeto.tipo]
            nomes: set[str] = set()
            for campo in objeto.campos:
                if campo.nome in nomes:
                    erros.append(
                        f"objeto {objeto.objeto_id} repete o campo {campo.nome}"
                    )
                nomes.add(campo.nome)
                if campo.nome not in permitidos:
                    erros.append(
                        f"campo {campo.nome} não é permitido para {objeto.tipo}"
                    )
                if campo.estado == "confirmada" and campo.origem in {
                    "professor",
                    "llama",
                    "internet",
                }:
                    erros.append(
                        "fonte automática não pode confirmar a própria proposta"
                    )
                if not set(campo.evidencia_ids) <= evidencias:
                    erros.append(
                        f"campo {campo.nome} referencia evidência inexistente"
                    )
            for campo_obrigatorio in _CAMPOS_OBRIGATORIOS[objeto.tipo]:
                if campo_obrigatorio not in nomes:
                    pendencias.append(
                        f"objeto {objeto.objeto_id} não informa {campo_obrigatorio}"
                    )
            for relacao in objeto.relacoes:
                if relacao.origem_objeto_id not in objeto_ids:
                    erros.append("relação referencia objeto de origem inexistente")
                if relacao.origem_objeto_id != objeto.objeto_id:
                    erros.append(
                        "relação embutida precisa estar no objeto de origem"
                    )
                if not set(relacao.evidencia_ids) <= evidencias:
                    erros.append("relação referencia evidência inexistente")
                if relacao.tipo == "componente_de_expressao":
                    if objeto.tipo != "expressao":
                        erros.append(
                            "componente_de_expressao precisa ter origem expressao"
                        )
                    if relacao.destino_tipo != "lexema":
                        erros.append(
                            "componente_de_expressao precisa ter destino lexema"
                        )
                    ordem = self._ordem_componente(
                        objeto,
                        relacao.destino_chave,
                        contrato.objetos,
                    )
                    if ordem is None:
                        pendencias.append(
                            "componente_de_expressao não permite determinar "
                            "a ordem de forma única"
                        )
                    elif relacao.ordem != ordem:
                        pendencias.append(
                            "componente_de_expressao informa ordem diferente "
                            "da posição lexical determinística"
                        )
                    continue
                if objeto.tipo not in _TIPOS_SEMANTICOS:
                    erros.append(
                        "relação embutida precisa de origem semântica persistível"
                    )
                if relacao.destino_tipo not in _TIPOS_SEMANTICOS:
                    erros.append(
                        "relação embutida possui destino não persistível"
                    )

            if objeto.tipo == "relacao_semantica":
                campos_relacao = {
                    campo.nome: campo for campo in objeto.campos
                }
                tipo_relacao = campos_relacao.get("tipo_relacao")
                tipo_relacao_valor = (
                    tipo_relacao.valor if tipo_relacao is not None else None
                )
                if tipo_relacao_valor == "relacionado_no_tema":
                    if (
                        "origem_tipo" in campos_relacao
                        and campos_relacao["origem_tipo"].valor
                        not in _TIPOS_RELACAO_TEMATICA
                    ):
                        erros.append(
                            "relacionado_no_tema precisa ter origem expressao"
                        )
                    if (
                        "destino_tipo" in campos_relacao
                        and campos_relacao["destino_tipo"].valor
                        not in _TIPOS_RELACAO_TEMATICA
                    ):
                        erros.append(
                            "relacionado_no_tema precisa ter destino expressao"
                        )
                    if (
                        "direcao" not in campos_relacao
                        or campos_relacao["direcao"].valor != "simetrica"
                    ):
                        erros.append(
                            "relacionado_no_tema precisa ter direção simetrica"
                        )
                else:
                    if (
                        "origem_tipo" in campos_relacao
                        and campos_relacao["origem_tipo"].valor
                        not in _TIPOS_SEMANTICOS
                    ):
                        erros.append("origem de relação não é um tipo semântico")
                    if (
                        "destino_tipo" in campos_relacao
                        and campos_relacao["destino_tipo"].valor
                        not in _TIPOS_SEMANTICOS
                    ):
                        erros.append(
                            "destino de relação não é um tipo semântico"
                        )

        if contrato.entrada in {"professor", "llama"} and not contrato.evidencias:
            pendencias.append("proposta automática precisa registrar sua evidência")
        if contrato.ambiguidades:
            pendencias.extend(contrato.ambiguidades)
        for objeto in contrato.objetos:
            pendencias.extend(objeto.pendencias)
            if objeto.ambiguidades:
                pendencias.extend(objeto.ambiguidades)

        conflitos.extend(self._detectar_conflitos(contrato))
        erros_unicos = tuple(dict.fromkeys(erros))
        pendencias_unicas = tuple(dict.fromkeys(pendencias))
        conflitos_unicos = tuple(dict.fromkeys(conflitos))
        return ResultadoValidacao(
            proposta_id=contrato.proposta_id,
            valido=not erros_unicos,
            pendencias=pendencias_unicas,
            erros=erros_unicos,
            conflitos=conflitos_unicos,
            ambigua=bool(contrato.ambiguidades)
            or any(objeto.ambiguidades for objeto in contrato.objetos),
        )

    @staticmethod
    def _ordem_componente(
        objeto: Any,
        destino_chave: str,
        objetos: tuple[Any, ...],
    ) -> Optional[int]:
        """Retorna a posição somente para uma ocorrência lexical inequívoca."""
        campos = {campo.nome: campo.valor for campo in objeto.campos}
        expressao = campos.get("normalizada") or campos.get("forma")
        if not isinstance(expressao, str) or not expressao.strip():
            return None

        candidatos = [
            item
            for item in objetos
            if item.tipo == "lexema" and item.chave == destino_chave
        ]
        if len(candidatos) > 1:
            return None
        palavra = destino_chave
        if candidatos:
            campos_lexema = {
                campo.nome: campo.valor for campo in candidatos[0].campos
            }
            palavra = campos_lexema.get("lema") or palavra
        if not isinstance(palavra, str) or not palavra.strip():
            return None

        tokens = tuple(expressao.casefold().split())
        procurada = palavra.casefold().strip()
        ocorrencias = tuple(
            indice + 1
            for indice, token in enumerate(tokens)
            if token == procurada
        )
        if len(ocorrencias) != 1:
            return None
        return ocorrencias[0]

    def registrar_proposta(self, contrato: ContratoCadastro) -> PropostaConhecimento:
        """Registra a proposta em memória, com idempotência lógica."""
        resultado = self.validar(contrato)
        if not resultado.valido:
            detalhes = "; ".join(resultado.erros)
            raise ValueError(f"contrato inválido: {detalhes}")
        anterior = self._propostas.get(contrato.proposta_id)
        if anterior is not None:
            if anterior.contrato != contrato:
                raise ValueError("proposta_id já foi usado para outro contrato")
            return anterior
        outro_id = self._idempotencias.get(contrato.idempotencia)
        if outro_id is not None and outro_id != contrato.proposta_id:
            raise ValueError("idempotência já está associada a outra proposta")
        proposta = PropostaConhecimento(contrato=contrato, validacao=resultado)
        self._propostas[contrato.proposta_id] = proposta
        self._idempotencias[contrato.idempotencia] = contrato.proposta_id
        return proposta

    def obter_proposta(self, proposta_id: str) -> PropostaConhecimento:
        try:
            return self._propostas[proposta_id]
        except KeyError as erro:
            raise LookupError(f"proposta não encontrada: {proposta_id}") from erro

    def iniciar_revisao(self, proposta_id: str, revisor: str) -> PropostaConhecimento:
        revisor = self._texto_identidade(revisor, "revisor")
        proposta = self.obter_proposta(proposta_id)
        if proposta.estado != "proposta":
            raise ValueError("somente proposta nova pode entrar em revisão")
        atualizada = PropostaConhecimento(
            contrato=proposta.contrato,
            validacao=proposta.validacao,
            estado="em_revisao",
            revisado_por=revisor,
        )
        self._propostas[proposta_id] = atualizada
        return atualizada

    def autorizar(self, proposta_id: str, autorizador: str) -> PropostaConhecimento:
        autorizador = self._texto_identidade(autorizador, "autorizador")
        proposta = self.obter_proposta(proposta_id)
        if proposta.estado != "em_revisao":
            raise ValueError("a proposta precisa estar em revisão")
        if not proposta.validacao.pode_autorizar:
            raise ValueError(
                "proposta incompleta, ambígua, conflitante ou inválida "
                "não pode ser autorizada"
            )
        fontes = {
            evidencia.fonte_identificador
            for evidencia in proposta.contrato.evidencias
        }
        if autorizador in fontes:
            raise PermissionError("a fonte da proposta não pode autorizá-la")
        autorizada = PropostaConhecimento(
            contrato=proposta.contrato,
            validacao=proposta.validacao,
            estado="autorizada",
            revisado_por=proposta.revisado_por,
            autorizador=autorizador,
        )
        self._propostas[proposta_id] = autorizada
        return autorizada

    def persistir(self, *_args: object, **_kwargs: object) -> None:
        """A aplicação transacional pertence a fase posterior."""
        raise NotImplementedError(
            "persistência do contrato não faz parte da Fase 3.1"
        )

    def aplicar_autorizada(self, proposta_id: str) -> Any:
        """Aplica uma proposta autorizada pela ingestão controlada da 3.3."""
        proposta = self.obter_proposta(proposta_id)
        if proposta.estado != "autorizada":
            raise PermissionError(
                "somente uma proposta autorizada pode ser aplicada"
            )
        from bancos.persistencia_conhecimento import (
            _TOKEN_AUTORIZACAO,
            aplicar_contrato,
        )

        return aplicar_contrato(
            self.caminho_db,
            proposta.contrato,
            _token_autorizacao=_TOKEN_AUTORIZACAO,
        )

    def fechar(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ConhecimentoAPI":
        return self

    def __exit__(self, *_args: object) -> None:
        self.fechar()

    @staticmethod
    def _texto_identidade(valor: str, nome: str) -> str:
        if not isinstance(valor, str) or not valor.strip():
            raise ValueError(f"{nome} deve ser uma identidade textual")
        return valor.strip()

    def _detectar_conflitos(
        self,
        contrato: ContratoCadastro,
    ) -> tuple[str, ...]:
        """Compara identidades lógicas sem sobrescrever registros existentes."""
        tipos_com_chave = {
            "lexema",
            "forma_lexical",
            "conceito",
            "expressao",
        }
        conflitos: list[str] = []
        campos_comparaveis = {
            "lexema": ("lema", "categoria_lexical"),
            "forma_lexical": ("forma", "normalizada", "tipo_forma"),
            "conceito": ("chave", "rotulo", "tipo"),
            "expressao": ("forma", "normalizada", "tipo"),
        }
        for objeto in contrato.objetos:
            if objeto.tipo not in tipos_com_chave:
                # Sentidos diferentes e proposições relacionadas não devem ser
                # reduzidos a uma identidade textual única nesta fase.
                continue
            existentes = self.consultar(objeto.tipo, objeto.chave)
            if not existentes:
                continue
            propostos = {
                campo.nome: campo.valor
                for campo in objeto.campos
                if campo.nome in campos_comparaveis[objeto.tipo]
            }
            if not propostos:
                continue
            for existente in existentes:
                valores = {
                    campo.nome: campo.valor
                    for campo in existente.campos
                }
                diferentes = [
                    nome
                    for nome, valor in propostos.items()
                    if nome in valores
                    and valores[nome] is not None
                    and str(valores[nome]) != str(valor)
                ]
                if diferentes:
                    conflitos.append(
                        f"objeto {objeto.objeto_id} conflita com "
                        f"{objeto.tipo}:{objeto.chave} nos campos "
                        + ", ".join(sorted(diferentes))
                    )
        return tuple(conflitos)