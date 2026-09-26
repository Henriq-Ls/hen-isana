"""Aplicação transacional do contrato lógico no banco linguístico.

Este módulo pertence à fronteira confiável de ``bancos``. Adaptadores de
entrada não escolhem tabelas nem colunas; recebem somente um contrato que já
foi validado e autorizado pela ``ConhecimentoAPI``.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import sqlite3
from typing import Any, Optional

from core.contratos import (
    CampoCadastro,
    ContratoCadastro,
    EvidenciaCadastro,
    ObjetoCadastro,
    RelacaoCadastro,
)

_TOKEN_AUTORIZACAO = object()


@dataclass(frozen=True)
class ResultadoAplicacao:
    """Auditoria em memória da transação concluída."""

    ids_por_objeto: tuple[tuple[str, int], ...]
    evidencias_criadas: tuple[int, ...]
    registros_reutilizados: tuple[str, ...]


_ORDEM_OBJETOS = (
    "lexema",
    "conceito",
    "forma_lexical",
    "sentido",
    "expressao",
    "analise_morfologica",
    "proposicao",
    "fato",
    "argumento",
    "relacao_semantica",
)
_TIPOS_SEMANTICOS = {"conceito", "sentido", "proposicao", "fato"}
_TIPOS_RELACAO_TEMATICA = {"expressao"}
_TIPOS_EVIDENCIA = {
    "lexema",
    "forma_lexical",
    "analise_morfologica",
    "sentido",
    "conceito",
    "expressao",
    "proposicao",
    "fato",
    "relacao_semantica",
}


def aplicar_contrato(
    caminho_db: Path | str,
    contrato: ContratoCadastro,
    *,
    _token_autorizacao: object | None = None,
) -> ResultadoAplicacao:
    """Aplica o contrato inteiro em uma transação ou não aplica nada."""
    if not isinstance(contrato, ContratoCadastro):
        raise TypeError("contrato deve ser um ContratoCadastro")
    if _token_autorizacao is not _TOKEN_AUTORIZACAO:
        raise PermissionError(
            "aplicação transacional exige autorização explícita da API"
        )
    caminho = Path(caminho_db)
    conn = sqlite3.connect(caminho)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    aplicador = _Aplicador(conn, contrato)
    try:
        conn.execute("BEGIN")
        resultado = aplicador.executar()
        conn.commit()
        return resultado
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class _Aplicador:
    def __init__(self, conn: sqlite3.Connection, contrato: ContratoCadastro):
        self.conn = conn
        self.contrato = contrato
        self.objetos_por_id = {
            objeto.objeto_id: objeto for objeto in contrato.objetos
        }
        self.ids_por_objeto: dict[str, int] = {}
        self.ids_por_tipo_chave: dict[tuple[str, str], int] = {}
        self.fontes: dict[str, int] = {}
        self.reutilizados: list[str] = []
        self.evidencias_criadas: list[int] = []
        self.alvos_evidencia: set[tuple[str, int, str]] = set()

    def executar(self) -> ResultadoAplicacao:
        self._preparar_fontes()
        for tipo in _ORDEM_OBJETOS:
            for objeto in self.contrato.objetos:
                if objeto.tipo == tipo:
                    self._aplicar_objeto(objeto)
        self._aplicar_relacoes_embutidas()
        self._aplicar_evidencias()
        return ResultadoAplicacao(
            ids_por_objeto=tuple(sorted(self.ids_por_objeto.items())),
            evidencias_criadas=tuple(self.evidencias_criadas),
            registros_reutilizados=tuple(self.reutilizados),
        )

    def _preparar_fontes(self) -> None:
        for evidencia in self.contrato.evidencias:
            linha = self.conn.execute(
                "SELECT id FROM fontes WHERE tipo = ? AND identificador = ?",
                (evidencia.fonte_tipo, evidencia.fonte_identificador),
            ).fetchone()
            if linha is None:
                fonte_id = self.conn.execute(
                    "INSERT INTO fontes "
                    "(tipo, identificador, origem, descricao, confiabilidade, estado) "
                    "VALUES (?, ?, ?, ?, ?, 'aprovado')",
                    (
                        evidencia.fonte_tipo,
                        evidencia.fonte_identificador,
                        evidencia.origem,
                        evidencia.referencia,
                        evidencia.confianca,
                    ),
                ).lastrowid
            else:
                fonte_id = int(linha["id"])
                self.reutilizados.append(
                    f"fonte:{evidencia.fonte_tipo}:{evidencia.fonte_identificador}"
                )
            self.fontes[evidencia.evidencia_id] = int(fonte_id)

    def _aplicar_objeto(self, objeto: ObjetoCadastro) -> None:
        campos = {campo.nome: campo for campo in objeto.campos}
        if objeto.tipo == "lexema":
            registro_id = self._lexema(objeto, campos)
        elif objeto.tipo == "conceito":
            registro_id = self._conceito(objeto, campos)
        elif objeto.tipo == "forma_lexical":
            registro_id = self._forma_lexical(objeto, campos)
        elif objeto.tipo == "sentido":
            registro_id = self._sentido(objeto, campos)
        elif objeto.tipo == "expressao":
            registro_id = self._expressao(objeto, campos)
        elif objeto.tipo == "analise_morfologica":
            registro_id = self._analise(objeto, campos)
        elif objeto.tipo == "proposicao":
            registro_id = self._proposicao(objeto, campos)
        elif objeto.tipo == "fato":
            registro_id = self._fato(objeto, campos)
        elif objeto.tipo == "argumento":
            registro_id = self._argumento(objeto, campos)
        elif objeto.tipo == "relacao_semantica":
            registro_id = self._relacao(objeto, campos)
        else:
            raise ValueError(f"tipo de objeto não aplicável: {objeto.tipo}")
        self.ids_por_objeto[objeto.objeto_id] = registro_id
        self.ids_por_tipo_chave[(objeto.tipo, objeto.chave)] = registro_id
        for campo in objeto.campos:
            for evidencia_id in campo.evidencia_ids:
                self._registrar_alvo_evidencia(
                    evidencia_id,
                    objeto.tipo,
                    registro_id,
                    objeto.objeto_id,
                )

    def _lexema(
        self,
        objeto: ObjetoCadastro,
        campos: dict[str, CampoCadastro],
    ) -> int:
        lema = self._texto(campos, "lema")
        categoria = self._texto(campos, "categoria_lexical")
        existente = self.conn.execute(
            "SELECT id FROM lexemas WHERE lema = ? AND categoria_lexical = ?",
            (lema, categoria),
        ).fetchone()
        if existente is not None:
            self.reutilizados.append(f"lexema:{objeto.chave}")
            return int(existente["id"])
        return int(
            self.conn.execute(
                "INSERT INTO lexemas "
                "(lema, categoria_lexical, descricao, estado) "
                "VALUES (?, ?, ?, 'aprovado')",
                (lema, categoria, self._valor(campos, "descricao")),
            ).lastrowid
        )

    def _conceito(
        self,
        objeto: ObjetoCadastro,
        campos: dict[str, CampoCadastro],
    ) -> int:
        chave = self._texto(campos, "chave", objeto.chave)
        rotulo = self._texto(campos, "rotulo")
        tipo = self._texto(campos, "tipo")
        existente = self.conn.execute(
            "SELECT id FROM conceitos WHERE chave = ?", (chave,)
        ).fetchone()
        if existente is not None:
            self.reutilizados.append(f"conceito:{chave}")
            return int(existente["id"])
        return int(
            self.conn.execute(
                "INSERT INTO conceitos "
                "(chave, rotulo, descricao, tipo, estado) "
                "VALUES (?, ?, ?, ?, 'aprovado')",
                (chave, rotulo, self._valor(campos, "descricao"), tipo),
            ).lastrowid
        )

    def _forma_lexical(
        self,
        objeto: ObjetoCadastro,
        campos: dict[str, CampoCadastro],
    ) -> int:
        lexema_id = self._resolver_lexema(campos.get("lexema"))
        forma = self._texto(campos, "forma")
        normalizada = self._texto(campos, "normalizada")
        tipo_forma = self._valor(campos, "tipo_forma") or "flexionada"
        existente = self.conn.execute(
            "SELECT id FROM formas_lexicais "
            "WHERE lexema_id = ? AND normalizada = ?",
            (lexema_id, normalizada),
        ).fetchone()
        if existente is not None:
            self.reutilizados.append(f"forma_lexical:{objeto.chave}")
            return int(existente["id"])
        return int(
            self.conn.execute(
                "INSERT INTO formas_lexicais "
                "(lexema_id, forma, normalizada, tipo_forma, estado) "
                "VALUES (?, ?, ?, ?, 'aprovado')",
                (lexema_id, forma, normalizada, tipo_forma),
            ).lastrowid
        )

    def _sentido(
        self,
        objeto: ObjetoCadastro,
        campos: dict[str, CampoCadastro],
    ) -> int:
        lexema_id = self._resolver_lexema(campos.get("lexema"))
        definicao = self._texto(campos, "definicao")
        contexto = self._valor(campos, "contexto_uso")
        existente = self.conn.execute(
            "SELECT id FROM sentidos "
            "WHERE lexema_id = ? AND definicao = ? "
            "AND (contexto_uso IS ? OR contexto_uso = ?)",
            (lexema_id, definicao, contexto, contexto),
        ).fetchone()
        if existente is not None:
            self.reutilizados.append(f"sentido:{objeto.chave}")
            return int(existente["id"])
        return int(
            self.conn.execute(
                "INSERT INTO sentidos "
                "(lexema_id, definicao, contexto_uso, classe_gramatical, dominio, estado) "
                "VALUES (?, ?, ?, ?, ?, 'aprovado')",
                (
                    lexema_id,
                    definicao,
                    contexto,
                    self._valor(campos, "classe_gramatical"),
                    self._valor(campos, "dominio"),
                ),
            ).lastrowid
        )

    def _expressao(
        self,
        objeto: ObjetoCadastro,
        campos: dict[str, CampoCadastro],
    ) -> int:
        forma = self._texto(campos, "forma")
        normalizada = self._texto(campos, "normalizada")
        tipo = self._texto(campos, "tipo")
        existente = self.conn.execute(
            "SELECT id FROM expressoes WHERE normalizada = ?",
            (normalizada,),
        ).fetchone()
        if existente is not None:
            self.reutilizados.append(f"expressao:{objeto.chave}")
            return int(existente["id"])
        return int(
            self.conn.execute(
                "INSERT INTO expressoes "
                "(forma, normalizada, tipo, fixidez, estado, confianca) "
                "VALUES (?, ?, ?, ?, 'aprovado', ?)",
                (
                    forma,
                    normalizada,
                    tipo,
                    self._numero(campos, "fixidez", 0.5),
                    self._confianca(campos),
                ),
            ).lastrowid
        )

    def _analise(
        self,
        objeto: ObjetoCadastro,
        campos: dict[str, CampoCadastro],
    ) -> int:
        forma_id = self._resolver_tipo_chave(
            "forma_lexical",
            campos.get("forma_lexical"),
        )
        classe = self._texto(campos, "classe_gramatical")
        colunas = (
            "forma_lexical_id", "classe_gramatical", "genero", "numero",
            "pessoa", "tempo", "modo", "aspecto", "voz", "confianca",
        )
        valores = (
            forma_id,
            self._valor(campos, "classe_gramatical"),
            self._valor(campos, "genero"),
            self._valor(campos, "numero"),
            self._valor(campos, "pessoa"),
            self._valor(campos, "tempo"),
            self._valor(campos, "modo"),
            self._valor(campos, "aspecto"),
            self._valor(campos, "voz"),
            self._confianca(campos),
        )
        existente = self.conn.execute(
            "SELECT id FROM analises_morfologicas "
            "WHERE forma_lexical_id = ? AND classe_gramatical = ? "
            "AND (genero IS ? OR genero = ?) AND (numero IS ? OR numero = ?)",
            (forma_id, classe, valores[2], valores[2], valores[3], valores[3]),
        ).fetchone()
        if existente is not None:
            self.reutilizados.append(f"analise_morfologica:{objeto.chave}")
            return int(existente["id"])
        return int(
            self.conn.execute(
                f"INSERT INTO analises_morfologicas ({', '.join(colunas)}) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                valores,
            ).lastrowid
        )

    def _proposicao(
        self,
        objeto: ObjetoCadastro,
        campos: dict[str, CampoCadastro],
    ) -> int:
        sentido_id = self._resolver_tipo_chave(
            "sentido",
            campos.get("predicado_sentido"),
            permitir_nulo=True,
        )
        conceito_id = self._resolver_tipo_chave(
            "conceito",
            campos.get("predicado_conceito"),
            permitir_nulo=True,
        )
        if sentido_id is None and conceito_id is None:
            raise ValueError("proposição precisa de predicado lógico resolvível")
        fonte_id = self._resolver_fonte(campos.get("fonte"))
        valores = (
            sentido_id,
            conceito_id,
            self._texto(campos, "tipo_predicado"),
            self._valor(campos, "polaridade") or "afirmativa",
            self._valor(campos, "modalidade") or "assertiva",
            self._valor(campos, "tempo_referencia"),
            self._resolver_tipo_chave(
                "proposicao",
                campos.get("escopo"),
                permitir_nulo=True,
            ),
            "aprovado",
            self._confianca(campos),
            fonte_id,
        )
        existente = self.conn.execute(
            "SELECT id FROM proposicoes WHERE "
            "predicado_sentido_id IS ? AND predicado_conceito_id IS ? "
            "AND tipo_predicado = ? AND polaridade = ? AND modalidade = ? "
            "AND tempo_referencia IS ? AND escopo_id IS ?",
            valores[:7] + (None,) * 0,
        ).fetchone()
        if existente is not None:
            self.reutilizados.append(f"proposicao:{objeto.chave}")
            return int(existente["id"])
        return int(
            self.conn.execute(
                "INSERT INTO proposicoes "
                "(predicado_sentido_id, predicado_conceito_id, tipo_predicado, "
                "polaridade, modalidade, tempo_referencia, escopo_id, estado, "
                "confianca, fonte_id) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                valores,
            ).lastrowid
        )

    def _fato(
        self,
        objeto: ObjetoCadastro,
        campos: dict[str, CampoCadastro],
    ) -> int:
        proposicao_id = self._resolver_tipo_chave(
            "proposicao",
            campos.get("proposicao"),
        )
        fonte_id = self._resolver_fonte(campos.get("fonte"))
        valores = (
            proposicao_id,
            "aprovado",
            self._valor(campos, "validade_inicio"),
            self._valor(campos, "validade_fim"),
            fonte_id,
            self._confianca(campos),
            self._valor(campos, "contexto"),
        )
        existente = self.conn.execute(
            "SELECT id FROM fatos WHERE proposicao_id = ? AND fonte_id = ? "
            "AND (contexto IS ? OR contexto = ?)",
            (proposicao_id, fonte_id, valores[6], valores[6]),
        ).fetchone()
        if existente is not None:
            self.reutilizados.append(f"fato:{objeto.chave}")
            return int(existente["id"])
        return int(
            self.conn.execute(
                "INSERT INTO fatos "
                "(proposicao_id, estado, validade_inicio, validade_fim, "
                "fonte_id, confianca, contexto) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                valores,
            ).lastrowid
        )

    def _argumento(
        self,
        objeto: ObjetoCadastro,
        campos: dict[str, CampoCadastro],
    ) -> int:
        proposicao_id = self._resolver_tipo_chave(
            "proposicao",
            campos.get("proposicao"),
        )
        alvo_tipo = self._texto(campos, "alvo_tipo")
        alvo_id = self._resolver_tipo_chave(
            alvo_tipo,
            campos.get("alvo_chave"),
        )
        ordem = int(self._numero(campos, "ordem", 1))
        existente = self.conn.execute(
            "SELECT id FROM proposicao_argumentos "
            "WHERE proposicao_id = ? AND ordem = ?",
            (proposicao_id, ordem),
        ).fetchone()
        if existente is not None:
            self.reutilizados.append(f"argumento:{objeto.chave}")
            return int(existente["id"])
        return int(
            self.conn.execute(
                "INSERT INTO proposicao_argumentos "
                "(proposicao_id, ordem, papel, alvo_tipo, alvo_id, "
                "funcao_sintatica, confianca) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    proposicao_id,
                    ordem,
                    self._texto(campos, "papel"),
                    alvo_tipo,
                    alvo_id,
                    self._valor(campos, "funcao_sintatica"),
                    self._confianca(campos),
                ),
            ).lastrowid
        )

    def _relacao(
        self,
        objeto: ObjetoCadastro,
        campos: dict[str, CampoCadastro],
    ) -> int:
        origem_tipo = self._texto(campos, "origem_tipo")
        destino_tipo = self._texto(campos, "destino_tipo")
        origem_id = self._resolver_tipo_chave(
            origem_tipo,
            campos.get("origem_chave"),
        )
        destino_id = self._resolver_tipo_chave(
            destino_tipo,
            campos.get("destino_chave"),
        )
        return self._inserir_relacao(
            objeto.chave,
            origem_tipo,
            origem_id,
            destino_tipo,
            destino_id,
            self._valor(campos, "tipo_relacao"),
            self._valor(campos, "direcao") or "direta",
            self._valor(campos, "contexto"),
            self._confianca(campos),
        )

    def _aplicar_relacoes_embutidas(self) -> None:
        for objeto in self.contrato.objetos:
            origem_tipo = objeto.tipo
            if not objeto.relacoes:
                continue
            origem_id = self.ids_por_objeto[objeto.objeto_id]
            for relacao in objeto.relacoes:
                if relacao.origem_objeto_id != objeto.objeto_id:
                    raise ValueError(
                        "relação embutida precisa estar no objeto de origem"
                    )
                if relacao.tipo == "componente_de_expressao":
                    if origem_tipo != "expressao":
                        raise ValueError(
                            "componente_de_expressao precisa ter origem expressao"
                        )
                    if relacao.destino_tipo != "lexema":
                        raise ValueError(
                            "componente_de_expressao precisa ter destino lexema"
                        )
                    lexema_id = self._resolver_tipo_chave(
                        "lexema",
                        relacao.destino_chave,
                    )
                    existente = self.conn.execute(
                        "SELECT lexema_id FROM expressao_componentes "
                        "WHERE expressao_id = ? AND ordem = ?",
                        (origem_id, relacao.ordem),
                    ).fetchone()
                    if existente is not None:
                        if int(existente["lexema_id"]) != int(lexema_id):
                            raise ValueError(
                                "componente de expressão conflita com a ordem existente"
                            )
                        self.reutilizados.append(
                            f"expressao_componente:{objeto.objeto_id}:{relacao.ordem}"
                        )
                    else:
                        self.conn.execute(
                            "INSERT INTO expressao_componentes "
                            "(expressao_id, ordem, tipo_componente, lexema_id, "
                            "opcional, restricao) "
                            "VALUES (?, ?, 'lexema', ?, 0, NULL)",
                            (origem_id, relacao.ordem, lexema_id),
                        )
                    continue
                if relacao.tipo == "sentido_conceito":
                    if origem_tipo != "sentido":
                        raise ValueError(
                            "sentido_conceito precisa ter origem sentido"
                        )
                    if relacao.destino_tipo != "conceito":
                        raise ValueError(
                            "sentido_conceito precisa ter destino conceito"
                        )
                    if relacao.tipo_ligacao is None:
                        raise ValueError(
                            "sentido_conceito precisa informar tipo_ligacao"
                        )
                    if relacao.evidencia_ids:
                        raise ValueError(
                            "o modelo atual de evidências não suporta "
                            "alvo sentidos_conceitos"
                        )
                    conceito_id = self._resolver_tipo_chave(
                        "conceito",
                        relacao.destino_chave,
                    )
                    existente = self.conn.execute(
                        "SELECT tipo_ligacao, confianca, estado "
                        "FROM sentidos_conceitos "
                        "WHERE sentido_id = ? AND conceito_id = ?",
                        (origem_id, conceito_id),
                    ).fetchone()
                    if existente is not None:
                        if (
                            existente["tipo_ligacao"] != relacao.tipo_ligacao
                            or float(existente["confianca"])
                            != float(relacao.confianca)
                        ):
                            raise ValueError(
                                "sentido_conceito existente possui atributos "
                                "incompatíveis"
                            )
                        self.reutilizados.append(
                            f"sentido_conceito:{objeto.objeto_id}:{relacao.ordem}"
                        )
                    else:
                        self.conn.execute(
                            """
                            INSERT INTO sentidos_conceitos (
                                sentido_id, conceito_id, tipo_ligacao,
                                confianca, estado
                            ) VALUES (?, ?, ?, ?, 'aprovado')
                            """,
                            (
                                origem_id,
                                conceito_id,
                                relacao.tipo_ligacao,
                                relacao.confianca,
                            ),
                        )
                    continue
                if origem_tipo not in _TIPOS_SEMANTICOS:
                    raise ValueError(
                        "relação física exige origem semântica resolvível"
                    )
                destino_id = self._resolver_tipo_chave(
                    relacao.destino_tipo,
                    relacao.destino_chave,
                )
                relacao_id = self._inserir_relacao(
                    relacao.tipo,
                    origem_tipo,
                    origem_id,
                    relacao.destino_tipo,
                    destino_id,
                    relacao.tipo,
                    "direta",
                    None,
                    relacao.confianca,
                )
                for evidencia_id in relacao.evidencia_ids:
                    self._registrar_alvo_evidencia(
                        evidencia_id,
                        "relacao_semantica",
                        relacao_id,
                        f"relacao:{objeto.objeto_id}:{relacao.ordem}",
                    )

    def _inserir_relacao(
        self,
        chave: str,
        origem_tipo: str,
        origem_id: int,
        destino_tipo: str,
        destino_id: int,
        tipo_relacao: Any,
        direcao: Any,
        contexto: Any,
        confianca: float,
    ) -> int:
        if tipo_relacao == "relacionado_no_tema":
            if (
                origem_tipo not in _TIPOS_RELACAO_TEMATICA
                or destino_tipo not in _TIPOS_RELACAO_TEMATICA
            ):
                raise ValueError(
                    "relacionado_no_tema aceita somente expressao como endpoint"
                )
            if direcao != "simetrica":
                raise ValueError(
                    "relacionado_no_tema precisa ter direção simetrica"
                )
        elif (
            origem_tipo not in _TIPOS_SEMANTICOS
            or destino_tipo not in _TIPOS_SEMANTICOS
        ):
            raise ValueError("relação física aceita somente tipos semânticos")

        if direcao == "simetrica":
            existente = self.conn.execute(
                "SELECT id FROM relacoes_semanticas "
                "WHERE tipo_relacao = ? AND direcao = ? AND ("
                "(origem_tipo = ? AND origem_id = ? AND destino_tipo = ? "
                "AND destino_id = ?) OR "
                "(origem_tipo = ? AND origem_id = ? AND destino_tipo = ? "
                "AND destino_id = ?))",
                (
                    tipo_relacao,
                    direcao,
                    origem_tipo,
                    origem_id,
                    destino_tipo,
                    destino_id,
                    destino_tipo,
                    destino_id,
                    origem_tipo,
                    origem_id,
                ),
            ).fetchone()
        else:
            existente = self.conn.execute(
                "SELECT id FROM relacoes_semanticas "
                "WHERE tipo_relacao = ? AND origem_tipo = ? AND origem_id = ? "
                "AND destino_tipo = ? AND destino_id = ? AND direcao = ?",
                (
                    tipo_relacao,
                    origem_tipo,
                    origem_id,
                    destino_tipo,
                    destino_id,
                    direcao,
                ),
            ).fetchone()
        if existente is not None:
            self.reutilizados.append(f"relacao_semantica:{chave}")
            return int(existente["id"])
        return int(
            self.conn.execute(
                "INSERT INTO relacoes_semanticas "
                "(tipo_relacao, origem_tipo, origem_id, destino_tipo, "
                "destino_id, direcao, estado, contexto, confianca) "
                "VALUES (?, ?, ?, ?, ?, ?, 'aprovado', ?, ?)",
                (
                    tipo_relacao,
                    origem_tipo,
                    origem_id,
                    destino_tipo,
                    destino_id,
                    direcao,
                    contexto,
                    confianca,
                ),
            ).lastrowid
        )

    def _aplicar_evidencias(self) -> None:
        por_id = {e.evidencia_id: e for e in self.contrato.evidencias}
        for evidencia_id, tipo, alvo_id, alvo_chave in sorted(self.alvos_evidencia):
            if tipo not in _TIPOS_EVIDENCIA:
                raise ValueError(
                    f"evidência não pode apontar para o tipo {tipo}"
                )
            evidencia = por_id[evidencia_id]
            existente = self.conn.execute(
                "SELECT id FROM evidencias WHERE fonte_id = ? "
                "AND alvo_tipo = ? AND alvo_id = ? AND trecho = ?",
                (
                    self.fontes[evidencia_id],
                    tipo,
                    alvo_id,
                    evidencia.trecho,
                ),
            ).fetchone()
            if existente is not None:
                self.reutilizados.append(f"evidencia:{evidencia_id}:{alvo_chave}")
                continue
            evidencia_db_id = self.conn.execute(
                "INSERT INTO evidencias "
                "(fonte_id, alvo_tipo, alvo_id, trecho, referencia, "
                "data_evidencia, estado, confianca, revisao_necessaria) "
                "VALUES (?, ?, ?, ?, ?, ?, 'aprovado', ?, 0)",
                (
                    self.fontes[evidencia_id],
                    tipo,
                    alvo_id,
                    evidencia.trecho,
                    evidencia.referencia,
                    None,
                    evidencia.confianca,
                ),
            ).lastrowid
            self.evidencias_criadas.append(int(evidencia_db_id))

    def _registrar_alvo_evidencia(
        self,
        evidencia_id: str,
        tipo: str,
        alvo_id: int,
        chave: str,
    ) -> None:
        if evidencia_id not in self.fontes:
            raise ValueError(f"evidência não preparada: {evidencia_id}")
        self.alvos_evidencia.add((evidencia_id, tipo, alvo_id, chave))

    def _resolver_lexema(self, campo: Optional[CampoCadastro]) -> int:
        return self._resolver_tipo_chave("lexema", campo)

    def _resolver_tipo_chave(
        self,
        tipo: str,
        campo: Optional[CampoCadastro | str | int],
        permitir_nulo: bool = False,
    ) -> Optional[int]:
        if campo is None:
            if permitir_nulo:
                return None
            raise ValueError(f"referência obrigatória ausente: {tipo}")
        chave = str(campo.valor if isinstance(campo, CampoCadastro) else campo)
        for objeto_id, objeto in self.objetos_por_id.items():
            if objeto.tipo == tipo and (
                objeto_id == chave or objeto.chave == chave
            ):
                return self.ids_por_objeto[objeto_id]
        if tipo == "lexema":
            linha = self.conn.execute(
                "SELECT id FROM lexemas WHERE lema = ?", (chave,)
            ).fetchone()
        elif tipo == "conceito":
            linha = self.conn.execute(
                "SELECT id FROM conceitos WHERE chave = ?", (chave,)
            ).fetchone()
        elif tipo == "forma_lexical":
            linha = self.conn.execute(
                "SELECT id FROM formas_lexicais WHERE normalizada = ?",
                (chave,),
            ).fetchone()
        elif tipo == "expressao":
            linha = self.conn.execute(
                "SELECT id FROM expressoes WHERE normalizada = ?",
                (chave,),
            ).fetchone()
        elif tipo in {"sentido", "proposicao", "fato"}:
            # Esses tipos não possuem uma chave lógica externa no schema atual.
            # Nunca interpretar um inteiro legado como ID canônico.
            linha = None
        else:
            linha = None
        if linha is None:
            raise ValueError(f"referência não resolvida: {tipo}:{chave}")
        return int(linha["id"])

    @staticmethod
    def _tabela_tipo(tipo: str) -> str:
        return {
            "sentido": "sentidos",
            "proposicao": "proposicoes",
            "fato": "fatos",
        }[tipo]

    def _resolver_fonte(self, campo: Optional[CampoCadastro]) -> int:
        if campo is None:
            raise ValueError("fonte obrigatória e explícita não resolvida")
        valor = str(campo.valor)
        for evidencia_id, fonte_id in self.fontes.items():
            evidencia = next(
                evidencia
                for evidencia in self.contrato.evidencias
                if evidencia.evidencia_id == evidencia_id
            )
            if valor in {evidencia_id, evidencia.fonte_identificador}:
                return fonte_id
        linha = self.conn.execute(
            "SELECT id FROM fontes WHERE identificador = ? ORDER BY id LIMIT 1",
            (valor,),
        ).fetchone()
        if linha is not None:
            return int(linha["id"])
        raise ValueError(f"fonte explícita não resolvida: {valor}")

    @staticmethod
    def _valor(
        campos: dict[str, CampoCadastro],
        nome: str,
        padrao: Any = None,
    ) -> Any:
        campo = campos.get(nome)
        return padrao if campo is None else campo.valor

    @classmethod
    def _texto(
        cls,
        campos: dict[str, CampoCadastro],
        nome: str,
        padrao: Optional[str] = None,
    ) -> str:
        valor = cls._valor(campos, nome, padrao)
        if not isinstance(valor, str) or not valor.strip():
            raise ValueError(f"campo obrigatório não resolvido: {nome}")
        return valor.strip()

    @classmethod
    def _numero(
        cls,
        campos: dict[str, CampoCadastro],
        nome: str,
        padrao: float,
    ) -> float:
        valor = cls._valor(campos, nome, padrao)
        if not isinstance(valor, (int, float)) or isinstance(valor, bool):
            raise ValueError(f"campo numérico inválido: {nome}")
        return float(valor)

    @classmethod
    def _confianca(cls, campos: dict[str, CampoCadastro]) -> float:
        valores = [
            campo.confianca
            for campo in campos.values()
            if campo.nome not in {"ordem"}
        ]
        return min(valores) if valores else 0.5