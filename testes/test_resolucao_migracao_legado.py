"""Testes da resolução semântica conservadora da Fase 3.7."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from aplicacao.migracao_legado_json import (
    resolver_revisao_lotes_migracao_legado,
)


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


class TestResolucaoMigracaoLegado(unittest.TestCase):
    def test_resolve_todas_sem_inventar_objetos_e_preserva_bancos(self):
        antes = _hashes()
        with tempfile.TemporaryDirectory() as temporario:
            saida = Path(temporario) / "lotes"
            relatorio_path = Path(temporario) / "resolucao.json"
            resultado = resolver_revisao_lotes_migracao_legado(
                ROOT,
                saida_candidata=saida,
                relatorio=relatorio_path,
            )
            relatorio = json.loads(
                relatorio_path.read_text(encoding="utf-8")
            )
            arquivos = sorted(saida.rglob("propostas/*.json"))
            payloads = [
                json.loads(arquivo.read_text(encoding="utf-8"))
                for arquivo in arquivos
            ]
        depois = _hashes()

        self.assertEqual(antes, depois)
        self.assertTrue(resultado.hashes_bancos_inalterados)
        self.assertEqual(relatorio["total_propostas"], 70)
        self.assertEqual(
            relatorio["classificacoes"],
            {
                "apta": 0,
                "pendente": 37,
                "conflitante": 33,
                "rejeitada": 0,
            },
        )
        self.assertEqual(len(arquivos), 70)
        self.assertTrue(
            all(not payload["objetos"] for payload in payloads)
        )
        self.assertTrue(
            all(
                not proposta["objeto_semantico_gerado"]
                for proposta in relatorio["propostas"]
            )
        )
        self.assertTrue(
            relatorio["verificacoes"]["nenhum_objeto_semantico_inventado"]
        )
        self.assertTrue(
            relatorio["verificacoes"]["dry_run_real_em_todas_as_propostas"]
        )
        self.assertTrue(
            relatorio["verificacoes"]["sem_registro_autorizacao_aplicacao"]
        )

    def test_resposta_padrao_e_evidencias_tem_tratamento_explicito(self):
        with tempfile.TemporaryDirectory() as temporario:
            relatorio_path = Path(temporario) / "resolucao.json"
            resolver_revisao_lotes_migracao_legado(
                ROOT,
                saida_candidata=Path(temporario) / "lotes",
                relatorio=relatorio_path,
            )
            relatorio = json.loads(
                relatorio_path.read_text(encoding="utf-8")
            )

        propostas = {
            item["proposta_id"]: item for item in relatorio["propostas"]
        }
        conhecimento = [
            propostas[f"migracao-legado-conhecimento-{indice}"]
            for indice in range(1, 38)
        ]
        com_valor = [
            item
            for item in conhecimento
            if item["resposta_padrao"]["estado"] == "presente"
        ]
        ausentes = [
            item
            for item in conhecimento
            if item["resposta_padrao"]["estado"] == "ausente"
        ]

        self.assertEqual(relatorio["resposta_padrao"]["com_valor"], 32)
        self.assertEqual(relatorio["resposta_padrao"]["ausente"], 5)
        self.assertEqual(len(com_valor), 32)
        self.assertEqual(len(ausentes), 5)
        self.assertTrue(
            all(
                item["resposta_padrao"]["tratamento"]
                == "sem_correspondencia_preservada_em_evidencia"
                for item in com_valor
            )
        )
        self.assertTrue(
            all(
                any(
                    campo["campo"] == "resposta_padrao"
                    for campo in item["campos_descartados"]
                )
                for item in conhecimento
            )
        )
        self.assertEqual(
            relatorio["evidencias_proveniencia"][
                "total_evidencias_preservadas"
            ],
            217,
        )
        self.assertTrue(
            relatorio["evidencias_proveniencia"][
                "origens_ou_estados_nao_reescritos"
            ]
        )

    def test_referencias_objetivas_ficam_no_escopo_legado(self):
        with tempfile.TemporaryDirectory() as temporario:
            relatorio_path = Path(temporario) / "resolucao.json"
            resolver_revisao_lotes_migracao_legado(
                ROOT,
                saida_candidata=Path(temporario) / "lotes",
                relatorio=relatorio_path,
            )
            relatorio = json.loads(
                relatorio_path.read_text(encoding="utf-8")
            )

        propostas = {
            item["proposta_id"]: item for item in relatorio["propostas"]
        }
        primeiro = propostas["migracao-legado-conhecimento-1"]
        self.assertIn(
            {
                "escopo": "somente_identidade_legada",
                "registro_legado_id": 2,
                "valor_legado": "oi",
            },
            primeiro["referencias_resolvidas"],
        )
        self.assertTrue(primeiro["referencias_pendentes"])
        self.assertEqual(
            relatorio["relacoes"]["com_direcao_comprovada"],
            [],
        )
        relacoes = [
            item
            for item in relatorio["propostas"]
            if item["proposta_id"].startswith("migracao-legado-relacao-")
        ]
        self.assertEqual(len(relacoes), 33)
        self.assertTrue(
            all(
                not item["direcao_comprovada"]
                and not item["ordem_comprovada"]
                for item in relacoes
            )
        )
        self.assertTrue(
            all(item["eventuais_conflitos"] for item in relacoes)
        )

    def test_resolucao_e_idempotente(self):
        with tempfile.TemporaryDirectory() as temporario:
            saida = Path(temporario) / "lotes"
            relatorio_path = Path(temporario) / "resolucao.json"
            primeira = resolver_revisao_lotes_migracao_legado(
                ROOT,
                saida_candidata=saida,
                relatorio=relatorio_path,
            )
            arquivos_primeiros = {
                caminho.relative_to(saida).as_posix(): hashlib.sha256(
                    caminho.read_bytes()
                ).hexdigest()
                for caminho in saida.rglob("*")
                if caminho.is_file()
            }
            segunda = resolver_revisao_lotes_migracao_legado(
                ROOT,
                saida_candidata=saida,
                relatorio=relatorio_path,
            )
            arquivos_segundos = {
                caminho.relative_to(saida).as_posix(): hashlib.sha256(
                    caminho.read_bytes()
                ).hexdigest()
                for caminho in saida.rglob("*")
                if caminho.is_file()
            }

        self.assertEqual(primeira.classificacoes, segunda.classificacoes)
        self.assertEqual(arquivos_primeiros, arquivos_segundos)


if __name__ == "__main__":
    unittest.main()