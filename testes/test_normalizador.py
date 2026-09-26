import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.normalizador import (
    normalizar_frase,
    normalizar_termo_chave,
    normalizar_termo_estrito,
)


class TestNormalizadorDeTermos(unittest.TestCase):
    def test_normaliza_caixa_acentos_unicode_pontuacao_e_espacos(self):
        self.assertEqual(normalizar_termo_chave("  OLÁ!!! "), "ola")
        self.assertEqual(normalizar_termo_chave("o\u0301la"), "ola")
        self.assertEqual(normalizar_termo_chave("até-logo?"), "ate logo")
        self.assertEqual(normalizar_termo_chave("BOM   DIA"), "bom dia")

    def test_preserva_acento_em_pares_semanticos(self):
        for sem_acento, com_acento in (
            ("por", "pôr"),
            ("esta", "está"),
            ("sabia", "sábia"),
        ):
            with self.subTest(sem_acento=sem_acento):
                self.assertNotEqual(
                    normalizar_termo_chave(sem_acento),
                    normalizar_termo_chave(com_acento),
                )

    def test_chave_automatica_para_ola_e_ola_com_acento(self):
        self.assertEqual(
            normalizar_termo_chave("ola"),
            normalizar_termo_chave("olá"),
        )

    def test_frase_preserva_pontuacao_enquanto_a_chave_a_ignora(self):
        original = "Olá, bom dia!"

        self.assertEqual(normalizar_frase(original), "olá, bom dia!")
        self.assertEqual(normalizar_termo_chave(original), "ola bom dia")

    def test_normalizacao_estrita_preserva_distincao_de_acento(self):
        self.assertNotEqual(
            normalizar_termo_estrito("cafe"),
            normalizar_termo_estrito("café"),
        )