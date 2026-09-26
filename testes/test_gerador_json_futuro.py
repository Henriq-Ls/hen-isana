"""Validação do gerador de teste contra o fluxo real de ingestão."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bancos.api_conhecimento import ConhecimentoAPI  # noqa: E402
from bancos.ingestao_json import IngestaoJSON  # noqa: E402
from core.contratos import ContratoCadastro  # noqa: E402
from .gerador_json_teste import (  # noqa: E402
    gerar_arquivo_json_teste,
    gerar_json_teste,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "aprendizado" / "bancos" / "linguagem_schema.sql"


def evidencia(
    evidencia_id: str = "ev-1",
    *,
    fonte_tipo: str = "manual",
    fonte_identificador: str = "teste-gerador",
) -> dict:
    return {
        "evidencia_id": evidencia_id,
        "fonte_tipo": fonte_tipo,
        "fonte_identificador": fonte_identificador,
        "origem": "teste determinístico",
        "trecho": "correr",
    }


def campo(
    nome: str,
    valor: object,
    *,
    origem: str = "usuario",
    estado: str | None = None,
    evidencia_ids: list[str] | None = None,
) -> dict:
    item = {"nome": nome, "valor": valor, "origem": origem}
    if estado is not None:
        item["estado"] = estado
    if evidencia_ids is not None:
        item["evidencia_ids"] = evidencia_ids
    return item


def lexema_descricao(
    *,
    proposta_id: str = "prop-correr",
    idempotencia: str = "correr:v1",
    categoria: str = "verbo",
    campos: list[dict] | None = None,
) -> dict:
    return {
        "proposta_id": proposta_id,
        "entrada": "json",
        "idempotencia": idempotencia,
        "evidencias": [evidencia()],
        "objetos": [
            {
                "objeto_id": "lexema-correr",
                "tipo": "lexema",
                "chave": "correr",
                "campos": campos
                or [
                    campo("lema", "correr", evidencia_ids=["ev-1"]),
                    campo(
                        "categoria_lexical",
                        categoria,
                        evidencia_ids=["ev-1"],
                    ),
                ],
            }
        ],
    }


class TestGeradorJSONFuturo(unittest.TestCase):
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

    def gerar_arquivo(self, descricao: dict) -> tuple[dict, str]:
        caminho = Path(self.tmp.name) / f"{descricao['proposta_id']}.json"
        gerar_arquivo_json_teste(descricao, caminho)
        texto = caminho.read_text(encoding="utf-8")
        return json.loads(texto), texto

    def validar_dry_run(self, descricao: dict):
        pacote, texto = self.gerar_arquivo(descricao)
        self.assertIsInstance(pacote, dict)
        relatorio = self.ingestao.dry_run(texto)
        self.assertTrue(relatorio.dry_run)
        self.assertFalse(relatorio.aplicado)
        self.assertEqual(relatorio.contrato.proposta_id, descricao["proposta_id"])
        return relatorio

    def test_a_cadastro_simples_e_aceito(self):
        relatorio = self.validar_dry_run(lexema_descricao())

        self.assertTrue(relatorio.validacao.valido)
        self.assertFalse(relatorio.validacao.pendencias)
        self.assertFalse(relatorio.validacao.erros)

    def test_b_dois_sentidos_distintos_sao_preservados(self):
        descricao = lexema_descricao()
        descricao["objetos"] += [
            {
                "objeto_id": "sentido-correr-1",
                "tipo": "sentido",
                "chave": "correr:1",
                "campos": [
                    campo(
                        "definicao",
                        "deslocar-se rapidamente",
                        evidencia_ids=["ev-1"],
                    ),
                    campo("lexema", "correr", evidencia_ids=["ev-1"]),
                ],
            },
            {
                "objeto_id": "sentido-correr-2",
                "tipo": "sentido",
                "chave": "correr:2",
                "campos": [
                    campo(
                        "definicao",
                        "disputar uma corrida",
                        evidencia_ids=["ev-1"],
                    ),
                    campo("lexema", "correr", evidencia_ids=["ev-1"]),
                ],
            },
        ]

        relatorio = self.validar_dry_run(descricao)

        sentidos = [
            objeto
            for objeto in relatorio.contrato.objetos
            if objeto.tipo == "sentido"
        ]
        self.assertEqual(len(sentidos), 2)
        self.assertNotEqual(
            sentidos[0].campos[0].valor,
            sentidos[1].campos[0].valor,
        )

    def test_c_relacao_semantica_e_aceita(self):
        descricao = lexema_descricao()
        descricao["objetos"] += [
            {
                "objeto_id": "sentido-correr",
                "tipo": "sentido",
                "chave": "correr:movimento",
                "campos": [
                    campo(
                        "definicao",
                        "deslocar-se rapidamente",
                        evidencia_ids=["ev-1"],
                    ),
                    campo("lexema", "correr", evidencia_ids=["ev-1"]),
                ],
            },
            {
                "objeto_id": "conceito-movimento",
                "tipo": "conceito",
                "chave": "movimento",
                "campos": [
                    campo("chave", "movimento", evidencia_ids=["ev-1"]),
                    campo("rotulo", "Movimento", evidencia_ids=["ev-1"]),
                    campo("tipo", "evento", evidencia_ids=["ev-1"]),
                ],
                "relacoes": [
                    {
                        "tipo": "associado_a",
                        "origem_objeto_id": "conceito-movimento",
                        "destino_tipo": "sentido",
                        "destino_chave": "correr:movimento",
                        "evidencia_ids": ["ev-1"],
                    }
                ],
            },
        ]

        relatorio = self.validar_dry_run(descricao)

        self.assertTrue(relatorio.validacao.valido)
        conceito = next(
            objeto
            for objeto in relatorio.contrato.objetos
            if objeto.objeto_id == "conceito-movimento"
        )
        self.assertEqual(len(conceito.relacoes), 1)

    def test_d_evidencia_e_proveniencia_sao_preservadas(self):
        descricao = lexema_descricao()
        descricao["evidencias"][0].update(
            {
                "referencia": "fonte-documental-1",
                "confianca": 0.8,
            }
        )

        relatorio = self.validar_dry_run(descricao)

        self.assertEqual(
            relatorio.contrato.evidencias[0].fonte_identificador,
            "teste-gerador",
        )
        self.assertEqual(
            relatorio.contrato.evidencias[0].referencia,
            "fonte-documental-1",
        )

    def test_e_proposta_incompleta_continua_pendente(self):
        descricao = lexema_descricao(
            campos=[campo("lema", "correr", evidencia_ids=["ev-1"])]
        )
        descricao["pendencias"] = ["categoria lexical ausente"]

        relatorio = self.validar_dry_run(descricao)

        self.assertTrue(relatorio.validacao.valido)
        self.assertTrue(relatorio.validacao.incompleta)
        self.assertFalse(relatorio.validacao.pode_autorizar)

    def test_f_incerteza_e_preservada_sem_confirmacao(self):
        descricao = lexema_descricao()
        descricao["incertezas"] = ["a categoria ainda precisa de confirmação"]
        descricao["objetos"][0]["campos"][1]["estado"] = "proposta"
        descricao["objetos"][0]["campos"][1]["confianca"] = 0.4

        relatorio = self.validar_dry_run(descricao)

        self.assertIn(
            "a categoria ainda precisa de confirmação",
            relatorio.contrato.incertezas,
        )
        self.assertEqual(
            relatorio.contrato.objetos[0].campos[1].estado,
            "proposta",
        )

    def test_g_referencia_logica_pendente_nao_e_inventada(self):
        descricao = {
            "proposta_id": "prop-forma-pendente",
            "entrada": "json",
            "idempotencia": "forma:corro:v1",
            "pendencias": ["lexema ainda não identificado"],
            "evidencias": [evidencia()],
            "objetos": [
                {
                    "objeto_id": "forma-corro",
                    "tipo": "forma_lexical",
                    "chave": "corro",
                    "campos": [
                        campo("forma", "corro", evidencia_ids=["ev-1"]),
                        campo("normalizada", "corro", evidencia_ids=["ev-1"]),
                    ],
                }
            ],
        }

        relatorio = self.validar_dry_run(descricao)

        self.assertTrue(relatorio.validacao.incompleta)
        self.assertTrue(
            any("lexema" in pendencia for pendencia in relatorio.validacao.pendencias)
        )

    def test_h_duplicidade_e_idempotencia_sao_deterministicas(self):
        descricao = lexema_descricao()
        primeiro = gerar_json_teste(descricao)
        segundo = gerar_json_teste(deepcopy(descricao))
        self.assertEqual(primeiro, segundo)

        proposta_1 = self.ingestao.registrar(primeiro)
        proposta_2 = self.ingestao.registrar(segundo)
        self.assertIs(proposta_1, proposta_2)

        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "INSERT INTO lexemas "
                "(lema, categoria_lexical, estado) "
                "VALUES ('correr', 'verbo', 'aprovado')"
            )
            conn.commit()
        relatorio = self.ingestao.dry_run(primeiro)
        self.assertIn("lexema:correr", relatorio.duplicidades)

    def test_i_conflito_e_encaminhado_para_revisao(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "INSERT INTO lexemas "
                "(lema, categoria_lexical, estado) "
                "VALUES ('correr', 'substantivo', 'aprovado')"
            )
            conn.commit()

        relatorio = self.validar_dry_run(lexema_descricao())

        self.assertTrue(relatorio.validacao.valido)
        self.assertTrue(relatorio.validacao.conflitos)
        self.assertFalse(relatorio.validacao.pode_autorizar)

    def test_j_campo_fisico_e_rejeitado_pelo_gerador(self):
        descricao = lexema_descricao()
        descricao["objetos"][0]["campos"].append(
            campo("tabela_sqlite", "lexemas", evidencia_ids=["ev-1"])
        )

        with self.assertRaisesRegex(ValueError, "não suportado"):
            gerar_json_teste(descricao)

    def test_k_sql_e_rejeitado_sem_execucao(self):
        descricao = lexema_descricao()
        descricao["objetos"][0]["campos"].append(
            campo(
                "descricao",
                "SELECT lema FROM lexemas; DROP TABLE conceitos;",
                evidencia_ids=["ev-1"],
            )
        )

        with self.assertRaisesRegex(ValueError, "contém SQL"):
            gerar_json_teste(descricao)

    def test_l_codigo_executavel_e_rejeitado_sem_execucao(self):
        marcador = Path(self.tmp.name) / "nao-deve-existir"
        descricao = lexema_descricao()
        descricao["objetos"][0]["campos"].append(
            campo(
                "descricao",
                f"__import__('pathlib').Path({str(marcador)!r}).write_text('x')",
                evidencia_ids=["ev-1"],
            )
        )

        with self.assertRaisesRegex(ValueError, "código executável"):
            gerar_json_teste(descricao)
        self.assertFalse(marcador.exists())

    def test_uniformidade_canonica_independe_da_ordem_de_entrada(self):
        primeiro = lexema_descricao()
        primeiro["evidencias"].append(
            evidencia(
                "ev-0",
                fonte_identificador="teste-gerador-0",
            )
        )
        primeiro["objetos"][0]["campos"].reverse()
        primeiro["objetos"].extend(
            [
                {
                    "objeto_id": "sentido-correr",
                    "tipo": "sentido",
                    "chave": "correr:movimento",
                    "campos": [
                        campo(
                            "definicao",
                            "deslocar-se rapidamente",
                            evidencia_ids=["ev-1"],
                        ),
                        campo("lexema", "correr", evidencia_ids=["ev-1"]),
                    ],
                },
                {
                    "objeto_id": "conceito-movimento",
                    "tipo": "conceito",
                    "chave": "movimento",
                    "campos": [
                        campo("chave", "movimento", evidencia_ids=["ev-1"]),
                        campo("rotulo", "Movimento", evidencia_ids=["ev-1"]),
                        campo("tipo", "evento", evidencia_ids=["ev-1"]),
                    ],
                    "relacoes": [
                        {
                            "tipo": "associado_a",
                            "origem_objeto_id": "conceito-movimento",
                            "destino_tipo": "sentido",
                            "destino_chave": "correr:movimento",
                        },
                        {
                            "tipo": "relacionado_a",
                            "origem_objeto_id": "conceito-movimento",
                            "destino_tipo": "sentido",
                            "destino_chave": "correr:movimento",
                        },
                    ],
                },
            ]
        )

        segundo = deepcopy(primeiro)
        segundo["evidencias"].reverse()
        segundo["objetos"].reverse()
        segundo["objetos"][0]["campos"].reverse()
        segundo["objetos"][0]["relacoes"].reverse()

        self.assertEqual(
            gerar_json_teste(primeiro),
            gerar_json_teste(segundo),
        )

    def test_dry_run_nao_altera_banco_real(self):
        banco_real = ROOT / "aprendizado" / "bancos" / "linguagem.db"
        antes = hashlib.sha256(banco_real.read_bytes()).hexdigest()

        _, texto = self.gerar_arquivo(lexema_descricao())
        self.ingestao.dry_run(texto)
        proposta = self.ingestao.registrar(texto)
        with self.assertRaises(PermissionError):
            self.ingestao.aplicar(proposta.contrato.proposta_id)

        depois = hashlib.sha256(banco_real.read_bytes()).hexdigest()
        self.assertEqual(antes, depois)


if __name__ == "__main__":
    unittest.main()