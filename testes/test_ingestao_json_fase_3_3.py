"""Testes da ingestão controlada de JSON da Fase 3.3."""

from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bancos.api_conhecimento import ConhecimentoAPI  # noqa: E402
from bancos.ingestao_json import IngestaoJSON  # noqa: E402
from bancos.persistencia_conhecimento import aplicar_contrato  # noqa: E402
from core.contratos import ContratoCadastro  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "aprendizado" / "bancos" / "linguagem_schema.sql"


def pacote_completo() -> dict:
    evidencia = {
        "evidencia_id": "ev-1",
        "fonte_tipo": "manual",
        "fonte_identificador": "usuario-ingestao",
        "origem": "teste 3.3",
        "trecho": "correr",
    }
    return {
        "proposta_id": "prop-ingestao",
        "entrada": "json",
        "idempotencia": "json:correr:v1",
        "evidencias": [evidencia],
        "objetos": [
            {
                "objeto_id": "lex-correr",
                "tipo": "lexema",
                "chave": "correr",
                "campos": [
                    {
                        "nome": "lema",
                        "valor": "correr",
                        "origem": "usuario",
                        "estado": "fornecida",
                        "evidencia_ids": ["ev-1"],
                    },
                    {
                        "nome": "categoria_lexical",
                        "valor": "verbo",
                        "origem": "usuario",
                        "estado": "fornecida",
                        "evidencia_ids": ["ev-1"],
                    },
                ],
            },
            {
                "objeto_id": "forma-corro",
                "tipo": "forma_lexical",
                "chave": "corro",
                "campos": [
                    {
                        "nome": "forma",
                        "valor": "corro",
                        "origem": "usuario",
                        "evidencia_ids": ["ev-1"],
                    },
                    {
                        "nome": "normalizada",
                        "valor": "corro",
                        "origem": "usuario",
                        "evidencia_ids": ["ev-1"],
                    },
                    {
                        "nome": "lexema",
                        "valor": "correr",
                        "origem": "usuario",
                        "evidencia_ids": ["ev-1"],
                    },
                ],
            },
            {
                "objeto_id": "sentido-correr",
                "tipo": "sentido",
                "chave": "correr:1",
                "campos": [
                    {
                        "nome": "definicao",
                        "valor": "deslocar-se rapidamente",
                        "origem": "usuario",
                        "evidencia_ids": ["ev-1"],
                    },
                    {
                        "nome": "lexema",
                        "valor": "correr",
                        "origem": "usuario",
                        "evidencia_ids": ["ev-1"],
                    },
                ],
            },
            {
                "objeto_id": "conceito-movimento",
                "tipo": "conceito",
                "chave": "movimento",
                "campos": [
                    {
                        "nome": "chave",
                        "valor": "movimento",
                        "origem": "usuario",
                        "evidencia_ids": ["ev-1"],
                    },
                    {
                        "nome": "rotulo",
                        "valor": "Movimento",
                        "origem": "usuario",
                        "evidencia_ids": ["ev-1"],
                    },
                    {
                        "nome": "tipo",
                        "valor": "evento",
                        "origem": "usuario",
                        "evidencia_ids": ["ev-1"],
                    },
                ],
                "relacoes": [
                    {
                        "tipo": "associado_a",
                        "origem_objeto_id": "conceito-movimento",
                        "destino_tipo": "sentido",
                        "destino_chave": "correr:1",
                        "evidencia_ids": ["ev-1"],
                    }
                ],
            },
        ],
    }


def pacote_relacoes_piloto() -> dict:
    return {
        "proposta_id": "prop-relacoes-piloto",
        "entrada": "json",
        "idempotencia": "piloto:relacoes:v2",
        "objetos": [
            {
                "objeto_id": "lex-bom",
                "tipo": "lexema",
                "chave": "bom",
                "campos": [
                    {"nome": "lema", "valor": "bom", "origem": "sistema"},
                    {
                        "nome": "categoria_lexical",
                        "valor": "adjetivo",
                        "origem": "sistema",
                    },
                ],
            },
            {
                "objeto_id": "expr-bom-dia",
                "tipo": "expressao",
                "chave": "bom dia",
                "campos": [
                    {"nome": "forma", "valor": "bom dia", "origem": "sistema"},
                    {
                        "nome": "normalizada",
                        "valor": "bom dia",
                        "origem": "sistema",
                    },
                    {
                        "nome": "tipo",
                        "valor": "conversacional",
                        "origem": "sistema",
                    },
                ],
                "relacoes": [
                    {
                        "tipo": "componente_de_expressao",
                        "origem_objeto_id": "expr-bom-dia",
                        "destino_tipo": "lexema",
                        "destino_chave": "bom",
                        "ordem": 1,
                    }
                ],
            },
            {
                "objeto_id": "expr-ola",
                "tipo": "expressao",
                "chave": "ola",
                "campos": [
                    {"nome": "forma", "valor": "olá", "origem": "sistema"},
                    {"nome": "normalizada", "valor": "ola", "origem": "sistema"},
                    {
                        "nome": "tipo",
                        "valor": "conversacional",
                        "origem": "sistema",
                    },
                ],
            },
            {
                "objeto_id": "expr-ola-pessoal",
                "tipo": "expressao",
                "chave": "ola pessoal",
                "campos": [
                    {
                        "nome": "forma",
                        "valor": "olá pessoal",
                        "origem": "sistema",
                    },
                    {
                        "nome": "normalizada",
                        "valor": "ola pessoal",
                        "origem": "sistema",
                    },
                    {
                        "nome": "tipo",
                        "valor": "conversacional",
                        "origem": "sistema",
                    },
                ],
            },
            {
                "objeto_id": "relacao-ola-tema",
                "tipo": "relacao_semantica",
                "chave": "relacionado_no_tema:ola:ola pessoal",
                "campos": [
                    {
                        "nome": "tipo_relacao",
                        "valor": "relacionado_no_tema",
                        "origem": "sistema",
                    },
                    {
                        "nome": "origem_tipo",
                        "valor": "expressao",
                        "origem": "sistema",
                    },
                    {
                        "nome": "origem_chave",
                        "valor": "ola",
                        "origem": "sistema",
                    },
                    {
                        "nome": "destino_tipo",
                        "valor": "expressao",
                        "origem": "sistema",
                    },
                    {
                        "nome": "destino_chave",
                        "valor": "ola pessoal",
                        "origem": "sistema",
                    },
                    {
                        "nome": "direcao",
                        "valor": "simetrica",
                        "origem": "sistema",
                    },
                ],
            },
        ],
    }


class TestIngestaoJSONFase33(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "linguagem.db"
        with sqlite3.connect(self.db) as conn:
            conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        self.api = ConhecimentoAPI(self.db)
        self.ingestao = IngestaoJSON(self.api)

    def tearDown(self) -> None:
        self.api.fechar()
        self.tmp.cleanup()

    def test_dry_run_nao_grava_e_retorna_relatorio(self):
        antes = hashlib.sha256(self.db.read_bytes()).hexdigest()

        relatorio = self.ingestao.dry_run(json.dumps(pacote_completo()))

        depois = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.assertTrue(relatorio.dry_run)
        self.assertFalse(relatorio.aplicado)
        self.assertEqual(antes, depois)
        self.assertFalse(hasattr(relatorio, "conn"))

    def test_piloto_aceita_componente_e_relacao_simetrica(self):
        relatorio = self.ingestao.dry_run(pacote_relacoes_piloto())

        self.assertTrue(relatorio.validacao.valido)
        self.assertFalse(relatorio.validacao.erros)
        self.assertFalse(relatorio.validacao.pendencias)

    def test_piloto_rejeita_combinacoes_fora_do_escopo(self):
        pacote = pacote_relacoes_piloto()
        pacote["objetos"][1]["relacoes"][0]["destino_tipo"] = "expressao"
        pacote["objetos"][4]["campos"][3]["valor"] = "lexema"

        relatorio = self.ingestao.dry_run(pacote)

        self.assertFalse(relatorio.validacao.valido)
        self.assertTrue(
            any("destino lexema" in erro for erro in relatorio.validacao.erros)
        )
        self.assertTrue(
            any("destino expressao" in erro for erro in relatorio.validacao.erros)
        )

    def test_piloto_mantem_ordem_ambigua_pendente(self):
        pacote = pacote_relacoes_piloto()
        pacote["objetos"][1]["campos"][1]["valor"] = "bom bom"
        pacote["objetos"][1]["campos"][2]["valor"] = "bom bom"

        relatorio = self.ingestao.dry_run(pacote)

        self.assertTrue(relatorio.validacao.valido)
        self.assertTrue(relatorio.validacao.incompleta)
        self.assertFalse(relatorio.validacao.pode_autorizar)
        self.assertTrue(
            any(
                "ordem de forma única" in pendencia
                for pendencia in relatorio.validacao.pendencias
            )
        )

    def test_piloto_rejeita_origem_embutida_fora_do_objeto(self):
        pacote = pacote_relacoes_piloto()
        pacote["objetos"][1]["relacoes"][0]["origem_objeto_id"] = "expr-ola"

        relatorio = self.ingestao.dry_run(pacote)

        self.assertFalse(relatorio.validacao.valido)
        self.assertTrue(
            any(
                "objeto de origem" in erro
                for erro in relatorio.validacao.erros
            )
        )

    def test_api_rejeita_direcao_direta_sem_reinterpretar(self):
        pacote = pacote_relacoes_piloto()
        pacote["objetos"][4]["campos"][5]["valor"] = "direta"

        resultado = self.api.validar(ContratoCadastro.from_dict(pacote))

        self.assertFalse(resultado.valido)
        self.assertTrue(
            any("direção simetrica" in erro for erro in resultado.erros)
        )

    def test_resposta_padrao_fica_fora_do_contrato_canonico(self):
        pacote = pacote_relacoes_piloto()
        pacote["objetos"][2]["campos"].append(
            {
                "nome": "resposta_padrao",
                "valor": "Olá!",
                "origem": "legado",
            }
        )

        with self.assertRaises(ValueError):
            self.ingestao.dry_run(pacote)

    def test_piloto_persiste_e_reutiliza_relacoes_sem_duplicate(self):
        proposta = self.ingestao.registrar(pacote_relacoes_piloto())
        self.ingestao.iniciar_revisao(proposta.contrato.proposta_id, "revisor")
        self.ingestao.autorizar(proposta.contrato.proposta_id, "revisor")

        primeira = self.ingestao.aplicar(proposta.contrato.proposta_id)
        reversa = deepcopy(pacote_relacoes_piloto())
        reversa["proposta_id"] = "prop-relacoes-piloto-reverso"
        reversa["idempotencia"] = "piloto:relacoes:reverso:v2"
        campos_relacao = reversa["objetos"][4]["campos"]
        campos = {campo["nome"]: campo for campo in campos_relacao}
        campos["origem_chave"]["valor"] = "ola pessoal"
        campos["destino_chave"]["valor"] = "ola"
        segunda_proposta = self.ingestao.registrar(reversa)
        self.ingestao.iniciar_revisao(
            segunda_proposta.contrato.proposta_id,
            "revisor",
        )
        self.ingestao.autorizar(
            segunda_proposta.contrato.proposta_id,
            "revisor",
        )
        segunda = self.ingestao.aplicar(segunda_proposta.contrato.proposta_id)

        self.assertTrue(primeira.aplicado)
        self.assertTrue(segunda.aplicado)
        self.assertTrue(
            any(
                item.startswith("expressao_componente:")
                for item in segunda.auditoria.registros_reutilizados
            )
        )
        self.assertTrue(
            any(
                item.startswith("relacao_semantica:")
                for item in segunda.auditoria.registros_reutilizados
            )
        )
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM expressao_componentes").fetchone()[0],
                1,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM relacoes_semanticas").fetchone()[0],
                1,
            )
            relacao = conn.execute(
                "SELECT origem_tipo, destino_tipo, direcao "
                "FROM relacoes_semanticas"
            ).fetchone()
            self.assertEqual(tuple(relacao), ("expressao", "expressao", "simetrica"))

    def test_ingestao_exige_revisao_e_autorizacao_antes_de_aplicar(self):
        proposta = self.ingestao.registrar(pacote_completo())

        with self.assertRaises(PermissionError):
            self.ingestao.aplicar(proposta.contrato.proposta_id)

        self.ingestao.iniciar_revisao(proposta.contrato.proposta_id, "revisor")
        with self.assertRaises(PermissionError):
            self.ingestao.aplicar(proposta.contrato.proposta_id)

    def test_aplicacao_autorizada_e_transacional(self):
        proposta = self.ingestao.registrar(pacote_completo())
        self.ingestao.iniciar_revisao(proposta.contrato.proposta_id, "revisor")
        self.ingestao.autorizar(proposta.contrato.proposta_id, "revisor")

        relatorio = self.ingestao.aplicar(proposta.contrato.proposta_id)

        self.assertTrue(relatorio.aplicado)
        self.assertIsNotNone(relatorio.auditoria)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM lexemas").fetchone()[0], 1)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM formas_lexicais").fetchone()[0],
                1,
            )
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM sentidos").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM conceitos").fetchone()[0], 1)
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM relacoes_semanticas").fetchone()[0],
                1,
            )
            self.assertEqual(
                conn.execute("SELECT COUNT(*) FROM evidencias").fetchone()[0],
                5,
            )

    def test_reaplicacao_reutiliza_registros_sem_duplicar(self):
        proposta = self.ingestao.registrar(pacote_completo())
        self.ingestao.iniciar_revisao(proposta.contrato.proposta_id, "revisor")
        self.ingestao.autorizar(proposta.contrato.proposta_id, "revisor")
        primeira = self.ingestao.aplicar(proposta.contrato.proposta_id)
        segunda = self.ingestao.aplicar(proposta.contrato.proposta_id)

        self.assertTrue(primeira.aplicado)
        self.assertTrue(segunda.auditoria.registros_reutilizados)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM lexemas").fetchone()[0], 1)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM evidencias").fetchone()[0], 5)

    def test_duplicidade_existente_e_reportada_sem_sobrescrever(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "INSERT INTO lexemas (lema, categoria_lexical, estado) "
                "VALUES ('correr', 'verbo', 'aprovado')"
            )
            conn.commit()

        relatorio = self.ingestao.validar(pacote_completo())

        self.assertIn("lexema:correr", relatorio.duplicidades)
        self.assertTrue(relatorio.validacao.valido)
        self.assertFalse(relatorio.aplicado)

    def test_referencia_fisica_incompleta_fica_pendente(self):
        pacote = pacote_completo()
        del pacote["objetos"][1]["campos"][2]

        relatorio = self.ingestao.validar(pacote)

        self.assertTrue(relatorio.validacao.incompleta)
        self.assertFalse(relatorio.validacao.pode_autorizar)

    def test_rollback_remove_todos_os_registros_da_transacao(self):
        pacote = pacote_completo()
        pacote["objetos"][1]["campos"][2]["valor"] = "lexema-ausente"
        proposta = self.ingestao.registrar(pacote)
        self.ingestao.iniciar_revisao(proposta.contrato.proposta_id, "revisor")
        self.ingestao.autorizar(proposta.contrato.proposta_id, "revisor")

        with self.assertRaisesRegex(ValueError, "referência não resolvida"):
            self.ingestao.aplicar(proposta.contrato.proposta_id)

        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM fontes").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM lexemas").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM evidencias").fetchone()[0], 0)

    def test_aplicacao_direta_sem_autorizacao_nao_grava(self):
        contrato = ContratoCadastro.from_dict(pacote_completo())

        with self.assertRaises(PermissionError):
            aplicar_contrato(self.db, contrato)

        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM fontes").fetchone()[0], 0)
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM lexemas").fetchone()[0], 0)

    def test_json_invalido_e_rejeitado_sem_acesso_ao_banco(self):
        with self.assertRaisesRegex(ValueError, "JSON inválido"):
            self.ingestao.validar("{não é json")


if __name__ == "__main__":
    unittest.main()