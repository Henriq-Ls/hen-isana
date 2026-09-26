"""Testes do primeiro modo sombra observacional da Fase 3.5."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aplicacao.modo_sombra import (
    HistoricoSombra,
    ModoSombra,
    ObservacaoFluxo,
    StatusComparacao,
    processar_frase_em_modo_sombra,
)
from bancos.conhecimento import ConhecimentoDB


class TestModoSombraGenerico(unittest.TestCase):
    def executar(
        self,
        novo,
        legado,
        *,
        historico: HistoricoSombra | None = None,
        entrada: str = "entrada controlada",
    ):
        return ModoSombra(historico).executar(
            entrada,
            novo,
            legado,
            operacao="teste",
            origem="teste_fase_3_5",
        )

    def test_processa_novo_e_legado_e_devolve_somente_o_legado(self):
        chamadas: list[str] = []

        resultado = self.executar(
            lambda _entrada: (
                chamadas.append("novo")
                or ObservacaoFluxo(
                    resultado={"novo": True},
                    representacao={"valor": "comum"},
                )
            ),
            lambda _entrada: (
                chamadas.append("legado")
                or ObservacaoFluxo(
                    resultado={"legado": True},
                    representacao={"valor": "comum"},
                )
            ),
        )

        self.assertEqual(chamadas, ["novo", "legado"])
        self.assertEqual(resultado.resultado, {"legado": True})
        self.assertEqual(resultado.registro.status, StatusComparacao.EQUIVALENTE)
        self.assertTrue(resultado.registro.fallback)

    def test_registra_resultados_diferentes_sem_alterar_o_legado(self):
        legado = {"estado": ["original"]}
        antes = dict(legado)

        resultado = self.executar(
            lambda _entrada: ObservacaoFluxo({"valor": "novo"}),
            lambda _entrada: ObservacaoFluxo(legado),
            entrada="diferença controlada",
        )

        self.assertEqual(resultado.registro.status, StatusComparacao.DIFERENTE)
        self.assertTrue(resultado.registro.diferencas)
        self.assertEqual(legado, antes)
        self.assertEqual(resultado.resultado, {"estado": ["original"]})
        self.assertIn('"valor":"novo"', resultado.registro.resultado_novo)
        self.assertIn('"estado"', resultado.registro.resultado_legado)

    def test_sem_suporte_faz_fallback_explicito(self):
        chamadas = []
        resultado = self.executar(
            lambda _entrada: ObservacaoFluxo(
                {"novo": "não usado"},
                suportado=False,
                completo=False,
                motivo="operação fora do escopo",
            ),
            lambda _entrada: chamadas.append("legado") or ["resposta legada"],
            entrada="operação sem suporte",
        )

        self.assertEqual(chamadas, ["legado"])
        self.assertEqual(resultado.resultado, ["resposta legada"])
        self.assertEqual(resultado.registro.status, StatusComparacao.SEM_SUPORTE)
        self.assertTrue(resultado.registro.fallback)
        self.assertIn("fora do escopo", resultado.registro.diferencas[0])

    def test_falha_do_novo_nao_interrompe_o_legado(self):
        resultado = self.executar(
            lambda _entrada: (_ for _ in ()).throw(RuntimeError("erro novo")),
            lambda _entrada: ["fallback"],
            entrada="falha no novo",
        )

        self.assertEqual(resultado.resultado, ["fallback"])
        self.assertEqual(resultado.registro.status, StatusComparacao.FALHA_NOVO)
        self.assertTrue(resultado.registro.fallback)
        self.assertIn("RuntimeError", resultado.registro.erro_novo or "")

    def test_resultado_incompleto_faz_fallback(self):
        resultado = self.executar(
            lambda _entrada: ObservacaoFluxo(
                {"parcial": True},
                completo=False,
                motivo="faltam campos",
            ),
            lambda _entrada: "legado",
            entrada="resultado incompleto",
        )

        self.assertEqual(resultado.registro.status, StatusComparacao.INCOMPLETO)
        self.assertEqual(resultado.resultado, "legado")
        self.assertTrue(resultado.registro.fallback)

    def test_ambiguidade_faz_fallback_sem_escolher_um_lado(self):
        resultado = self.executar(
            lambda _entrada: ObservacaoFluxo(
                {"candidatos": ("a", "b")},
                ambiguidades=("há duas leituras",),
            ),
            lambda _entrada: {"resposta": "legado"},
            entrada="resultado ambíguo",
        )

        self.assertEqual(resultado.registro.status, StatusComparacao.AMBIGUO)
        self.assertEqual(resultado.resultado, {"resposta": "legado"})
        self.assertTrue(resultado.registro.fallback)

    def test_comparacao_e_idempotente(self):
        historico = HistoricoSombra()
        novo = lambda _entrada: {"mesmo": True}
        legado = lambda _entrada: {"mesmo": True}

        primeira = self.executar(
            novo,
            legado,
            historico=historico,
            entrada="idempotente",
        )
        segunda = self.executar(
            novo,
            legado,
            historico=historico,
            entrada="idempotente",
        )

        self.assertEqual(primeira.registro, segunda.registro)
        self.assertEqual(historico.listar(), (primeira.registro,))

    def test_nova_saida_deterministica_preserva_ordem_canonica(self):
        resultado = self.executar(
            lambda _entrada: {"b": 2, "a": 1},
            lambda _entrada: {"a": 1, "b": 2},
            entrada="ordem",
        )

        self.assertEqual(resultado.registro.status, StatusComparacao.EQUIVALENTE)

    def test_falha_do_legado_e_registrada_e_propagada(self):
        historico = HistoricoSombra()
        with self.assertRaises(LookupError):
            self.executar(
                lambda _entrada: {"novo": True},
                lambda _entrada: (_ for _ in ()).throw(
                    LookupError("legado indisponível")
                ),
                historico=historico,
                entrada="falha legado",
            )

        registro = historico.listar()[0]
        self.assertEqual(registro.status, StatusComparacao.FALHA_LEGADO)
        self.assertFalse(registro.fallback)
        self.assertIn("LookupError", registro.erro_legado or "")


class TestIntegracaoLexicalDoModoSombra(unittest.TestCase):
    def test_compara_nucleo_novo_com_tokenizacao_legada(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            resultado = processar_frase_em_modo_sombra(
                "Ana viu o livro.",
                banco,
                modo_aprendizagem=False,
                projeto_dir=Path(pasta),
            )
            banco.fechar()

        self.assertEqual(resultado.registro.operacao, "analise_lexica")
        self.assertIn(
            resultado.registro.status,
            {
                StatusComparacao.EQUIVALENTE.value,
                StatusComparacao.DIFERENTE.value,
            },
        )
        self.assertTrue(resultado.registro.fallback)
        self.assertIsInstance(resultado.resultado, list)

    def test_intencao_operacional_fica_no_legado(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            resultado = processar_frase_em_modo_sombra(
                "que horas são",
                banco,
                modo_aprendizagem=False,
                projeto_dir=Path(pasta),
            )
            banco.fechar()

        self.assertEqual(resultado.registro.status, StatusComparacao.SEM_SUPORTE.value)
        self.assertTrue(resultado.registro.fallback)
        self.assertIsInstance(resultado.resultado, list)

    def test_modo_sombra_nao_escreve_no_banco_ou_schema(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "conhecimento.db"
            banco = ConhecimentoDB(caminho)
            banco.fechar()
            antes = sha256(caminho.read_bytes()).hexdigest()

            banco = ConhecimentoDB(caminho)
            processar_frase_em_modo_sombra(
                "Ana viu o livro.",
                banco,
                modo_aprendizagem=False,
                projeto_dir=Path(pasta),
            )
            banco.fechar()
            depois = sha256(caminho.read_bytes()).hexdigest()

        self.assertEqual(antes, depois)


if __name__ == "__main__":
    unittest.main()