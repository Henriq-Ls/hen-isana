"""Testes da preparação de lotes JSON da Fase 3.7."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from aplicacao.lotes_json import (
    LotesJSONConhecimento,
    carregar_descricoes_json,
    inventariar_fontes,
)
from aplicacao.contrato_entrada import contrato_de_json
from bancos.api_conhecimento import ConhecimentoAPI, ResultadoValidacao
from bancos.ingestao_json import IngestaoJSON, RelatorioIngestao


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "aprendizado" / "bancos" / "linguagem_schema.sql"


def pacote_lexema(
    proposta_id: str = "prop-correr",
    categoria: str = "verbo",
) -> dict:
    return {
        "proposta_id": proposta_id,
        "entrada": "json",
        "idempotencia": f"{proposta_id}:v1",
        "evidencias": [
            {
                "evidencia_id": "ev-1",
                "fonte_tipo": "manual",
                "fonte_identificador": "teste-lote",
                "origem": "teste determinístico",
                "trecho": "correr",
            }
        ],
        "objetos": [
            {
                "objeto_id": "lexema-correr",
                "tipo": "lexema",
                "chave": "correr",
                "campos": [
                    {
                        "nome": "lema",
                        "valor": "correr",
                        "origem": "usuario",
                        "evidencia_ids": ["ev-1"],
                    },
                    {
                        "nome": "categoria_lexical",
                        "valor": categoria,
                        "origem": "usuario",
                        "evidencia_ids": ["ev-1"],
                    },
                ],
            }
        ],
    }


class TestLotesJSONFase37(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.raiz = Path(self.tmp.name) / "lotes_json"
        self.lotes = LotesJSONConhecimento(self.raiz)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_inventario_separa_fonte_elegivel_de_fixtures_e_legado(self):
        fontes = {
            fonte.identificador: fonte
            for fonte in inventariar_fontes(ROOT)
        }
        self.assertTrue(fontes["documentacao-json-conhecimento"].elegivel)
        self.assertEqual(fontes["documentacao-json-conhecimento"].quantidade, 7)
        self.assertFalse(fontes["documentacao-json-fase-1-3"].elegivel)
        self.assertFalse(fontes["conhecimento-legado"].elegivel)
        self.assertFalse(fontes["linguagem-canonica"].elegivel)
        self.assertFalse(fontes["snapshots-de-codigo"].elegivel)

    def test_carrega_somente_jsons_diretos_sem_executar_conteudo(self):
        fonte = Path(self.tmp.name) / "fonte"
        fonte.mkdir()
        (fonte / "a.json").write_text(
            json.dumps(pacote_lexema()), encoding="utf-8"
        )
        (fonte / "nao-json.txt").write_text("__import__('x')", encoding="utf-8")
        descricoes = carregar_descricoes_json(fonte)
        self.assertEqual(tuple(descricoes), ("a.json",))
        self.assertEqual(descricoes["a.json"]["proposta_id"], "prop-correr")

    def test_manifesto_e_layout_sao_deterministicos(self):
        primeiro = {
            "z.json": pacote_lexema("prop-z"),
            "a.json": pacote_lexema("prop-a"),
        }
        segundo = {
            "a.json": deepcopy(primeiro["a.json"]),
            "z.json": deepcopy(primeiro["z.json"]),
        }
        lote_a = self.lotes.preparar(
            primeiro,
            fonte="documentacao-json",
            assunto="lexico",
            lote_id="exemplos",
        )
        lote_b = self.lotes.preparar(
            segundo,
            fonte="documentacao-json",
            assunto="lexico",
            lote_id="exemplos",
        )
        self.assertEqual(lote_a.manifesto_json(), lote_b.manifesto_json())
        caminho = self.lotes.gravar(lote_a)
        self.assertEqual(
            caminho.relative_to(self.raiz).as_posix(),
            "documentacao-json/lexico/exemplos/v1",
        )
        self.assertEqual(
            sorted(item.name for item in (caminho / "propostas").iterdir()),
            ["a.json", "z.json"],
        )
        manifesto = json.loads((caminho / "manifesto.json").read_text())
        self.assertEqual(manifesto["totais"]["objetos"], 2)
        self.assertEqual(manifesto["totais"]["relacoes"], 0)
        self.assertEqual(manifesto["totais"]["evidencias"], 2)

    def test_repeticao_identica_e_idempotente(self):
        lote = self.lotes.preparar(
            {"correr": pacote_lexema()},
            fonte="manual",
            assunto="lexico",
            lote_id="base",
        )
        primeiro = self.lotes.gravar(lote)
        segundo = self.lotes.gravar(lote)
        self.assertEqual(primeiro, segundo)
        self.assertEqual(len(tuple(primeiro.rglob("*"))), 3)

    def test_conteudo_diferente_nao_sobrescreve_mesma_versao(self):
        primeiro = self.lotes.preparar(
            {"correr": pacote_lexema()},
            fonte="manual",
            assunto="lexico",
            lote_id="base",
        )
        self.lotes.gravar(primeiro)
        diferente = self.lotes.preparar(
            {"correr": pacote_lexema(categoria="substantivo")},
            fonte="manual",
            assunto="lexico",
            lote_id="base",
        )
        with self.assertRaises(FileExistsError):
            self.lotes.gravar(diferente)

    def test_rejeicao_impede_gravacao_do_lote(self):
        invalido = pacote_lexema()
        invalido["objetos"][0]["campos"].append(
            {
                "nome": "descricao",
                "valor": "SELECT lema FROM lexemas",
                "origem": "usuario",
            }
        )
        lote = self.lotes.preparar(
            {"invalido": invalido},
            fonte="manual",
            assunto="lexico",
            lote_id="invalido",
        )
        self.assertEqual(lote.entradas[0].status, "rejeitado")
        with self.assertRaises(ValueError):
            self.lotes.gravar(lote)
        self.assertFalse((self.raiz / "manual").exists())

    def test_validacao_do_lote_usa_dry_run_e_nao_altera_banco(self):
        lote = self.lotes.preparar(
            {"correr": pacote_lexema()},
            fonte="manual",
            assunto="lexico",
            lote_id="base",
        )
        caminho = self.lotes.gravar(lote)
        banco = Path(self.tmp.name) / "linguagem.db"
        with sqlite3.connect(banco) as conn:
            conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        antes = hashlib.sha256(banco.read_bytes()).hexdigest()
        api = ConhecimentoAPI(banco)
        try:
            relatorio = self.lotes.validar_lote(caminho, IngestaoJSON(api))
        finally:
            api.fechar()
        depois = hashlib.sha256(banco.read_bytes()).hexdigest()
        self.assertTrue(relatorio.valido, relatorio.motivos)
        self.assertEqual(relatorio.totais["aceitos"], 1)
        self.assertEqual(antes, depois)

    def test_conflito_do_dry_run_e_contado_no_manifesto(self):
        class IngestaoConflito:
            def __init__(self) -> None:
                self.chamadas = 0

            def dry_run(self, texto: str) -> RelatorioIngestao:
                self.chamadas += 1
                contrato = contrato_de_json(texto)
                return RelatorioIngestao(
                    contrato=contrato,
                    validacao=ResultadoValidacao(
                        proposta_id=contrato.proposta_id,
                        valido=True,
                        conflitos=("conflito lógico preservado",),
                    ),
                    duplicidades=("lexema:correr",),
                )

        ingestao = IngestaoConflito()
        lote = self.lotes.preparar(
            {"correr": pacote_lexema()},
            fonte="manual",
            assunto="lexico",
            lote_id="conflito",
            ingestao=ingestao,
        )
        self.assertEqual(ingestao.chamadas, 1)
        self.assertEqual(lote.entradas[0].status, "conflito")
        self.assertEqual(lote.entradas[0].conflitos, 1)
        self.assertEqual(lote.totais["conflitos"], 1)
        self.assertEqual(lote.totais["conflitos_detalhados"], 1)

    def test_validacao_detecta_hash_de_arquivo_alterado(self):
        lote = self.lotes.preparar(
            {"correr": pacote_lexema()},
            fonte="manual",
            assunto="lexico",
            lote_id="base",
        )
        caminho = self.lotes.gravar(lote)
        arquivo = caminho / "propostas" / "correr.json"
        arquivo.write_text(arquivo.read_text() + " ", encoding="utf-8")
        banco = Path(self.tmp.name) / "linguagem.db"
        with sqlite3.connect(banco) as conn:
            conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        api = ConhecimentoAPI(banco)
        try:
            relatorio = self.lotes.validar_lote(caminho, IngestaoJSON(api))
        finally:
            api.fechar()
        self.assertFalse(relatorio.manifesto_integro)
        self.assertIn("hash divergente", relatorio.motivos[0])

    def test_validacao_detecta_arquivo_extra_nao_declarado(self):
        lote = self.lotes.preparar(
            {"correr": pacote_lexema()},
            fonte="manual",
            assunto="lexico",
            lote_id="base",
        )
        caminho = self.lotes.gravar(lote)
        (caminho / "propostas" / "extra.json").write_text(
            "arquivo não declarado",
            encoding="utf-8",
        )
        banco = Path(self.tmp.name) / "linguagem.db"
        with sqlite3.connect(banco) as conn:
            conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        api = ConhecimentoAPI(banco)
        try:
            relatorio = self.lotes.validar_lote(caminho, IngestaoJSON(api))
        finally:
            api.fechar()
        self.assertFalse(relatorio.manifesto_integro)
        self.assertIn(
            "arquivo não declarado: propostas/extra.json",
            relatorio.motivos,
        )

    def test_validacao_rejeita_versao_ou_contrato_desconhecido(self):
        lote = self.lotes.preparar(
            {"correr": pacote_lexema()},
            fonte="manual",
            assunto="lexico",
            lote_id="base",
        )
        caminho = self.lotes.gravar(lote)
        manifesto_path = caminho / "manifesto.json"
        manifesto = json.loads(manifesto_path.read_text(encoding="utf-8"))
        banco = Path(self.tmp.name) / "linguagem.db"
        with sqlite3.connect(banco) as conn:
            conn.executescript(SCHEMA.read_text(encoding="utf-8"))
        api = ConhecimentoAPI(banco)
        try:
            manifesto["formato_versao"] = "desconhecida"
            manifesto_path.write_text(
                json.dumps(manifesto),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "versão de formato"):
                self.lotes.validar_lote(caminho, IngestaoJSON(api))

            manifesto["formato_versao"] = "1"
            manifesto["contrato"] = "ContratoDesconhecido"
            manifesto_path.write_text(
                json.dumps(manifesto),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(ValueError, "contrato de lote"):
                self.lotes.validar_lote(caminho, IngestaoJSON(api))
        finally:
            api.fechar()

    def test_referencias_e_estados_do_gerador_sao_preservados(self):
        descricoes = carregar_descricoes_json(
            ROOT / "docs" / "exemplos_json_conhecimento"
        )
        lote = self.lotes.preparar(
            descricoes,
            fonte="documentacao-json",
            assunto="contrato",
            lote_id="exemplos",
        )
        self.assertEqual(len(lote.entradas), 7)
        self.assertEqual(lote.totais["pendentes"], 2)
        self.assertEqual(lote.totais["aceitos"], 5)
        self.assertEqual(lote.totais["rejeitados"], 0)
        self.lotes.gravar(lote)


if __name__ == "__main__":
    unittest.main()