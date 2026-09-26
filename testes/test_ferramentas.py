import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import tempfile


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from ferramentas.internet import (  # noqa: E402
    ConsultaInternetError,
    DefinicaoInternet,
    ResultadoInternet,
    _validar_url,
    texto_visivel,
)
from ferramentas.sistema import consultar_data_hora  # noqa: E402
from bancos.conhecimento import ConhecimentoDB  # noqa: E402
from main import aprender_termo, processar_frase  # noqa: E402
from protocolo.regras import ALVO_CONHECIMENTO, TipoAcao  # noqa: E402
from protocolo.verificador import (  # noqa: E402
    emitir_permissao,
    verificar_acao,
)


def permissao_memoria():
    return emitir_permissao(
        TipoAcao.SALVAR_CONHECIMENTO,
        ALVO_CONHECIMENTO,
    )


class TestFerramentasSistema(unittest.TestCase):
    def test_consulta_data_hora_usa_fuso_solicitado(self):
        leitura = consultar_data_hora("America/Sao_Paulo")

        self.assertEqual(leitura.nome_fuso, "America/Sao_Paulo")
        self.assertRegex(leitura.hora, r"^\d{2}:\d{2}:\d{2}$")
        self.assertIn(" de ", leitura.data_extensa)

    def test_protocolo_autoriza_apenas_alvo_de_data_hora(self):
        self.assertTrue(
            verificar_acao(
                TipoAcao.CONSULTAR_SISTEMA,
                "sistema/data_hora",
            ).permitida
        )
        self.assertFalse(
            verificar_acao(
                TipoAcao.CONSULTAR_SISTEMA,
                "core/segredo",
            ).permitida
        )

    def test_pergunta_de_hora_nao_vai_para_aprendizagem(self):
        respostas = processar_frase("que horas são", None)  # type: ignore[arg-type]

        self.assertEqual(len(respostas), 1)
        self.assertIn("Agora são", respostas[0])

    def test_definicao_online_pode_ser_aceita_sem_pular_os_outros_campos(self):
        definicao = DefinicaoInternet(
            termo="biblioteca",
            titulo="Biblioteca",
            resumo="Lugar onde livros e outros materiais são organizados.",
            url="https://pt.wikipedia.org/wiki/Biblioteca",
        )
        respostas = iter(
            [
                "sim",
                "Uma biblioteca organiza livros para consulta.",
            ]
        )
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            with patch("main.consultar_definicao", return_value=definicao):
                entrada = aprender_termo(
                    "biblioteca",
                    banco,
                    perguntar=lambda _mensagem: next(respostas),
                    usar_internet=True,
                    permissao_memoria=permissao_memoria(),
                )
            self.assertEqual(entrada.significado, definicao.resumo)
            self.assertEqual(
                entrada.exemplo_uso,
                "Uma biblioteca organiza livros para consulta.",
            )
            banco.fechar()


class TestFerramentaInternet(unittest.TestCase):
    def test_bloqueia_host_local_e_porta_customizada(self):
        with self.assertRaises(ConsultaInternetError):
            _validar_url("http://localhost:5000/segredo")
        with self.assertRaises(ConsultaInternetError):
            _validar_url("https://example.com:8443/")

    def test_extrai_texto_de_html_e_limita_tamanho(self):
        resultado = ResultadoInternet(
            "https://example.com",
            200,
            "text/html",
            "<html><script>oculto</script><h1>Olá</h1><p>Mundo</p></html>",
        )

        self.assertEqual(texto_visivel(resultado), "Olá Mundo")

    def test_protocolo_autoriza_alvo_de_internet(self):
        self.assertTrue(
            verificar_acao(
                TipoAcao.CONSULTAR_INTERNET,
                "internet/consulta",
            ).permitida
        )
        self.assertFalse(
            verificar_acao(
                TipoAcao.CONSULTAR_INTERNET,
                "internet/arquivo",
            ).permitida
        )