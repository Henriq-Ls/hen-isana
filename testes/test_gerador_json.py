"""Testes do gerador definitivo de JSON da Fase 3.7."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from aplicacao.gerador_json import GeradorJSONConhecimento
from bancos.api_conhecimento import ConhecimentoAPI
from bancos.ingestao_json import IngestaoJSON


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "aprendizado" / "bancos" / "linguagem_schema.sql"


def evidencia(
    evidencia_id: str = "ev-1",
    *,
    fonte_identificador: str = "teste-gerador-definitivo",
) -> dict:
    return {
        "evidencia_id": evidencia_id,
        "fonte_tipo": "manual",
        "fonte_identificador": fonte_identificador,
        "origem": "teste determinístico",
        "trecho": "correr",
    }


def campo(
    nome: str,
    valor: object,
    *,
    evidencia_ids: list[str] | None = None,
    estado: str | None = None,
) -> dict:
    item = {"nome": nome, "valor": valor, "origem": "usuario"}
    if evidencia_ids is not None:
        item["evidencia_ids"] = evidencia_ids
    if estado is not None:
        item["estado"] = estado
    return item


def descricao_lexema(
    *,
    proposta_id: str = "prop-correr",
    idempotencia: str = "correr:v1",
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
                "campos": [
                    campo("lema", "correr", evidencia_ids=["ev-1"]),
                    campo(
                        "categoria_lexical",
                        "verbo",
                        evidencia_ids=["ev-1"],
                    ),
                ],
            }
        ],
    }


class TestGeradorJSON(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "linguagem.db"
        with sqlite3.connect(self.db) as conn:
            conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        self.api = ConhecimentoAPI(self.db)
        self.ingestao = IngestaoJSON(self.api)
        self.gerador = GeradorJSONConhecimento()

    def tearDown(self) -> None:
        self.api.fechar()
        self.tmp.cleanup()

    def validar(self, descricao: dict):
        resultado = self.gerador.validar_no_fluxo_real(
            descricao,
            self.ingestao,
        )
        self.assertNotEqual(resultado.status, "rejeitado", resultado.motivos)
        self.assertTrue(resultado.json_texto)
        return resultado

    def test_cadastro_simples(self):
        resultado = self.validar(descricao_lexema())
        self.assertEqual(resultado.status, "aceito")

    def test_multiplos_sentidos_sao_preservados(self):
        descricao = descricao_lexema()
        descricao["objetos"].extend(
            [
                {
                    "objeto_id": "sentido-1",
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
                    "objeto_id": "sentido-2",
                    "tipo": "sentido",
                    "chave": "correr:disputa",
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
        )
        resultado = self.validar(descricao)
        objetos = json.loads(resultado.json_texto)["objetos"]
        self.assertEqual(
            [item["objeto_id"] for item in objetos],
            ["lexema-correr", "sentido-1", "sentido-2"],
        )

    def test_relacao_logica_e_preservada(self):
        descricao = descricao_lexema()
        descricao["objetos"].extend(
            [
                {
                    "objeto_id": "sentido-1",
                    "tipo": "sentido",
                    "chave": "correr:movimento",
                    "campos": [
                        campo("definicao", "deslocar-se", evidencia_ids=["ev-1"]),
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
        )
        resultado = self.validar(descricao)
        conceito = next(
            item
            for item in json.loads(resultado.json_texto)["objetos"]
            if item["objeto_id"] == "conceito-movimento"
        )
        self.assertEqual(conceito["relacoes"][0]["destino_chave"], "correr:movimento")

    def test_evidencia_proveniencia_e_incerteza_sao_preservadas(self):
        descricao = descricao_lexema()
        descricao["evidencias"][0].update(
            {"referencia": "fonte-1", "confianca": 0.8}
        )
        descricao["incertezas"] = ["categoria ainda não confirmada"]
        descricao["objetos"][0]["campos"][1].update(
            {"estado": "proposta", "confianca": 0.4}
        )
        resultado = self.validar(descricao)
        pacote = json.loads(resultado.json_texto)
        self.assertEqual(pacote["evidencias"][0]["referencia"], "fonte-1")
        categoria = next(
            item
            for item in pacote["objetos"][0]["campos"]
            if item["nome"] == "categoria_lexical"
        )
        self.assertEqual(categoria["confianca"], 0.4)
        self.assertIn("incertezas preservadas", resultado.motivos[0])

    def test_pendencia_nao_e_preenchida(self):
        descricao = descricao_lexema()
        descricao["objetos"][0]["campos"].pop()
        descricao["pendencias"] = ["categoria lexical ausente"]
        resultado = self.validar(descricao)
        self.assertEqual(resultado.status, "pendente")
        self.assertIn("categoria lexical ausente", resultado.motivos)

    def test_entrada_incompleta_continua_pendente(self):
        descricao = descricao_lexema()
        descricao["objetos"][0]["campos"].pop()
        resultado = self.validar(descricao)
        self.assertEqual(resultado.status, "pendente")
        self.assertTrue(any("categoria_lexical" in item for item in resultado.motivos))

    def test_referencia_desconhecida_nao_e_inventada(self):
        descricao = {
            "proposta_id": "prop-forma",
            "entrada": "json",
            "idempotencia": "forma:corro:v1",
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
        resultado = self.validar(descricao)
        self.assertEqual(resultado.status, "pendente")
        self.assertTrue(any("lexema" in item for item in resultado.motivos))

    def test_conflito_e_duplicidade_sao_reportados(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute(
                "INSERT INTO lexemas (lema, categoria_lexical, estado) "
                "VALUES ('correr', 'substantivo', 'aprovado')"
            )
            conn.commit()
        resultado = self.gerador.validar_no_fluxo_real(
            descricao_lexema(),
            self.ingestao,
        )
        self.assertEqual(resultado.status, "conflito")
        self.assertIn("lexema:correr", resultado.duplicidades)
        self.assertTrue(resultado.motivos)

    def test_idempotencia_e_repeticao_produzem_mesmo_json(self):
        descricao = descricao_lexema()
        primeiro = self.gerador.gerar_json(descricao)
        segundo = self.gerador.gerar_json(deepcopy(descricao))
        self.assertEqual(primeiro, segundo)
        proposta_1 = self.ingestao.registrar(primeiro)
        proposta_2 = self.ingestao.registrar(segundo)
        self.assertIs(proposta_1, proposta_2)

    def test_ordem_da_entrada_nao_altera_json(self):
        primeiro = descricao_lexema()
        primeiro["evidencias"].append(
            evidencia("ev-0", fonte_identificador="fonte-0")
        )
        primeiro["objetos"][0]["campos"].reverse()
        segundo = deepcopy(primeiro)
        segundo["evidencias"].reverse()
        segundo["objetos"].reverse()
        segundo["objetos"][0]["campos"].reverse()
        self.assertEqual(
            self.gerador.gerar_json(primeiro),
            self.gerador.gerar_json(segundo),
        )

    def test_campo_fisico_e_rejeitado(self):
        descricao = descricao_lexema()
        descricao["objetos"][0]["campos"].append(
            campo("tabela_sqlite", "lexemas")
        )
        resultado = self.gerador.gerar(descricao)
        self.assertEqual(resultado.status, "rejeitado")
        self.assertTrue(any("referência física" in item for item in resultado.motivos))

    def test_sql_e_rejeitado_sem_execucao(self):
        descricao = descricao_lexema()
        descricao["objetos"][0]["campos"].append(
            campo("descricao", "SELECT lema FROM lexemas; DROP TABLE conceitos;")
        )
        resultado = self.gerador.gerar(descricao)
        self.assertEqual(resultado.status, "rejeitado")
        self.assertTrue(any("SQL" in item for item in resultado.motivos))

    def test_codigo_executavel_e_rejeitado_sem_execucao(self):
        marcador = Path(self.tmp.name) / "nao-criar"
        descricao = descricao_lexema()
        descricao["objetos"][0]["campos"].append(
            campo(
                "descricao",
                f"__import__('pathlib').Path({str(marcador)!r}).write_text('x')",
            )
        )
        resultado = self.gerador.gerar(descricao)
        self.assertEqual(resultado.status, "rejeitado")
        self.assertFalse(marcador.exists())

    def test_duplicidade_de_ids_e_rejeitada(self):
        descricao = descricao_lexema()
        descricao["evidencias"].append(evidencia())
        resultado = self.gerador.gerar(descricao)
        self.assertEqual(resultado.status, "rejeitado")

    def test_arquivo_individual_nao_aplica(self):
        caminho = Path(self.tmp.name) / "pacote.json"
        resultado = self.gerador.gerar_arquivo(descricao_lexema(), caminho)
        self.assertEqual(resultado.status, "aceito")
        self.assertEqual(json.loads(caminho.read_text())["entrada"], "json")
        self.assertEqual(caminho.read_text().endswith("\n"), True)

    def test_lote_organiza_arquivos_sem_aplicar(self):
        diretorio = Path(self.tmp.name) / "lote"
        resultados = self.gerador.gerar_lote(
            {"zeta": descricao_lexema(proposta_id="z", idempotencia="z"),
             "alfa": descricao_lexema(proposta_id="a", idempotencia="a")},
            diretorio,
        )
        self.assertEqual([item.status for item in resultados], ["aceito", "aceito"])
        self.assertEqual(sorted(item.name for item in diretorio.iterdir()), ["alfa.json", "zeta.json"])

    def test_nome_de_lote_inseguro_e_rejeitado(self):
        resultados = self.gerador.gerar_lote(
            {"../fora": descricao_lexema()},
            Path(self.tmp.name) / "lote",
        )
        self.assertEqual(resultados[0].status, "rejeitado")
        self.assertFalse((Path(self.tmp.name) / "fora.json").exists())

    def test_dry_run_nao_altera_banco_real(self):
        banco_real = ROOT / "aprendizado" / "bancos" / "linguagem.db"
        antes = hashlib.sha256(banco_real.read_bytes()).hexdigest()
        api_real = ConhecimentoAPI(banco_real)
        try:
            resultado = self.gerador.validar_no_fluxo_real(
                descricao_lexema(),
                IngestaoJSON(api_real),
            )
        finally:
            api_real.fechar()
        self.assertEqual(resultado.status, "aceito")
        depois = hashlib.sha256(banco_real.read_bytes()).hexdigest()
        self.assertEqual(antes, depois)


if __name__ == "__main__":
    unittest.main()