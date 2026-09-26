import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.roteador import Categoria, Destino, Intencao, rotear


class TestRoteador(unittest.TestCase):
    def test_reconhece_expressao_de_saudacao(self):
        resultado = rotear("Bom dia, tudo bem?")

        self.assertEqual(resultado.categoria, Categoria.PERGUNTA)
        self.assertEqual(resultado.destino, Destino.INTERACAO)

    def test_reconhece_ordem(self):
        resultado = rotear("crie uma classe nova")

        self.assertEqual(resultado.categoria, Categoria.ORDEM)
        self.assertEqual(resultado.destino, Destino.INTERACAO)

    def test_encaminha_informacao_para_conhecimento(self):
        resultado = rotear("manga é uma fruta")

        self.assertEqual(resultado.categoria, Categoria.INFORMACAO)
        self.assertEqual(resultado.destino, Destino.CONHECIMENTO)

    def test_termo_desconhecido_entra_em_aprendizagem(self):
        resultado = rotear("zorpel")

        self.assertEqual(resultado.categoria, Categoria.DESCONHECIDO)
        self.assertEqual(resultado.destino, Destino.APRENDIZAGEM)

    def test_tipo_informado_tem_precedencia(self):
        resultado = rotear("qualquer entrada", tipo="informacao")

        self.assertEqual(resultado.categoria, Categoria.INFORMACAO)
        self.assertEqual(resultado.destino, Destino.CONHECIMENTO)

    def test_rejeita_entrada_que_nao_e_texto(self):
        with self.assertRaises(TypeError):
            rotear(None)  # type: ignore[arg-type]

    def test_reconhece_consulta_de_hora_com_contexto_diferente(self):
        resultado = rotear("quero saber quantas horas?")

        self.assertEqual(resultado.intencao, Intencao.CONSULTAR_HORA)
        self.assertEqual(resultado.categoria, Categoria.PERGUNTA)
        self.assertEqual(resultado.destino, Destino.INTERACAO)

    def test_reconhece_variantes_de_consulta_de_hora_sem_acento(self):
        frases = (
            "Me diz as horas",
            "Você sabe me informar o horário?",
            "qual é a hora atual",
        )

        for frase in frases:
            with self.subTest(frase=frase):
                self.assertEqual(
                    rotear(frase).intencao,
                    Intencao.CONSULTAR_HORA,
                )

    def test_reconhece_consulta_de_hora_depois_de_prefixo_conversacional(self):
        resultado = rotear("ola mano quantas horas?")

        self.assertEqual(resultado.intencao, Intencao.CONSULTAR_HORA)

    def test_reconhece_abreviacao_de_consulta_de_hora(self):
        resultado = rotear("qt horas")

        self.assertEqual(resultado.intencao, Intencao.CONSULTAR_HORA)

    def test_reconhece_saudacao_composta_com_pontuacao(self):
        resultado = rotear("Olá, bom dia!")

        self.assertEqual(resultado.intencao, Intencao.RESPONDER_SAUDACAO)
        self.assertEqual(resultado.categoria, Categoria.SAUDACAO)

    def test_reconhece_pergunta_social_de_estado(self):
        resultado = rotear("Como você está?")

        self.assertEqual(
            resultado.intencao,
            Intencao.PERGUNTAR_ESTADO_SOCIAL,
        )

    def test_reconhece_pergunta_de_nome_apos_apresentacao(self):
        resultado = rotear("Meu nome é Carlos. Qual é o seu nome?")

        self.assertEqual(resultado.intencao, Intencao.PERGUNTAR_NOME)

    def test_reconhece_despedida_real(self):
        resultado = rotear("Até logo!")

        self.assertEqual(resultado.intencao, Intencao.DESPEDIDA)
