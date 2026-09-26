"""Testes comportamentais da inferência simbólica da Fase 3.4."""

from __future__ import annotations

import hashlib
from pathlib import Path
import sqlite3
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.inferencia_simbolica import (  # noqa: E402
    AfirmacaoSimbolica,
    LiteralSimbolico,
    MotorInferenciaSimbolica,
    RegraSimbolica,
)


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "aprendizado" / "bancos" / "linguagem.db"


def afirmacao(
    chave: str,
    *,
    polaridade: str = "positiva",
    estado: str = "confirmada",
    origem: str = "usuario",
    evidencias: tuple[str, ...] = ("ev-p",),
) -> AfirmacaoSimbolica:
    return AfirmacaoSimbolica(
        LiteralSimbolico(chave, polaridade),
        estado=estado,
        origem=origem,
        evidencia_ids=evidencias,
    )


def regra(
    regra_id: str,
    antecedente: str,
    consequente: str,
    *,
    consequente_polaridade: str = "positiva",
) -> RegraSimbolica:
    return RegraSimbolica(
        regra_id,
        LiteralSimbolico(antecedente),
        LiteralSimbolico(consequente, consequente_polaridade),
        evidencia_ids=(f"regra-{regra_id}",),
    )


class TestInferenciaSimbolicaFase34(unittest.TestCase):
    def test_regra_simples_com_premissa_produz_conclusao(self):
        resultado = MotorInferenciaSimbolica(
            (regra("r-p-q", "p", "q"),)
        ).inferir((afirmacao("p"),))

        self.assertEqual(len(resultado.inferencias), 1)
        self.assertEqual(resultado.conclusoes[0].chave, "q")
        self.assertEqual(resultado.conclusoes[0].estado, "inferida")

    def test_premissa_ausente_nao_produz_conclusao(self):
        resultado = MotorInferenciaSimbolica(
            (regra("r-p-q", "p", "q"),)
        ).inferir(())

        self.assertEqual(resultado.inferencias, ())
        self.assertEqual(resultado.bloqueios[0].motivo, "premissa ausente")

    def test_premissa_negativa_bloqueia_conclusao_incompativel(self):
        resultado = MotorInferenciaSimbolica(
            (regra("r-p-q", "p", "q"),)
        ).inferir((afirmacao("p", polaridade="negativa"),))

        self.assertEqual(resultado.inferencias, ())
        self.assertEqual(resultado.bloqueios[0].motivo, "premissa negada")

    def test_inferencia_encadeada_preserva_a_derivacao_anterior(self):
        motor = MotorInferenciaSimbolica(
            (
                regra("r-p-q", "p", "q"),
                regra("r-q-r", "q", "r"),
            )
        )
        resultado = motor.inferir((afirmacao("p"),))

        conclusoes = {conclusao.chave for conclusao in resultado.conclusoes}
        self.assertEqual(conclusoes, {"q", "r"})
        inferencia_r = next(
            item for item in resultado.inferencias
            if item.conclusao.chave == "r"
        )
        self.assertEqual(inferencia_r.premissas[0].chave, "q")
        self.assertEqual(inferencia_r.premissas[0].origem, "inferencia")
        self.assertIsNotNone(inferencia_r.premissas[0].referencia)

    def test_repeticao_e_idempotente(self):
        motor = MotorInferenciaSimbolica((regra("r-p-q", "p", "q"),))
        fatos = (afirmacao("p"), afirmacao("p"))

        primeira = motor.inferir(fatos)
        segunda = motor.inferir(fatos)

        self.assertEqual(primeira, segunda)
        self.assertEqual(len(primeira.inferencias), 1)

    def test_premissas_e_evidencias_sao_preservadas(self):
        premissa = afirmacao("p", evidencias=("ev-usuario", "ev-fonte"))
        resultado = MotorInferenciaSimbolica(
            (regra("r-p-q", "p", "q"),)
        ).inferir((premissa,))

        inferencia = resultado.inferencias[0]
        self.assertEqual(inferencia.premissas, (premissa,))
        self.assertEqual(
            inferencia.conclusao.evidencia_ids,
            ("ev-usuario", "ev-fonte", "regra-r-p-q"),
        )
        self.assertEqual(inferencia.origem_regra, "sistema")

    def test_conclusao_tem_proveniencia_de_inferencia(self):
        resultado = MotorInferenciaSimbolica(
            (regra("r-p-q", "p", "q"),)
        ).inferir((afirmacao("p"),))

        conclusao = resultado.conclusoes[0]
        self.assertEqual(conclusao.origem, "inferencia")
        self.assertEqual(conclusao.referencia, "inferencia:r-p-q:q:positiva")
        self.assertNotEqual(conclusao.origem, "usuario")

    def test_conflito_e_preservado_sem_resolucao_automatica(self):
        resultado = MotorInferenciaSimbolica(
            (regra("r-p-q", "p", "q"),)
        ).inferir(
            (
                afirmacao("p"),
                afirmacao("p", polaridade="negativa"),
            )
        )

        self.assertEqual(len(resultado.conflitos), 1)
        self.assertFalse(resultado.conflitos[0].resolvido)
        self.assertEqual(resultado.resolucoes_de_conflito, ())
        self.assertEqual(resultado.inferencias, ())
        self.assertEqual(
            {item.polaridade for item in resultado.conflitos[0].afirmacoes},
            {"positiva", "negativa"},
        )

    def test_incerteza_nao_vira_certeza(self):
        resultado = MotorInferenciaSimbolica(
            (regra("r-p-q", "p", "q"),)
        ).inferir((afirmacao("p", estado="incerta"),))

        inferencia = resultado.inferencias[0]
        self.assertEqual(inferencia.estado, "incerta")
        self.assertEqual(inferencia.conclusao.estado, "incerta")
        self.assertEqual(inferencia.incertezas, ("premissa incerta",))
        self.assertEqual(inferencia.conclusao.origem, "inferencia")

    def test_conclusao_com_conflito_nao_e_apresentada_como_resolvida(self):
        motor = MotorInferenciaSimbolica(
            (
                regra("r-p-q", "p", "q"),
                regra("r-np-nq", "p", "q", consequente_polaridade="negativa"),
            )
        )
        resultado = motor.inferir(
            (
                afirmacao("p"),
                afirmacao("p", polaridade="negativa"),
            )
        )

        self.assertEqual(resultado.inferencias, ())
        self.assertTrue(all(not conflito.resolvido for conflito in resultado.conflitos))

    def test_motor_nao_modifica_o_banco_linguistico(self):
        antes = hashlib.sha256(DB.read_bytes()).hexdigest()
        MotorInferenciaSimbolica((regra("r-p-q", "p", "q"),)).inferir(
            (afirmacao("p"),)
        )
        depois = hashlib.sha256(DB.read_bytes()).hexdigest()

        self.assertEqual(antes, depois)
        with sqlite3.connect(DB) as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])

    def test_texto_recebido_e_tratado_como_dado(self):
        chave = "__import__('os').system('não executar')"
        resultado = MotorInferenciaSimbolica(
            (regra("r-dado", chave, "q"),)
        ).inferir((afirmacao(chave),))

        self.assertEqual(resultado.conclusoes[0].chave, "q")

    def test_erro_de_entrada_nao_deixa_resultado_parcial(self):
        motor = MotorInferenciaSimbolica((regra("r-p-q", "p", "q"),))

        def entradas():
            yield afirmacao("p")
            yield object()

        with self.assertRaises(TypeError):
            motor.inferir(entradas())
        self.assertEqual(motor.inferir(()).inferencias, ())

    def test_regra_auto_referente_e_repeticao_de_id_sao_rejeitadas(self):
        with self.assertRaises(ValueError):
            regra("r-invalida", "p", "p")
        with self.assertRaises(ValueError):
            MotorInferenciaSimbolica(
                (
                    regra("r-p-q", "p", "q"),
                    regra("r-p-q", "p", "r"),
                )
            )


if __name__ == "__main__":
    unittest.main()