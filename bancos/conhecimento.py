"""Banco principal de conhecimento aprendido."""

from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
import sqlite3
from typing import Iterable, Optional

from _LOGS_ import log as runtime_log
from core.normalizador import (
    normalizar_termo_chave,
    normalizar_termo_estrito,
)
from protocolo.regras import ALVO_CONHECIMENTO, TipoAcao
from protocolo.verificador import validar_permissao

DATA_DIR = Path(__file__).resolve().parents[1] / "aprendizado" / "bancos"
DEFAULT_DB = DATA_DIR / "conhecimento.db"


@dataclass(frozen=True)
class EntradaConhecimento:
    id: int
    termo: str
    tipo: Optional[str]
    significado: Optional[str]
    contexto_uso: Optional[str]
    resposta_padrao: Optional[str]
    relacionados: Optional[str]
    exemplo_uso: Optional[str] = None

    @property
    def completa(self) -> bool:
        """Um sentido está utilizável quando tem significado e ancoragem."""
        return bool(
            self.significado
            and (self.contexto_uso or self.exemplo_uso)
        )

    @property
    def termo_original(self) -> str:
        """Forma canônica de exibição, preservada no campo legado `termo`."""
        return self.termo


@dataclass(frozen=True)
class EvidenciaConhecimento:
    id: int
    conhecimento_id: int
    campo: str
    valor: str
    origem: str
    estado: str
    criado_em: str


@dataclass(frozen=True)
class FatoConhecimento:
    id: int
    afirmacao: str
    contexto: str
    origem: str
    estado: str
    criado_em: str
    atualizado_em: str


@dataclass(frozen=True)
class EvidenciaFato:
    id: int
    fato_id: int
    afirmacao: str
    contexto: str
    origem: str
    estado: str
    criado_em: str


class ConhecimentoDB:
    """Acesso a conceitos, fatos contextuais e suas evidências."""

    CAMPOS_APRENDIZAGEM = (
        "significado",
        "exemplo_uso",
    )
    CAMPOS_CONHECIMENTO = (
        "tipo",
        "significado",
        "contexto_uso",
        "resposta_padrao",
        "exemplo_uso",
    )

    def __init__(self, caminho_db: Optional[Path] = None):
        self.caminho_db = Path(caminho_db or DEFAULT_DB)
        self.caminho_db.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.caminho_db)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self._criar_tabelas()

    def _criar_tabelas(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS conhecimento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                termo TEXT NOT NULL,
                termo_original TEXT,
                termo_chave TEXT,
                tipo TEXT,
                significado TEXT,
                contexto_uso TEXT,
                resposta_padrao TEXT,
                relacionados TEXT,
                exemplo_uso TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_conhecimento_termo
                ON conhecimento(termo COLLATE NOCASE);

            CREATE INDEX IF NOT EXISTS idx_conhecimento_contexto
                ON conhecimento(termo COLLATE NOCASE, contexto_uso);
            """
        )
        versao = int(self.conn.execute("PRAGMA user_version").fetchone()[0])
        if versao < 1:
            colunas = {
                str(linha["name"])
                for linha in self.conn.execute(
                    "PRAGMA table_info(conhecimento)"
                ).fetchall()
            }
            if "exemplo_uso" not in colunas:
                self.conn.execute(
                    "ALTER TABLE conhecimento ADD COLUMN exemplo_uso TEXT"
                )
            self.conn.execute("PRAGMA user_version = 1")

        if versao < 2:
            self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS fatos_conhecimento (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    afirmacao TEXT NOT NULL,
                    contexto TEXT NOT NULL,
                    origem TEXT NOT NULL,
                    estado TEXT NOT NULL,
                    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );

                CREATE INDEX IF NOT EXISTS idx_fatos_contexto
                    ON fatos_conhecimento(contexto COLLATE NOCASE);

                CREATE TABLE IF NOT EXISTS evidencias_fatos (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    fato_id INTEGER NOT NULL,
                    afirmacao TEXT NOT NULL,
                    contexto TEXT NOT NULL,
                    origem TEXT NOT NULL,
                    estado TEXT NOT NULL,
                    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (fato_id)
                        REFERENCES fatos_conhecimento(id) ON DELETE CASCADE,
                    UNIQUE (fato_id, afirmacao, contexto, origem, estado)
                );

                CREATE INDEX IF NOT EXISTS idx_evidencias_fatos
                    ON evidencias_fatos(fato_id);

                PRAGMA user_version = 2;
                """
            )

        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS evidencias_conhecimento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                conhecimento_id INTEGER NOT NULL,
                campo TEXT NOT NULL,
                valor TEXT NOT NULL,
                origem TEXT NOT NULL,
                estado TEXT NOT NULL,
                criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (conhecimento_id)
                    REFERENCES conhecimento(id) ON DELETE CASCADE,
                UNIQUE (conhecimento_id, campo, valor, origem, estado)
            );

            CREATE INDEX IF NOT EXISTS idx_evidencias_conhecimento
                ON evidencias_conhecimento(conhecimento_id, campo);
            """
        )
        if versao < 3:
            self._migrar_termos_para_chave()
            self._registrar_evidencias_legadas()
        self.conn.commit()

    def _migrar_termos_para_chave(self) -> None:
        """Adiciona formas original/chave sem remover nem unir registros."""

        self.conn.execute("BEGIN IMMEDIATE")
        try:
            colunas = {
                str(linha["name"])
                for linha in self.conn.execute(
                    "PRAGMA table_info(conhecimento)"
                ).fetchall()
            }
            linhas = self.conn.execute(
                "SELECT * FROM conhecimento ORDER BY id"
            ).fetchall()
            formas_por_chave_contexto: dict[
                tuple[str, Optional[str]], set[str]
            ] = {}
            valores_migrados = []

            for linha in linhas:
                termo_existente = str(linha["termo"])
                termo_original = (
                    str(linha["termo_original"])
                    if "termo_original" in colunas
                    and linha["termo_original"] is not None
                    and str(linha["termo_original"]).strip()
                    else termo_existente
                )
                termo_chave = normalizar_termo_chave(termo_original)
                if not termo_chave:
                    raise ValueError(
                        "migração interrompida: há termo sem conteúdo "
                        "normalizável; nenhum registro foi unido ou removido"
                    )

                contexto = (
                    linha["contexto_uso"]
                    if "contexto_uso" in colunas
                    else None
                )
                chave_contexto = (termo_chave, contexto)
                formas_por_chave_contexto.setdefault(
                    chave_contexto,
                    set(),
                ).add(normalizar_termo_estrito(termo_original))
                valores_migrados.append(
                    (termo_original, termo_chave, int(linha["id"]))
                )

            colisoes = 0
            for (chave, _contexto), formas in formas_por_chave_contexto.items():
                if len(formas) <= 1:
                    continue
                if chave == "ola" and formas <= {"ola", "olá"}:
                    continue
                colisoes += 1
            if colisoes:
                raise ValueError(
                    "migração interrompida: "
                    f"{colisoes} colisão(ões) de chave em contexto igual; "
                    "os dados foram preservados e exigem revisão explícita"
                )

            if "termo_original" not in colunas:
                self.conn.execute(
                    "ALTER TABLE conhecimento ADD COLUMN termo_original TEXT"
                )
            if "termo_chave" not in colunas:
                self.conn.execute(
                    "ALTER TABLE conhecimento ADD COLUMN termo_chave TEXT"
                )
            self.conn.executemany(
                """
                UPDATE conhecimento
                SET termo_original = ?, termo_chave = ?
                WHERE id = ?
                """,
                valores_migrados,
            )
            self.conn.execute(
                """
                CREATE INDEX IF NOT EXISTS
                    idx_conhecimento_termo_chave_contexto
                ON conhecimento(termo_chave, contexto_uso)
                """
            )
            self.conn.execute("PRAGMA user_version = 3")
            self.conn.commit()
        except Exception:
            self.conn.rollback()
            raise

    def _registrar_evidencias_legadas(self) -> None:
        """Preserva campos legados somente durante uma migração explícita."""
        linhas = self.conn.execute(
            "SELECT * FROM conhecimento ORDER BY id"
        ).fetchall()
        for linha in linhas:
            conhecimento_id = int(linha["id"])
            for campo in self.CAMPOS_CONHECIMENTO:
                valor = linha[campo]
                if valor:
                    self.conn.execute(
                        """
                        INSERT OR IGNORE INTO evidencias_conhecimento (
                            conhecimento_id, campo, valor, origem, estado
                        )
                        VALUES (?, ?, ?, 'legado', 'historico')
                        """,
                        (conhecimento_id, campo, str(valor)),
                    )

    @staticmethod
    def _evidencia(linha: sqlite3.Row) -> EvidenciaConhecimento:
        return EvidenciaConhecimento(
            id=int(linha["id"]),
            conhecimento_id=int(linha["conhecimento_id"]),
            campo=str(linha["campo"]),
            valor=str(linha["valor"]),
            origem=str(linha["origem"]),
            estado=str(linha["estado"]),
            criado_em=str(linha["criado_em"]),
        )

    @staticmethod
    def _fato(linha: sqlite3.Row) -> FatoConhecimento:
        return FatoConhecimento(
            id=int(linha["id"]),
            afirmacao=str(linha["afirmacao"]),
            contexto=str(linha["contexto"]),
            origem=str(linha["origem"]),
            estado=str(linha["estado"]),
            criado_em=str(linha["criado_em"]),
            atualizado_em=str(linha["atualizado_em"]),
        )

    @staticmethod
    def _evidencia_fato(linha: sqlite3.Row) -> EvidenciaFato:
        return EvidenciaFato(
            id=int(linha["id"]),
            fato_id=int(linha["fato_id"]),
            afirmacao=str(linha["afirmacao"]),
            contexto=str(linha["contexto"]),
            origem=str(linha["origem"]),
            estado=str(linha["estado"]),
            criado_em=str(linha["criado_em"]),
        )

    @staticmethod
    def _normalizar_termo(termo: str) -> str:
        return normalizar_termo_chave(termo)

    @staticmethod
    def _normalizar_termo_original(termo: str) -> str:
        if not isinstance(termo, str):
            raise TypeError("termo deve ser uma string")
        return " ".join(termo.strip().split())

    @staticmethod
    def _opcional(valor: Optional[str]) -> Optional[str]:
        if valor is None:
            return None
        if not isinstance(valor, str):
            raise TypeError("campos de conhecimento devem ser strings ou None")
        valor_limpo = " ".join(valor.strip().split())
        return valor_limpo or None

    @staticmethod
    def _entrada(linha: sqlite3.Row) -> EntradaConhecimento:
        return EntradaConhecimento(
            id=int(linha["id"]),
            termo=str(
                linha["termo_original"]
                if linha["termo_original"] is not None
                else linha["termo"]
            ),
            tipo=linha["tipo"],
            significado=linha["significado"],
            contexto_uso=linha["contexto_uso"],
            resposta_padrao=linha["resposta_padrao"],
            relacionados=linha["relacionados"],
            exemplo_uso=linha["exemplo_uso"],
        )

    def buscar_termo(
        self,
        termo: str,
        contexto: Optional[str] = None,
    ) -> list[EntradaConhecimento]:
        termo_normalizado = self._normalizar_termo(termo)
        if contexto is None:
            cursor = self.conn.execute(
                """
                SELECT *
                FROM conhecimento
                WHERE termo_chave = ?
                ORDER BY id
                """,
                (termo_normalizado,),
            )
        else:
            cursor = self.conn.execute(
                """
                SELECT *
                FROM conhecimento
                WHERE termo_chave = ?
                  AND contexto_uso = ?
                ORDER BY id
                """,
                (termo_normalizado, self._opcional(contexto)),
            )
        entradas = [self._entrada(linha) for linha in cursor.fetchall()]
        runtime_log.acao(
            "bancos.conhecimento",
            "buscar_termo",
            "consulta de conhecimento",
            {
                "termo": termo_normalizado,
                "contexto": contexto,
                "resultados": len(entradas),
            },
        )
        return entradas

    def _somente_campos_confirmados(
        self,
        entradas: list[EntradaConhecimento],
    ) -> list[EntradaConhecimento]:
        """Oculta valores sem evidência confirmada para o valor atual."""
        if not entradas:
            return []

        ids = [entrada.id for entrada in entradas]
        marcadores = ",".join("?" for _ in ids)
        cursor = self.conn.execute(
            f"""
            SELECT conhecimento_id, campo, valor
            FROM evidencias_conhecimento
            WHERE estado = 'confirmada'
              AND conhecimento_id IN ({marcadores})
            """,
            ids,
        )
        confirmados: dict[int, set[tuple[str, str]]] = {}
        for linha in cursor.fetchall():
            confirmados.setdefault(int(linha["conhecimento_id"]), set()).add(
                (str(linha["campo"]), str(linha["valor"]))
            )

        campos = (
            "tipo",
            "significado",
            "contexto_uso",
            "resposta_padrao",
            "relacionados",
            "exemplo_uso",
        )
        resultado = []
        for entrada in entradas:
            valores = {}
            for campo in campos:
                valor = getattr(entrada, campo)
                valores[campo] = (
                    valor
                    if valor is not None
                    and (campo, valor) in confirmados.get(entrada.id, set())
                    else None
                )
            resultado.append(
                EntradaConhecimento(
                    id=entrada.id,
                    termo=entrada.termo,
                    tipo=valores["tipo"],
                    significado=valores["significado"],
                    contexto_uso=valores["contexto_uso"],
                    resposta_padrao=valores["resposta_padrao"],
                    relacionados=valores["relacionados"],
                    exemplo_uso=valores["exemplo_uso"],
                )
            )
        return resultado

    def buscar_termo_confirmado(
        self,
        termo: str,
        contexto: Optional[str] = None,
    ) -> list[EntradaConhecimento]:
        """Busca termos sem expor campos que ainda não foram confirmados."""
        entradas = self.buscar_termo(termo)
        if contexto is not None:
            contexto_normalizado = self._opcional(contexto)
            if contexto_normalizado is None:
                return []
            entradas = [
                entrada
                for entrada in entradas
                if (entrada.contexto_uso or "").casefold()
                == contexto_normalizado.casefold()
            ]
        return self._somente_campos_confirmados(entradas)

    def buscar_termo_por_id_confirmado(
        self,
        termo_id: int,
    ) -> Optional[EntradaConhecimento]:
        linha = self.conn.execute(
            "SELECT * FROM conhecimento WHERE id = ?",
            (termo_id,),
        ).fetchone()
        if linha is None:
            return None
        entradas = self._somente_campos_confirmados(
            [self._entrada(linha)]
        )
        return entradas[0]

    def listar_termos_confirmados(self) -> list[EntradaConhecimento]:
        cursor = self.conn.execute(
            "SELECT * FROM conhecimento ORDER BY id"
        )
        entradas = [
            self._entrada(linha)
            for linha in cursor.fetchall()
        ]
        return self._somente_campos_confirmados(entradas)

    def identificar_lacunas(
        self,
        termo: str,
        contexto: Optional[str] = None,
    ) -> list[str]:
        resultados = self.buscar_termo(termo, contexto)
        if not resultados:
            lacunas = ["significado", "exemplo_uso"]
            runtime_log.passo(
                "bancos.conhecimento",
                "identificar_lacunas",
                "termo sem registro; todos os campos faltam",
                {"termo": termo, "lacunas": lacunas},
            )
            return lacunas

        if contexto is None and len(resultados) > 1:
            lacunas = ["contexto_uso"]
            runtime_log.passo(
                "bancos.conhecimento",
                "identificar_lacunas",
                "mais de um sentido encontrado; contexto precisa ser esclarecido",
                {
                    "termo": termo,
                    "lacunas": lacunas,
                    "resultados": len(resultados),
                },
            )
            return lacunas

        entrada = resultados[0]

        valores = {
            "significado": entrada.significado,
            "exemplo_uso": entrada.exemplo_uso,
        }
        lacunas = [
            campo
            for campo, valor in valores.items()
            if not valor
            and not (
                campo == "exemplo_uso"
                and entrada.contexto_uso
            )
        ]
        runtime_log.passo(
            "bancos.conhecimento",
            "identificar_lacunas",
            "lacunas calculadas",
            {"termo": termo, "lacunas": lacunas},
        )
        return lacunas

    def salvar_termo(
        self,
        termo: str,
        tipo: Optional[str] = None,
        significado: Optional[str] = None,
        contexto_uso: Optional[str] = None,
        resposta_padrao: Optional[str] = None,
        relacionados: Optional[str] = None,
        exemplo_uso: Optional[str] = None,
        *,
        permissao: object | None = None,
        proveniencias: Optional[dict[str, tuple[str, str]]] = None,
    ) -> EntradaConhecimento:
        autorizacao = validar_permissao(
            permissao,
            TipoAcao.SALVAR_CONHECIMENTO,
            ALVO_CONHECIMENTO,
        )
        if not autorizacao.permitida:
            raise PermissionError(autorizacao.mensagem)

        termo_original = self._normalizar_termo_original(termo)
        termo_normalizado = self._normalizar_termo(termo_original)
        if not termo_normalizado:
            raise ValueError("termo precisa conter ao menos uma palavra")
        valores = {
            "tipo": self._opcional(tipo),
            "significado": self._opcional(significado),
            "contexto_uso": self._opcional(contexto_uso),
            "resposta_padrao": self._opcional(resposta_padrao),
            "relacionados": self._opcional(relacionados),
            "exemplo_uso": self._opcional(exemplo_uso),
        }
        valores_enviados = {
            "tipo": tipo,
            "significado": significado,
            "contexto_uso": contexto_uso,
            "resposta_padrao": resposta_padrao,
            "relacionados": relacionados,
            "exemplo_uso": exemplo_uso,
        }
        candidatos_existentes = self.conn.execute(
            """
            SELECT id, termo_original, termo
            FROM conhecimento
            WHERE termo_chave = ?
              AND contexto_uso IS ?
            ORDER BY id
            """,
            (termo_normalizado, valores["contexto_uso"]),
        ).fetchall()
        existente = None
        if len(candidatos_existentes) == 1:
            existente = candidatos_existentes[0]
        elif len(candidatos_existentes) > 1:
            forma_exata = normalizar_termo_estrito(termo_original)
            correspondencias_exatas = [
                candidato
                for candidato in candidatos_existentes
                if normalizar_termo_estrito(
                    str(
                        candidato["termo_original"]
                        if candidato["termo_original"] is not None
                        else candidato["termo"]
                    )
                )
                == forma_exata
            ]
            if len(correspondencias_exatas) == 1:
                existente = correspondencias_exatas[0]
            else:
                raise ValueError(
                    "a chave do termo corresponde a registros concorrentes; "
                    "informe um contexto ou resolva a colisão explicitamente"
                )

        if existente:
            self.conn.execute(
                """
                UPDATE conhecimento
                SET tipo = COALESCE(?, tipo),
                    significado = COALESCE(?, significado),
                    contexto_uso = COALESCE(?, contexto_uso),
                    resposta_padrao = COALESCE(?, resposta_padrao),
                    relacionados = COALESCE(?, relacionados),
                    exemplo_uso = COALESCE(?, exemplo_uso)
                WHERE id = ?
                """,
                (
                    valores["tipo"],
                    valores["significado"],
                    valores["contexto_uso"],
                    valores["resposta_padrao"],
                    valores["relacionados"],
                    valores["exemplo_uso"],
                    existente["id"],
                ),
            )
            entrada_id = int(existente["id"])
        else:
            cursor = self.conn.execute(
                """
                INSERT INTO conhecimento (
                    termo,
                    termo_original,
                    termo_chave,
                    tipo,
                    significado,
                    contexto_uso,
                    resposta_padrao,
                    relacionados,
                    exemplo_uso
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    termo_original,
                    termo_original,
                    termo_normalizado,
                    valores["tipo"],
                    valores["significado"],
                    valores["contexto_uso"],
                    valores["resposta_padrao"],
                    valores["relacionados"],
                    valores["exemplo_uso"],
                ),
            )
            entrada_id = int(cursor.lastrowid)

        for campo, valor_original in valores_enviados.items():
            valor = valores[campo]
            if valor is None or valor_original is None:
                continue
            origem, estado = (proveniencias or {}).get(
                campo,
                ("usuario", "confirmada"),
            )
            origem_limpa = self._opcional(origem)
            estado_limpo = self._opcional(estado)
            if origem_limpa is None or estado_limpo is None:
                raise ValueError("origem e estado da evidência são obrigatórios")
            self.conn.execute(
                """
                INSERT OR IGNORE INTO evidencias_conhecimento (
                    conhecimento_id, campo, valor, origem, estado
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (entrada_id, campo, valor, origem_limpa, estado_limpo),
            )

        self.conn.commit()
        linha = self.conn.execute(
            "SELECT * FROM conhecimento WHERE id = ?",
            (entrada_id,),
        ).fetchone()
        assert linha is not None
        entrada = self._entrada(linha)
        runtime_log.aprendizado(
            entrada.termo,
            {
                "entrada_id": entrada.id,
                "atualizada": bool(existente),
                "campos": [
                    campo
                    for campo in self.CAMPOS_CONHECIMENTO
                    if getattr(entrada, campo)
                ],
            },
        )
        return entrada

    def listar_evidencias(
        self,
        termo: str,
        contexto: Optional[str] = None,
    ) -> list[EvidenciaConhecimento]:
        termo_normalizado = self._normalizar_termo(termo)
        parametros: tuple[object, ...]
        filtro_contexto = ""
        if contexto is None:
            parametros = (termo_normalizado,)
        else:
            filtro_contexto = "AND c.contexto_uso = ?"
            parametros = (termo_normalizado, self._opcional(contexto))
        cursor = self.conn.execute(
            f"""
            SELECT e.*
            FROM evidencias_conhecimento AS e
            JOIN conhecimento AS c ON c.id = e.conhecimento_id
            WHERE c.termo_chave = ?
              {filtro_contexto}
            ORDER BY e.id
            """,
            parametros,
        )
        return [self._evidencia(linha) for linha in cursor.fetchall()]

    def buscar_fatos(
        self,
        contexto: Optional[str] = None,
    ) -> list[FatoConhecimento]:
        """Busca afirmações independentes de qualquer termo-chave."""
        cursor = self.conn.execute(
            "SELECT * FROM fatos_conhecimento ORDER BY id"
        )
        fatos = [self._fato(linha) for linha in cursor.fetchall()]
        if contexto is None:
            return fatos

        contexto_normalizado = self._opcional(contexto)
        if contexto_normalizado is None:
            return []
        return [
            fato
            for fato in fatos
            if fato.contexto.casefold() == contexto_normalizado.casefold()
        ]

    def buscar_fatos_confirmados(
        self,
        contexto: Optional[str] = None,
    ) -> list[FatoConhecimento]:
        """Retorna apenas fatos cujo estado atual está confirmado."""
        return [
            fato
            for fato in self.buscar_fatos(contexto)
            if fato.estado.casefold() == "confirmada"
        ]

    def buscar_fato(
        self,
        afirmacao: str,
        contexto: str,
    ) -> Optional[FatoConhecimento]:
        """Busca uma afirmação independente dentro de um contexto exato."""
        afirmacao_limpa = self._opcional(afirmacao)
        contexto_limpo = self._opcional(contexto)
        if afirmacao_limpa is None:
            raise ValueError("a afirmação do fato não pode ficar vazia")
        if contexto_limpo is None:
            raise ValueError("o contexto do fato não pode ficar vazio")

        afirmacao_normalizada = afirmacao_limpa.casefold()
        contexto_normalizado = contexto_limpo.casefold()
        for linha in self.conn.execute(
            "SELECT * FROM fatos_conhecimento ORDER BY id"
        ).fetchall():
            if str(linha["estado"]).casefold() == "revertida":
                continue
            if (
                str(linha["afirmacao"]).casefold() == afirmacao_normalizada
                and str(linha["contexto"]).casefold() == contexto_normalizado
            ):
                return self._fato(linha)
        return None

    def salvar_fato(
        self,
        afirmacao: str,
        contexto: str,
        *,
        origem: str = "usuario",
        estado: str = "confirmada",
        fato_id: Optional[int] = None,
        permissao: object | None = None,
    ) -> FatoConhecimento:
        """Insere um fato contextual ou registra uma correção pelo ID."""
        autorizacao = validar_permissao(
            permissao,
            TipoAcao.SALVAR_CONHECIMENTO,
            ALVO_CONHECIMENTO,
        )
        if not autorizacao.permitida:
            raise PermissionError(autorizacao.mensagem)

        afirmacao_limpa = self._opcional(afirmacao)
        contexto_limpo = self._opcional(contexto)
        origem_limpa = self._opcional(origem)
        estado_limpo = self._opcional(estado)
        if afirmacao_limpa is None:
            raise ValueError("a afirmação do fato não pode ficar vazia")
        if contexto_limpo is None:
            raise ValueError("o contexto do fato não pode ficar vazio")
        if origem_limpa is None or estado_limpo is None:
            raise ValueError("origem e estado do fato são obrigatórios")

        existente = None
        if fato_id is not None:
            existente = self.conn.execute(
                "SELECT id FROM fatos_conhecimento WHERE id = ?",
                (fato_id,),
            ).fetchone()
            if existente is None:
                raise LookupError(f"fato {fato_id} não encontrado")
            duplicado = self.conn.execute(
                """
                SELECT id
                FROM fatos_conhecimento
                WHERE afirmacao = ? COLLATE NOCASE
                  AND contexto = ? COLLATE NOCASE
                  AND estado <> 'revertida'
                  AND id <> ?
                LIMIT 1
                """,
                (afirmacao_limpa, contexto_limpo, fato_id),
            ).fetchone()
            if duplicado is not None:
                raise ValueError(
                    "a correção duplicaria outro fato no mesmo contexto"
                )
            self.conn.execute(
                """
                UPDATE fatos_conhecimento
                SET afirmacao = ?,
                    contexto = ?,
                    origem = ?,
                    estado = ?,
                    atualizado_em = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (
                    afirmacao_limpa,
                    contexto_limpo,
                    origem_limpa,
                    estado_limpo,
                    fato_id,
                ),
            )
            entrada_id = fato_id
        else:
            existente = self.conn.execute(
                """
                SELECT id
                FROM fatos_conhecimento
                WHERE afirmacao = ? COLLATE NOCASE
                  AND contexto = ? COLLATE NOCASE
                  AND estado <> 'revertida'
                LIMIT 1
                """,
                (afirmacao_limpa, contexto_limpo),
            ).fetchone()
            if existente is not None:
                return self._fato(
                    self.conn.execute(
                        "SELECT * FROM fatos_conhecimento WHERE id = ?",
                        (existente["id"],),
                    ).fetchone()
                )
            cursor = self.conn.execute(
                """
                INSERT INTO fatos_conhecimento (
                    afirmacao, contexto, origem, estado
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    afirmacao_limpa,
                    contexto_limpo,
                    origem_limpa,
                    estado_limpo,
                ),
            )
            entrada_id = int(cursor.lastrowid)

        self.conn.execute(
            """
            INSERT OR IGNORE INTO evidencias_fatos (
                fato_id, afirmacao, contexto, origem, estado
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                entrada_id,
                afirmacao_limpa,
                contexto_limpo,
                origem_limpa,
                estado_limpo,
            ),
        )
        self.conn.commit()
        linha = self.conn.execute(
            "SELECT * FROM fatos_conhecimento WHERE id = ?",
            (entrada_id,),
        ).fetchone()
        assert linha is not None
        fato = self._fato(linha)
        runtime_log.aprendizado(
            fato.afirmacao,
            {
                "fato_id": fato.id,
                "contexto": fato.contexto,
                "origem": fato.origem,
                "estado": fato.estado,
                "atualizado": fato_id is not None,
            },
        )
        return fato

    def listar_evidencias_fato(self, fato_id: int) -> list[EvidenciaFato]:
        cursor = self.conn.execute(
            """
            SELECT *
            FROM evidencias_fatos
            WHERE fato_id = ?
            ORDER BY id
            """,
            (fato_id,),
        )
        return [
            self._evidencia_fato(linha)
            for linha in cursor.fetchall()
        ]

    def listar_termos(self) -> list[str]:
        cursor = self.conn.execute(
            """
            SELECT DISTINCT termo_original
            FROM conhecimento
            ORDER BY termo_original COLLATE NOCASE
            """
        )
        return [str(linha["termo_original"]) for linha in cursor.fetchall()]

    def listar_expressoes_compostas(self) -> list[str]:
        return [
            termo
            for termo in self.listar_termos()
            if len(termo.split()) > 1
        ]

    def sugerir_termos(
        self,
        termo: str,
        limite: int = 3,
        proporcao_minima: float = 0.55,
    ) -> list[str]:
        termo_normalizado = self._normalizar_termo(termo)
        candidatos = []
        chaves_vistas: set[str] = set()
        for candidato in self.listar_termos():
            chave_candidato = self._normalizar_termo(candidato)
            proporcao = SequenceMatcher(
                None,
                termo_normalizado,
                chave_candidato,
            ).ratio()
            if (
                proporcao >= proporcao_minima
                and chave_candidato != termo_normalizado
                and chave_candidato not in chaves_vistas
            ):
                candidatos.append((proporcao, candidato))
                chaves_vistas.add(chave_candidato)
        candidatos.sort(key=lambda item: (-item[0], item[1]))
        return [candidato for _, candidato in candidatos[:limite]]

    def fechar(self) -> None:
        self.conn.close()

    def __enter__(self) -> "ConhecimentoDB":
        return self

    def __exit__(self, *_args: object) -> None:
        self.fechar()
