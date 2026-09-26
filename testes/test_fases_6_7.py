import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bancos.conhecimento import ConhecimentoDB, EntradaConhecimento
from core.composicao_resposta import compor_resposta_dinamica
from core.interpretacao import interpretar_pergunta
from core.perguntas import gerar_pergunta_adaptativa
from core.roteador import Intencao, rotear
from core.validador import validar_sintaxe
from ferramentas.busca import buscar_conhecimento_confirmado
from main import processar_frase
from protocolo.regras import ALVO_CONHECIMENTO, TipoAcao
from protocolo.verificador import emitir_permissao, validar_codigo_gerado


class TestFasesSeisESete(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.projeto = Path(self.pasta.name)
        self.banco = ConhecimentoDB(self.projeto / "conhecimento.db")

    def tearDown(self):
        self.banco.fechar()
        self.pasta.cleanup()

    @staticmethod
    def _permissao_memoria():
        return emitir_permissao(
            TipoAcao.SALVAR_CONHECIMENTO,
            ALVO_CONHECIMENTO,
        )

    def test_aprendizagem_de_termo_com_categoria_nao_gera_codigo(self):
        termo = EntradaConhecimento(
            id=1,
            termo="termo de teste",
            tipo="categoria executável",
            significado="Um conceito armazenado como dado.",
            contexto_uso="No teste de separação entre dados e código.",
            resposta_padrao=None,
            relacionados=None,
            exemplo_uso="O termo de teste permanece no SQLite.",
        )

        with patch("main.aprender_termo", return_value=termo):
            processar_frase(
                "termo de teste",
                self.banco,
                projeto_dir=self.projeto,
                modo_aprendizagem=True,
            )

        pasta_gerada = self.projeto / "aprendizado" / "gerado"
        self.assertFalse(pasta_gerada.exists())
        self.assertEqual(list(self.projeto.rglob("*.py")), [])

    def test_conversa_desconhecida_nao_escreve_sqlite_ou_gera_codigo(self):
        alteracoes_antes = self.banco.conn.total_changes

        resposta = processar_frase(
            "assunto desconhecido",
            self.banco,
            projeto_dir=self.projeto,
            modo_aprendizagem=False,
        )

        self.assertTrue(any("Ainda não sei" in item for item in resposta))
        self.assertEqual(self.banco.conn.total_changes, alteracoes_antes)
        self.assertEqual(self.banco.buscar_termo("assunto"), [])
        self.assertFalse(
            (self.projeto / "aprendizado" / "gerado").exists()
        )

    def test_interfaces_simbolicas_estao_separadas_e_utilizaveis(self):
        self.assertEqual(
            interpretar_pergunta("O que significa semântica?"),
            ("significado", "semântica"),
        )
        self.assertIn(
            "significa",
            gerar_pergunta_adaptativa("semântica", "significado"),
        )
        self.assertEqual(
            rotear("Que horas são?").intencao,
            Intencao.CONSULTAR_HORA,
        )
        self.assertTrue(validar_sintaxe("def ferramenta():\n    return 1\n").valido)

        salvo = self.banco.salvar_termo(
            "semântica",
            significado="Estudo do significado.",
            contexto_uso="Linguística.",
            permissao=self._permissao_memoria(),
        )
        recuperado = buscar_conhecimento_confirmado(self.banco, "semântica")
        resposta = compor_resposta_dinamica(recuperado, [], [])

        self.assertEqual([item.id for item in recuperado], [salvo.id])
        self.assertIn("Estudo do significado.", resposta)

    def test_codigo_gerado_rejeita_importes_e_caminhos_para_core(self):
        casos = (
            "import core",
            "from core.validador import validar",
            "from . import core",
            "import importlib\nimportlib.import_module('core')",
            "from pathlib import Path\nPath('core/validador.py').write_text('')",
        )

        for codigo in casos:
            with self.subTest(codigo=codigo):
                resultado = validar_codigo_gerado(codigo)
                self.assertFalse(resultado.permitida)

    def test_codigo_gerado_rejeita_sintaxe_invalida_sem_criar_arquivo(self):
        resultado = validar_codigo_gerado("class Quebrada(\n")

        self.assertFalse(resultado.permitida)
        self.assertIn("sintaxe inválida", resultado.mensagem)
        self.assertEqual(list(self.projeto.rglob("*.py")), [])


if __name__ == "__main__":
    unittest.main()