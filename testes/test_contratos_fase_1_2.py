"""Testes dos contratos da representação intermediária da Fase 1.2."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.contratos import (
    AlvoSemantico,
    AnaliseMorfologica,
    AnaliseMorfologicaAlternativa,
    ArgumentoSemantico,
    CandidatoLexical,
    ContextoAnalise,
    DependenciaSintatica,
    EntidadeDiscursiva,
    Enunciado,
    EstruturaSintatica,
    HipoteseAnalise,
    IntencaoIntermediaria,
    NoSintatico,
    PredicadoSemantico,
    ProposicaoIntermediaria,
    SpanTexto,
    Token,
)


class TestContratosFase12(unittest.TestCase):
    def test_enunciado_preserva_texto_spans_tokens_e_contexto(self):
        span = SpanTexto(0, 8)
        token = Token("cachorro", span, "cachorro")
        entidade = EntidadeDiscursiva("e1", "animal", (span,))
        contexto = ContextoAnalise("sessao-1", 2, entidades=(entidade,))
        enunciado = Enunciado(
            "Cachorro.",
            "cachorro.",
            "pt-BR",
            spans=(span,),
            tokens=(token,),
            contexto=contexto,
        )

        self.assertEqual(enunciado.texto_original, "Cachorro.")
        self.assertEqual(enunciado.tokens[0].span, span)
        self.assertEqual(enunciado.contexto.turno, 2)

    def test_estado_impossivel_e_span_invertido_sao_rejeitados(self):
        with self.assertRaises(ValueError):
            SpanTexto(4, 2)
        with self.assertRaises(ValueError):
            Enunciado("texto", "texto", "pt-BR", estado_processamento="invalido")

    def test_alternativas_morfologicas_nao_sao_descartadas(self):
        span = SpanTexto(0, 4)
        primeira = AnaliseMorfologica(span, "banco", "banco", "substantivo")
        segunda = AnaliseMorfologica(span, "banco", "bancar", "verbo")
        alternativas = AnaliseMorfologicaAlternativa(span, (primeira, segunda))

        self.assertEqual(len(alternativas.alternativas), 2)
        self.assertEqual(alternativas.alternativas[1].lema, "bancar")

    def test_sintaxe_preserva_nos_dependencias_e_alternativas(self):
        span = SpanTexto(0, 8)
        nos = (
            NoSintatico(1, "sujeito", span),
            NoSintatico(2, "predicado", SpanTexto(9, 17), cabeca_id=1),
        )
        estrutura = EstruturaSintatica(
            nos=nos,
            dependencias=(DependenciaSintatica(2, 1, "sujeito"),),
            alternativas=("leitura A", "leitura B"),
        )

        self.assertEqual(len(estrutura.alternativas), 2)
        self.assertEqual(estrutura.dependencias[0].funcao, "sujeito")

    def test_polaridade_modalidade_e_escopo_sao_preservados(self):
        predicado = PredicadoSemantico(
            "evento", conceito=AlvoSemantico("conceito", "DORMIR")
        )
        proposicao = ProposicaoIntermediaria(
            "p1",
            predicado,
            polaridade="negativa",
            modalidade="epistemica",
            escopo_id="p0",
        )

        self.assertEqual(proposicao.polaridade, "negativa")
        self.assertEqual(proposicao.modalidade, "epistemica")
        self.assertEqual(proposicao.escopo_id, "p0")

    def test_argumentos_e_proveniencia_nao_exigem_sqlite(self):
        predicado = PredicadoSemantico(
            "evento", sentido=AlvoSemantico("sentido", "s1")
        )
        argumento = ArgumentoSemantico(
            "sujeito", AlvoSemantico("entidade", "e1"), 1
        )
        intencao = IntencaoIntermediaria("afirmacao", "informar", confianca=0.8)
        hipotese = HipoteseAnalise("h1", "leitura candidata", 0.7)
        proposicao = ProposicaoIntermediaria(
            "p1", predicado, (argumento,), proposicoes_encaixadas=("p2",)
        )

        self.assertEqual(proposicao.argumentos[0].alvo.tipo, "entidade")
        self.assertEqual(intencao.confianca, 0.8)
        self.assertEqual(hipotese.status, "candidata")


if __name__ == "__main__":
    unittest.main()