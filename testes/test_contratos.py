"""Testes dos contratos de transporte entre camadas simbólicas."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.contratos import (
    CampoRecuperado,
    EvidenciaUsada,
    Interpretacao,
    ItemInterpretado,
    ReferenciaRegistro,
    ReferenciaTurno,
    ResultadoResposta,
    ResultadoRecuperacao,
)


class TestContratoInterpretacao(unittest.TestCase):
    def test_aceita_interpretacao_estruturada_sem_dependencia_de_runtime(self):
        resultado = Interpretacao(
            intencao="consulta_conhecimento",
            expressao_candidata="licença",
            entidades=(ItemInterpretado("termo", "licença"),),
            slots=(ItemInterpretado("campo", "significado"),),
            referencias_turnos=(ReferenciaTurno(1, "isso", "licença"),),
            confianca=0.82,
        )

        self.assertEqual(resultado.intencao, "consulta_conhecimento")
        self.assertEqual(resultado.entidades[0].valor, "licença")
        self.assertEqual(resultado.referencias_turnos[0].turno, 1)

    def test_confianca_fora_da_faixa_e_rejeitada(self):
        for valor in (-0.01, 1.01, True):
            with self.subTest(valor=valor):
                with self.assertRaises(ValueError):
                    Interpretacao("consulta", confianca=valor)

    def test_referencia_nao_pode_apontar_para_turno_invalido(self):
        with self.assertRaises(ValueError):
            ReferenciaTurno(0, "isso")

    def test_campos_coletivos_exigem_tuplas_imutaveis(self):
        with self.assertRaises(TypeError):
            Interpretacao("consulta", entidades=[ItemInterpretado("x", "y")])


class TestContratoRecuperacao(unittest.TestCase):
    def test_preserva_origem_confirmacao_e_contexto_do_campo(self):
        registro = ReferenciaRegistro("conhecimento", 7)
        campo = CampoRecuperado(
            registro=registro,
            nome="significado",
            valor="Pedido educado de passagem.",
            origem="usuario",
            estado_confirmacao="confirmada",
            evidencia_ids=(19,),
            contexto="Ao passar por alguém.",
        )
        resultado = ResultadoRecuperacao(
            candidatos=(registro,),
            campos=(campo,),
            contexto_relevante=("pedido de passagem",),
        )

        self.assertEqual(resultado.candidatos, (registro,))
        self.assertEqual(resultado.campos[0].origem, "usuario")
        self.assertEqual(resultado.campos[0].estado_confirmacao, "confirmada")

    def test_rejeita_campo_fora_dos_candidatos(self):
        campo = CampoRecuperado(
            registro=ReferenciaRegistro("conhecimento", 8),
            nome="significado",
            valor="valor",
            origem="usuario",
            estado_confirmacao="confirmada",
        )
        with self.assertRaises(ValueError):
            ResultadoRecuperacao(
                candidatos=(ReferenciaRegistro("conhecimento", 7),),
                campos=(campo,),
            )

    def test_ids_de_evidencia_devem_ser_positivos(self):
        with self.assertRaises(ValueError):
            CampoRecuperado(
                registro=ReferenciaRegistro("conhecimento", 7),
                nome="significado",
                valor="valor",
                origem="usuario",
                estado_confirmacao="confirmada",
                evidencia_ids=(0,),
            )


class TestContratoResposta(unittest.TestCase):
    def test_resposta_expõe_evidencias_e_incertezas(self):
        resposta = ResultadoResposta(
            texto="Preciso de mais contexto para responder.",
            evidencias_usadas=(
                EvidenciaUsada(
                    ReferenciaRegistro("conhecimento", 7),
                    "significado",
                    (19,),
                ),
            ),
            incertezas=("O contexto da pergunta está ambíguo.",),
            requer_esclarecimento=True,
        )

        self.assertTrue(resposta.requer_esclarecimento)
        self.assertEqual(resposta.evidencias_usadas[0].evidencia_ids, (19,))
        self.assertEqual(len(resposta.incertezas), 1)

    def test_evidencia_usada_precisa_referenciar_fonte(self):
        with self.assertRaises(ValueError):
            EvidenciaUsada(
                ReferenciaRegistro("conhecimento", 7),
                "significado",
                (),
            )


if __name__ == "__main__":
    unittest.main()