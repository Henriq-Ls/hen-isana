"""Testes da geração auditável de lotes a partir do legado."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from aplicacao.contrato_entrada import contrato_de_json
from aplicacao.lotes_json import LotesJSONConhecimento
from aplicacao.migracao_legado_json import (
    _marcar_rejeitados_no_ledger,
    _preparar_lote,
    gerar_lotes_migracao_legado,
    revisar_lotes_migracao_legado,
)
from bancos.api_conhecimento import ResultadoValidacao
from bancos.ingestao_json import RelatorioIngestao


ROOT = Path(__file__).resolve().parents[1]
_BANCOS = (
    ROOT / "aprendizado" / "bancos" / "conhecimento.db",
    ROOT / "aprendizado" / "bancos" / "relacoes.db",
    ROOT / "aprendizado" / "bancos" / "linguagem.db",
    ROOT / "aprendizado" / "bancos" / "indice_codigo.db",
    ROOT / "aprendizado" / "bancos" / "log_mudancas.db",
    ROOT / "data" / "diagnostico.db",
)


def _hashes() -> dict[str, str]:
    return {
        caminho.relative_to(ROOT).as_posix(): hashlib.sha256(
            caminho.read_bytes()
        ).hexdigest()
        for caminho in _BANCOS
    }


class _Rejeitador:
    def dry_run(self, texto: str) -> RelatorioIngestao:
        contrato = contrato_de_json(texto)
        return RelatorioIngestao(
            contrato=contrato,
            validacao=ResultadoValidacao(
                proposta_id=contrato.proposta_id,
                valido=False,
                erros=("rejeição de teste",),
            ),
        )


class TestMigracaoLegadoJSON(unittest.TestCase):
    def test_gera_lotes_dry_run_e_preserva_os_bancos(self):
        antes = _hashes()
        with tempfile.TemporaryDirectory() as temporario:
            resultado = gerar_lotes_migracao_legado(
                projeto=ROOT,
                saida=Path(temporario) / "lotes",
            )
            depois = _hashes()
            relatorio = json.loads(
                resultado.relatorio.read_text(encoding="utf-8")
            )
            ledger = json.loads(
                resultado.ledger.read_text(encoding="utf-8")
            )

        self.assertEqual(antes, depois)
        self.assertTrue(relatorio["hashes_bancos_inalterados"])
        self.assertFalse(relatorio["dry_run"]["aplicado"])
        self.assertFalse(relatorio["registrar_chamado"])
        self.assertFalse(relatorio["autorizar_chamado"])
        self.assertTrue(relatorio["dry_run"]["todos_manifestos_integros"])
        self.assertEqual(relatorio["quantidades"]["lotes_gerados"], 2)
        self.assertEqual(relatorio["quantidades"]["jsons_gerados"], 70)
        self.assertEqual(
            relatorio["informacoes_sem_correspondencia"][
                "relacoes_sem_direcao_ou_ordem"
            ],
            66,
        )
        self.assertEqual(
            ledger["totais"],
            {
                "elegivel": 0,
                "pendente": 287,
                "conflitante": 33,
                "rejeitado": 0,
                "excluido": 0,
            },
        )

    def test_repeticao_do_mesmo_lote_e_idempotente(self):
        with tempfile.TemporaryDirectory() as temporario:
            saida = Path(temporario) / "lotes"
            primeiro = gerar_lotes_migracao_legado(ROOT, saida)
            arquivos_primeiro = {
                caminho.relative_to(saida).as_posix(): hashlib.sha256(
                    caminho.read_bytes()
                ).hexdigest()
                for caminho in saida.rglob("*")
                if caminho.is_file()
            }
            segundo = gerar_lotes_migracao_legado(ROOT, saida)
            arquivos_segundo = {
                caminho.relative_to(saida).as_posix(): hashlib.sha256(
                    caminho.read_bytes()
                ).hexdigest()
                for caminho in saida.rglob("*")
                if caminho.is_file()
            }

        self.assertEqual(primeiro.totais, segundo.totais)
        self.assertEqual(arquivos_primeiro, arquivos_segundo)

    def test_revisa_individualmente_os_70_jsons_sem_alterar_bancos(self):
        antes = _hashes()
        with tempfile.TemporaryDirectory() as temporario:
            resultado = revisar_lotes_migracao_legado(
                projeto=ROOT,
                saida=Path(temporario) / "lotes",
            )
            relatorio = json.loads(
                resultado.relatorio.read_text(encoding="utf-8")
            )
        depois = _hashes()

        self.assertEqual(antes, depois)
        self.assertEqual(resultado.total_propostas, 70)
        self.assertEqual(
            resultado.classificacoes,
            {
                "valida": 0,
                "pendente": 37,
                "conflitante": 33,
                "rejeitada": 0,
            },
        )
        self.assertEqual(
            len(relatorio["ids_por_classificacao"]["pendente"]),
            37,
        )
        self.assertTrue(
            all(
                proposta.startswith("migracao-legado-conhecimento-")
                for proposta in relatorio["ids_por_classificacao"]["pendente"]
            )
        )
        self.assertTrue(
            all(
                proposta.startswith("migracao-legado-relacao-")
                for proposta in relatorio["ids_por_classificacao"][
                    "conflitante"
                ]
            )
        )
        self.assertEqual(
            relatorio["relacoes_e_referencias"]["linhas_de_relacao"],
            66,
        )
        self.assertEqual(
            relatorio["evidencias_e_proveniencia"]["total_evidencias"],
            217,
        )
        self.assertEqual(
            len(relatorio["exigem_revisao_humana"]),
            70,
        )
        self.assertEqual(relatorio["aptas_para_futura_aplicacao"], [])
        verificacoes = relatorio["verificacoes"]
        self.assertTrue(verificacoes["todos_os_70_jsons_revisados"])
        self.assertTrue(verificacoes["contrato_real_validado"])
        self.assertTrue(verificacoes["dry_run_real_executado"])
        self.assertTrue(verificacoes["determinismo_dos_lotes"])
        self.assertTrue(verificacoes["idempotencia"])
        self.assertEqual(verificacoes["jsons_duplicados_indevidamente"], [])
        self.assertEqual(verificacoes["propostas_duplicadas"], [])
        self.assertEqual(verificacoes["idempotencias_duplicadas"], [])
        self.assertEqual(verificacoes["conflitos_ocultos"], [])
        self.assertTrue(verificacoes["nenhum_conteudo_inventado"])
        self.assertTrue(verificacoes["nenhuma_referencia_fisica_de_destino"])
        self.assertTrue(verificacoes["nenhum_sql_ou_codigo"])

    def test_ledger_rejeitado_usa_o_proposta_id_real(self):
        descricao = {
            "proposta_id": "proposta-real-da-fonte",
            "entrada": "json",
            "idempotencia": "legado:teste:1",
            "objetos": [],
            "evidencias": [],
            "pendencias": ["pendência de teste"],
        }
        with tempfile.TemporaryDirectory() as temporario:
            _, rejeitados = _preparar_lote(
                {"nome-diferente.json": descricao},
                fonte="fonte",
                assunto="assunto",
                lote_id="lote",
                lotes=LotesJSONConhecimento(
                    Path(temporario) / "lotes"
                ),
                ingestao=_Rejeitador(),
            )
            ledger = [
                {
                    "proposta_id": "proposta-real-da-fonte",
                    "status": "pendente",
                    "motivos": ["motivo original"],
                },
                {
                    "proposta_id": "nome-diferente",
                    "status": "pendente",
                    "motivos": ["não deve ser alterado"],
                },
            ]
            _marcar_rejeitados_no_ledger(ledger, rejeitados)

        self.assertEqual(rejeitados[0]["arquivo"], "nome-diferente.json")
        self.assertEqual(
            rejeitados[0]["proposta_id"],
            "proposta-real-da-fonte",
        )
        self.assertEqual(ledger[0]["status"], "rejeitado")
        self.assertIn("rejeição de teste", ledger[0]["motivos"])
        self.assertEqual(ledger[1]["status"], "pendente")


if __name__ == "__main__":
    unittest.main()