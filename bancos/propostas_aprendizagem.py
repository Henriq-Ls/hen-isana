"""Propostas explícitas de aprendizagem de conteúdo, com auditoria e reversão."""

from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3
from typing import Optional

from bancos.conhecimento import ConhecimentoDB
from protocolo.regras import ALVO_CONHECIMENTO, TipoAcao
from protocolo.verificador import validar_permissao


_CAMPOS_TERMO_ORDENADOS = tuple(
    dict.fromkeys((*ConhecimentoDB.CAMPOS_CONHECIMENTO, "relacionados"))
)
_CAMPOS_TERMO = frozenset(_CAMPOS_TERMO_ORDENADOS)


@dataclass(frozen=True)
class PropostaAprendizagem:
    id: int
    entidade: str
    acao: str
    entidade_id: Optional[int]
    conteudo: dict
    antes: Optional[dict]
    depois: Optional[dict]
    estado: str
    motivo: str
    origem: str
    resultado: Optional[str]
    criado_em: str
    atualizado_em: str


class PropostasAprendizagem:
    """Registra mudanças de conteúdo sem capturar a conversa automaticamente.

    As propostas e o conhecimento canônico compartilham a conexão SQLite,
    permitindo aplicar ou reverter uma mudança e registrar seu resultado na
    mesma transação. Este serviço aceita apenas termos e fatos; não escreve
    arquivos nem oferece operações de alteração de código.
    """

    def __init__(self, banco: ConhecimentoDB):
        self.banco = banco
        self.conn = banco.conn
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS propostas_aprendizagem (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entidade TEXT NOT NULL
                    CHECK (entidade IN ('termo', 'fato')),
                acao TEXT NOT NULL
                    CHECK (acao IN ('inclusao', 'correcao')),
                entidade_id INTEGER,
                conteudo_json TEXT NOT NULL,
                antes_json TEXT,
                depois_json TEXT,
                estado TEXT NOT NULL
                    CHECK (estado IN (
                        'proposta', 'aprovada', 'recusada',
                        'aplicada', 'revertida'
                    )),
                motivo TEXT NOT NULL,
                origem TEXT NOT NULL,
                resultado TEXT,
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE INDEX IF NOT EXISTS idx_propostas_aprendizagem_estado
                ON propostas_aprendizagem(estado, id);
            """
        )
        self.conn.commit()

    @staticmethod
    def _json(dados: Optional[dict]) -> Optional[str]:
        if dados is None:
            return None
        return json.dumps(
            dados,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )

    @staticmethod
    def _proposta(linha: sqlite3.Row) -> PropostaAprendizagem:
        return PropostaAprendizagem(
            id=int(linha["id"]),
            entidade=str(linha["entidade"]),
            acao=str(linha["acao"]),
            entidade_id=(
                int(linha["entidade_id"])
                if linha["entidade_id"] is not None
                else None
            ),
            conteudo=json.loads(linha["conteudo_json"]),
            antes=(
                json.loads(linha["antes_json"])
                if linha["antes_json"] is not None
                else None
            ),
            depois=(
                json.loads(linha["depois_json"])
                if linha["depois_json"] is not None
                else None
            ),
            estado=str(linha["estado"]),
            motivo=str(linha["motivo"]),
            origem=str(linha["origem"]),
            resultado=linha["resultado"],
            criado_em=str(linha["criado_em"]),
            atualizado_em=str(linha["atualizado_em"]),
        )

    @staticmethod
    def _texto_obrigatorio(valor: str, nome: str) -> str:
        if not isinstance(valor, str):
            raise TypeError(f"{nome} deve ser texto")
        limpo = " ".join(valor.strip().split())
        if not limpo:
            raise ValueError(f"{nome} não pode ficar vazio")
        return limpo

    @staticmethod
    def _snapshot_termo(linha: sqlite3.Row) -> dict:
        return {
            "id": int(linha["id"]),
            "termo": str(
                linha["termo_original"]
                if linha["termo_original"] is not None
                else linha["termo"]
            ),
            **{
                campo: linha[campo]
                for campo in _CAMPOS_TERMO_ORDENADOS
            },
        }

    @staticmethod
    def _snapshot_fato(linha: sqlite3.Row) -> dict:
        return {
            "id": int(linha["id"]),
            "afirmacao": str(linha["afirmacao"]),
            "contexto": str(linha["contexto"]),
            "origem": str(linha["origem"]),
            "estado": str(linha["estado"]),
        }

    def _salvar_proposta(
        self,
        *,
        entidade: str,
        acao: str,
        entidade_id: Optional[int],
        conteudo: dict,
        antes: Optional[dict],
        motivo: str,
        origem: str,
    ) -> PropostaAprendizagem:
        if entidade not in {"termo", "fato"}:
            raise ValueError(
                "propostas só podem alterar conteúdo (termo ou fato); "
                "alteração de código não é suportada"
            )
        motivo_limpo = self._texto_obrigatorio(motivo, "motivo")
        origem_limpa = self._texto_obrigatorio(origem, "origem")
        cursor = self.conn.execute(
            """
            INSERT INTO propostas_aprendizagem (
                entidade, acao, entidade_id, conteudo_json, antes_json,
                estado, motivo, origem
            )
            VALUES (?, ?, ?, ?, ?, 'proposta', ?, ?)
            """,
            (
                entidade,
                acao,
                entidade_id,
                self._json(conteudo),
                self._json(antes),
                motivo_limpo,
                origem_limpa,
            ),
        )
        self.conn.commit()
        return self.obter(int(cursor.lastrowid))

    def propor_termo(
        self,
        termo: str,
        campos: dict[str, str],
        *,
        motivo: str,
        origem: str,
        contexto_alvo: Optional[str] = None,
    ) -> PropostaAprendizagem:
        """Propõe inclusão/correção de campos sem alterar o conhecimento."""
        termo_original = self.banco._normalizar_termo_original(termo)
        if not self.banco._normalizar_termo(termo_original):
            raise ValueError("termo não pode ficar vazio")
        if not isinstance(campos, dict) or not campos:
            raise ValueError("informe pelo menos um campo de conteúdo")
        desconhecidos = set(campos) - _CAMPOS_TERMO
        if desconhecidos:
            raise ValueError(
                "campos não permitidos: " + ", ".join(sorted(desconhecidos))
            )

        valores = {}
        for campo, valor in campos.items():
            normalizado = self.banco._opcional(valor)
            if normalizado is None:
                raise ValueError(f"o campo {campo} não pode ficar vazio")
            valores[campo] = normalizado

        entradas = self.banco.buscar_termo(termo_original)
        contexto_alvo_limpo = (
            self.banco._opcional(contexto_alvo)
            if contexto_alvo is not None
            else None
        )
        if contexto_alvo is None and len(entradas) > 1:
            raise ValueError(
                "o termo tem sentidos concorrentes; informe contexto_alvo"
            )
        correspondentes = [
            entrada
            for entrada in entradas
            if contexto_alvo is None
            or (entrada.contexto_uso or "").casefold()
            == (contexto_alvo_limpo or "").casefold()
        ]
        if len(correspondentes) > 1:
            raise ValueError("a proposta identifica mais de um sentido")

        antes = None
        entidade_id = None
        if correspondentes:
            entrada = correspondentes[0]
            linha = self.conn.execute(
                "SELECT * FROM conhecimento WHERE id = ?",
                (entrada.id,),
            ).fetchone()
            assert linha is not None
            antes = self._snapshot_termo(linha)
            entidade_id = entrada.id
            if all(antes[campo] == valor for campo, valor in valores.items()):
                raise ValueError("a proposta não altera nenhum campo")

        conteudo = {"termo": termo_original, "campos": valores}
        return self._salvar_proposta(
            entidade="termo",
            acao="correcao" if entidade_id is not None else "inclusao",
            entidade_id=entidade_id,
            conteudo=conteudo,
            antes=antes,
            motivo=motivo,
            origem=origem,
        )

    def propor_codigo(self, *_args: object, **_kwargs: object) -> None:
        """Recusa alterações de código; esta etapa só aprende conteúdo."""
        raise PermissionError(
            "propostas de alteração de código não são aceitas neste fluxo; "
            "nenhum arquivo foi alterado"
        )

    def propor_fato(
        self,
        afirmacao: str,
        contexto: str,
        *,
        motivo: str,
        origem: str,
        fato_id: Optional[int] = None,
    ) -> PropostaAprendizagem:
        """Propõe um fato contextual novo ou uma correção de fato existente."""
        afirmacao_limpa = self.banco._opcional(afirmacao)
        contexto_limpo = self.banco._opcional(contexto)
        if afirmacao_limpa is None:
            raise ValueError("a afirmação não pode ficar vazia")
        if contexto_limpo is None:
            raise ValueError("o contexto não pode ficar vazio")

        antes = None
        entidade_id = None
        if fato_id is not None:
            linha = self.conn.execute(
                "SELECT * FROM fatos_conhecimento WHERE id = ?",
                (fato_id,),
            ).fetchone()
            if linha is None:
                raise LookupError(f"fato {fato_id} não encontrado")
            antes = self._snapshot_fato(linha)
            if antes["contexto"].casefold() != contexto_limpo.casefold():
                raise ValueError("o contexto não corresponde ao fato indicado")
            if antes["estado"].casefold() == "revertida":
                raise ValueError("não é possível corrigir um fato já revertido")
            entidade_id = fato_id
            if antes["afirmacao"] == afirmacao_limpa:
                raise ValueError("a proposta não altera a afirmação")
        elif self.banco.buscar_fato(afirmacao_limpa, contexto_limpo):
            raise ValueError("o fato já existe nesse contexto")

        return self._salvar_proposta(
            entidade="fato",
            acao="correcao" if entidade_id is not None else "inclusao",
            entidade_id=entidade_id,
            conteudo={
                "afirmacao": afirmacao_limpa,
                "contexto": contexto_limpo,
            },
            antes=antes,
            motivo=motivo,
            origem=origem,
        )

    def obter(self, proposta_id: int) -> PropostaAprendizagem:
        linha = self.conn.execute(
            "SELECT * FROM propostas_aprendizagem WHERE id = ?",
            (proposta_id,),
        ).fetchone()
        if linha is None:
            raise LookupError(f"proposta {proposta_id} não encontrada")
        return self._proposta(linha)

    def listar(self, limite: int = 100) -> list[PropostaAprendizagem]:
        if not isinstance(limite, int) or isinstance(limite, bool) or limite < 1:
            raise ValueError("limite deve ser um inteiro positivo")
        linhas = self.conn.execute(
            """
            SELECT *
            FROM propostas_aprendizagem
            ORDER BY id DESC
            LIMIT ?
            """,
            (limite,),
        ).fetchall()
        return [self._proposta(linha) for linha in linhas]

    def _mudar_estado(
        self,
        proposta_id: int,
        *,
        estados_permitidos: set[str],
        novo_estado: str,
        resultado: str,
    ) -> PropostaAprendizagem:
        resultado_limpo = self._texto_obrigatorio(resultado, "resultado")
        if self.conn.in_transaction:
            raise RuntimeError("há outra transação ativa no banco de conhecimento")
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            proposta = self.obter(proposta_id)
            if proposta.estado not in estados_permitidos:
                raise ValueError(
                    f"não é possível mudar uma proposta de "
                    f"'{proposta.estado}' para '{novo_estado}'"
                )
            self.conn.execute(
                """
                UPDATE propostas_aprendizagem
                SET estado = ?, resultado = ?,
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (novo_estado, resultado_limpo, proposta_id),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return self.obter(proposta_id)

    def aprovar(
        self,
        proposta_id: int,
        resultado: str = "aprovada explicitamente; aguarda aplicação",
    ) -> PropostaAprendizagem:
        return self._mudar_estado(
            proposta_id,
            estados_permitidos={"proposta"},
            novo_estado="aprovada",
            resultado=resultado,
        )

    def recusar(
        self,
        proposta_id: int,
        resultado: str,
    ) -> PropostaAprendizagem:
        return self._mudar_estado(
            proposta_id,
            estados_permitidos={"proposta", "aprovada"},
            novo_estado="recusada",
            resultado=resultado,
        )

    def _validar_permissao_escrita(self, permissao: object) -> None:
        autorizacao = validar_permissao(
            permissao,
            TipoAcao.SALVAR_CONHECIMENTO,
            ALVO_CONHECIMENTO,
        )
        if not autorizacao.permitida:
            raise PermissionError(autorizacao.mensagem)

    def aplicar(
        self,
        proposta_id: int,
        *,
        permissao: object,
    ) -> PropostaAprendizagem:
        """Aplica conteúdo somente após aprovação e permissão de escrita."""
        self._validar_permissao_escrita(permissao)
        if self.conn.in_transaction:
            raise RuntimeError("há outra transação ativa no banco de conhecimento")

        self.conn.execute("BEGIN IMMEDIATE")
        try:
            proposta = self.obter(proposta_id)
            if proposta.estado != "aprovada":
                raise ValueError("a proposta precisa ser aprovada antes da aplicação")

            if proposta.entidade == "termo":
                entidade_id, depois = self._aplicar_termo(proposta)
            elif proposta.entidade == "fato":
                entidade_id, depois = self._aplicar_fato(proposta)
            else:
                raise ValueError("tipo de proposta não suportado")

            self.conn.execute(
                """
                UPDATE propostas_aprendizagem
                SET entidade_id = ?, depois_json = ?, estado = 'aplicada',
                    resultado = 'conteúdo aplicado explicitamente',
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (entidade_id, self._json(depois), proposta_id),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return self.obter(proposta_id)

    def _aplicar_termo(
        self,
        proposta: PropostaAprendizagem,
    ) -> tuple[int, dict]:
        termo = self.banco._normalizar_termo_original(
            proposta.conteudo["termo"]
        )
        termo_chave = self.banco._normalizar_termo(termo)
        campos = proposta.conteudo["campos"]
        atual = None
        if proposta.entidade_id is not None:
            linha = self.conn.execute(
                "SELECT * FROM conhecimento WHERE id = ?",
                (proposta.entidade_id,),
            ).fetchone()
            if linha is None:
                raise ValueError("o termo-alvo foi removido após a proposta")
            atual = self._snapshot_termo(linha)
            if atual != proposta.antes:
                raise ValueError(
                    "o termo mudou desde a proposta; crie uma nova proposta"
                )

        valores = {
            campo: (atual[campo] if atual else None)
            for campo in _CAMPOS_TERMO_ORDENADOS
        }
        valores.update(campos)
        contexto = valores["contexto_uso"]
        duplicado = self.conn.execute(
            """
            SELECT id
            FROM conhecimento
            WHERE termo_chave = ?
              AND contexto_uso IS ?
              AND (? IS NULL OR id <> ?)
            LIMIT 1
            """,
            (
                termo_chave,
                contexto,
                proposta.entidade_id,
                proposta.entidade_id,
            ),
        ).fetchone()
        if duplicado is not None:
            raise ValueError("a proposta duplicaria um sentido existente")

        if proposta.entidade_id is None:
            cursor = self.conn.execute(
                """
                INSERT INTO conhecimento (
                    termo, termo_original, termo_chave, tipo, significado,
                    contexto_uso, resposta_padrao, relacionados, exemplo_uso
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    termo,
                    termo,
                    termo_chave,
                    valores["tipo"],
                    valores["significado"],
                    valores["contexto_uso"],
                    valores["resposta_padrao"],
                    valores["relacionados"],
                    valores["exemplo_uso"],
                ),
            )
            entidade_id = int(cursor.lastrowid)
        else:
            entidade_id = proposta.entidade_id
            self.conn.execute(
                """
                UPDATE conhecimento
                SET tipo = ?, significado = ?, contexto_uso = ?,
                    resposta_padrao = ?, relacionados = ?, exemplo_uso = ?
                WHERE id = ?
                """,
                (
                    valores["tipo"],
                    valores["significado"],
                    valores["contexto_uso"],
                    valores["resposta_padrao"],
                    valores["relacionados"],
                    valores["exemplo_uso"],
                    entidade_id,
                ),
            )

        origem_evidencia = f"proposta:{proposta.id}:{proposta.origem}"
        for campo, valor in campos.items():
            if atual is not None and atual[campo] == valor:
                continue
            self.conn.execute(
                """
                INSERT OR IGNORE INTO evidencias_conhecimento (
                    conhecimento_id, campo, valor, origem, estado
                )
                VALUES (?, ?, ?, ?, 'confirmada')
                """,
                (entidade_id, campo, valor, origem_evidencia),
            )
        linha_depois = self.conn.execute(
            "SELECT * FROM conhecimento WHERE id = ?",
            (entidade_id,),
        ).fetchone()
        assert linha_depois is not None
        return entidade_id, self._snapshot_termo(linha_depois)

    def _aplicar_fato(
        self,
        proposta: PropostaAprendizagem,
    ) -> tuple[int, dict]:
        afirmacao = proposta.conteudo["afirmacao"]
        contexto = proposta.conteudo["contexto"]
        atual = None
        if proposta.entidade_id is not None:
            linha = self.conn.execute(
                "SELECT * FROM fatos_conhecimento WHERE id = ?",
                (proposta.entidade_id,),
            ).fetchone()
            if linha is None:
                raise ValueError("o fato-alvo foi removido após a proposta")
            atual = self._snapshot_fato(linha)
            if atual != proposta.antes:
                raise ValueError(
                    "o fato mudou desde a proposta; crie uma nova proposta"
                )

        duplicado = self.conn.execute(
            """
            SELECT id
            FROM fatos_conhecimento
            WHERE afirmacao = ? COLLATE NOCASE
              AND contexto = ? COLLATE NOCASE
              AND estado <> 'revertida'
              AND (? IS NULL OR id <> ?)
            LIMIT 1
            """,
            (
                afirmacao,
                contexto,
                proposta.entidade_id,
                proposta.entidade_id,
            ),
        ).fetchone()
        if duplicado is not None:
            raise ValueError("a proposta duplicaria um fato existente")

        origem_registro = f"proposta:{proposta.id}:{proposta.origem}"
        if proposta.entidade_id is None:
            cursor = self.conn.execute(
                """
                INSERT INTO fatos_conhecimento (
                    afirmacao, contexto, origem, estado
                )
                VALUES (?, ?, ?, 'confirmada')
                """,
                (afirmacao, contexto, origem_registro),
            )
            entidade_id = int(cursor.lastrowid)
        else:
            entidade_id = proposta.entidade_id
            self.conn.execute(
                """
                UPDATE fatos_conhecimento
                SET afirmacao = ?, contexto = ?, origem = ?, estado = 'confirmada',
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (afirmacao, contexto, origem_registro, entidade_id),
            )

        self.conn.execute(
            """
            INSERT OR IGNORE INTO evidencias_fatos (
                fato_id, afirmacao, contexto, origem, estado
            )
            VALUES (?, ?, ?, ?, 'confirmada')
            """,
            (entidade_id, afirmacao, contexto, origem_registro),
        )
        linha_depois = self.conn.execute(
            "SELECT * FROM fatos_conhecimento WHERE id = ?",
            (entidade_id,),
        ).fetchone()
        assert linha_depois is not None
        return entidade_id, self._snapshot_fato(linha_depois)

    def reverter(
        self,
        proposta_id: int,
        *,
        permissao: object,
    ) -> PropostaAprendizagem:
        """Restaura o estado anterior sem apagar o registro de auditoria."""
        self._validar_permissao_escrita(permissao)
        if self.conn.in_transaction:
            raise RuntimeError("há outra transação ativa no banco de conhecimento")

        self.conn.execute("BEGIN IMMEDIATE")
        try:
            proposta = self.obter(proposta_id)
            if proposta.estado != "aplicada" or proposta.depois is None:
                raise ValueError("somente uma proposta aplicada pode ser revertida")

            if proposta.entidade == "termo":
                self._reverter_termo(proposta)
            elif proposta.entidade == "fato":
                self._reverter_fato(proposta)
            else:
                raise ValueError("tipo de proposta não suportado")

            self.conn.execute(
                """
                UPDATE propostas_aprendizagem
                SET estado = 'revertida',
                    resultado = 'conteúdo revertido explicitamente',
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (proposta_id,),
            )
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise
        return self.obter(proposta_id)

    def _reverter_termo(self, proposta: PropostaAprendizagem) -> None:
        assert proposta.entidade_id is not None
        linha = self.conn.execute(
            "SELECT * FROM conhecimento WHERE id = ?",
            (proposta.entidade_id,),
        ).fetchone()
        if linha is None or self._snapshot_termo(linha) != proposta.depois:
            raise ValueError(
                "o termo mudou após a aplicação; a reversão automática foi "
                "bloqueada para não sobrescrever dados novos"
            )

        if proposta.antes is None:
            valores = {
                campo: None for campo in _CAMPOS_TERMO_ORDENADOS
            }
        else:
            valores = {
                campo: proposta.antes[campo]
                for campo in _CAMPOS_TERMO_ORDENADOS
            }
        self.conn.execute(
            """
            UPDATE conhecimento
            SET tipo = ?, significado = ?, contexto_uso = ?,
                resposta_padrao = ?, relacionados = ?, exemplo_uso = ?
            WHERE id = ?
            """,
            (
                valores["tipo"],
                valores["significado"],
                valores["contexto_uso"],
                valores["resposta_padrao"],
                valores["relacionados"],
                valores["exemplo_uso"],
                proposta.entidade_id,
            ),
        )
        prefixo_origem = f"proposta:{proposta.id}:{proposta.origem}"
        self.conn.execute(
            """
            UPDATE evidencias_conhecimento
            SET estado = 'revertida'
            WHERE conhecimento_id = ? AND origem = ?
              AND estado = 'confirmada'
            """,
            (proposta.entidade_id, prefixo_origem),
        )

    def _reverter_fato(self, proposta: PropostaAprendizagem) -> None:
        assert proposta.entidade_id is not None
        linha = self.conn.execute(
            "SELECT * FROM fatos_conhecimento WHERE id = ?",
            (proposta.entidade_id,),
        ).fetchone()
        if linha is None or self._snapshot_fato(linha) != proposta.depois:
            raise ValueError(
                "o fato mudou após a aplicação; a reversão automática foi "
                "bloqueada para não sobrescrever dados novos"
            )

        origem_evidencia = f"proposta:{proposta.id}:{proposta.origem}"
        if proposta.antes is None:
            self.conn.execute(
                """
                UPDATE fatos_conhecimento
                SET estado = 'revertida', atualizado_em = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (proposta.entidade_id,),
            )
            self.conn.execute(
                """
                UPDATE evidencias_fatos
                SET estado = 'revertida'
                WHERE fato_id = ? AND origem = ? AND estado = 'confirmada'
                """,
                (proposta.entidade_id, origem_evidencia),
            )
            return

        antes = proposta.antes
        self.conn.execute(
            """
            UPDATE fatos_conhecimento
            SET afirmacao = ?, contexto = ?, origem = ?, estado = ?,
                atualizado_em = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (
                antes["afirmacao"],
                antes["contexto"],
                antes["origem"],
                antes["estado"],
                proposta.entidade_id,
            ),
        )
        self.conn.execute(
            """
            UPDATE evidencias_fatos
            SET estado = 'revertida'
            WHERE fato_id = ? AND origem = ? AND estado = 'confirmada'
            """,
            (proposta.entidade_id, origem_evidencia),
        )
