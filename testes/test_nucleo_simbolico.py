"""Testes da Parte 2: léxico, parser, semântica e referências."""

from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.contratos import ContextoAnalise, EntidadeDiscursiva, SpanTexto
from core.nucleo_simbolico import (
    analisar_morfologia,
    parsear,
    representar_semantica,
    resolver_referencias,
    tokenizar_enunciado,
)


class TestFase21LexicoMorfologia(unittest.TestCase):
    def test_preserva_spans_e_identifica_desconhecida(self):
        resultado = tokenizar_enunciado("Cães correm.")

        self.assertEqual(resultado.enunciado.tokens[0].span, SpanTexto(0, 4))
        self.assertIn("cães", resultado.desconhecidos)
        self.assertEqual(resultado.enunciado.tokens[-1].pontuacao, ".")

    def test_preserva_candidatos_e_ambiguidade_morfologica(self):
        resultado = tokenizar_enunciado("banco")
        alternativas = analisar_morfologia(resultado)

        self.assertGreaterEqual(len(alternativas[0].alternativas), 2)
        self.assertEqual(alternativas[0].alternativas[0].forma, "banco")


class TestFase22Parser(unittest.TestCase):
    def test_produz_sujeito_verbo_objeto(self):
        lexical = tokenizar_enunciado("Ana viu o livro.")
        morfologia = analisar_morfologia(lexical)
        parser = parsear(lexical, morfologia)
        funcoes = {dependencia.funcao for dependencia in parser.estruturas[0].dependencias}

        self.assertEqual(len(parser.estruturas), 1)
        self.assertEqual(funcoes, {"sujeito", "objeto"})

    def test_preserva_estruturas_para_dois_verbos(self):
        lexical = tokenizar_enunciado("Ana pode estudar.")
        parser = parsear(lexical, analisar_morfologia(lexical))

        self.assertGreaterEqual(len(parser.estruturas), 2)


class TestFase23Semantica(unittest.TestCase):
    def test_produz_proposicao_sem_criar_fato(self):
        lexical = tokenizar_enunciado("Ana não dorme.")
        parser = parsear(lexical, analisar_morfologia(lexical))
        semantica = representar_semantica(lexical, parser)

        self.assertEqual(len(semantica.proposicoes), 1)
        self.assertEqual(semantica.proposicoes[0].polaridade, "negativa")
        self.assertFalse(hasattr(semantica.proposicoes[0], "fato"))

    def test_modalidade_e_argumentos_sao_estruturados(self):
        lexical = tokenizar_enunciado("Talvez Ana leia.")
        parser = parsear(lexical, analisar_morfologia(lexical))
        semantica = representar_semantica(lexical, parser)

        self.assertEqual(semantica.proposicoes[0].modalidade, "epistemica")
        self.assertEqual(semantica.proposicoes[0].argumentos[0].papel, "sujeito")


class TestFase24Referencias(unittest.TestCase):
    def test_resolve_pronome_com_uma_entidade_em_memoria(self):
        entidade = EntidadeDiscursiva("e1", "pessoa", (SpanTexto(0, 3),))
        contexto = ContextoAnalise("sessao", 2, entidades=(entidade,))
        resultado = resolver_referencias(tokenizar_enunciado("Ela chegou."), contexto)

        self.assertTrue(resultado.resolucoes[0].resolvida)
        self.assertEqual(resultado.resolucoes[0].entidade_id, "e1")
        self.assertEqual(resultado.contexto_atual.referencias[0].alvo, "e1")

    def test_preserva_ambiguidade_sem_persistir_contexto(self):
        entidades = (
            EntidadeDiscursiva("e1", "pessoa", (SpanTexto(0, 3),)),
            EntidadeDiscursiva("e2", "pessoa", (SpanTexto(4, 7),)),
        )
        contexto = ContextoAnalise("sessao", 2, entidades=entidades)
        resultado = resolver_referencias(tokenizar_enunciado("Ela chegou."), contexto)

        self.assertTrue(resultado.resolucoes[0].ambigua)
        self.assertIn("referência ambígua: Ela", resultado.pendencias)


if __name__ == "__main__":
    unittest.main()