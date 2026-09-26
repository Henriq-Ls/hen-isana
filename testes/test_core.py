import sys
import subprocess
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.validador import validar, validar_execucao_isolada, validar_sintaxe
from core.versionamento import registrar_alteracao


class TestValidador(unittest.TestCase):
    def test_aceita_codigo_valido(self):
        resultado = validar("valor = 1 + 1")

        self.assertTrue(resultado.valido)
        self.assertEqual(resultado.etapa, "execucao")

    def test_bloqueia_sintaxe_invalida(self):
        resultado = validar_sintaxe("def sem_fechamento(")

        self.assertFalse(resultado.valido)
        self.assertEqual(resultado.etapa, "sintaxe")

    def test_bloqueia_erro_durante_execucao(self):
        resultado = validar_execucao_isolada("raise RuntimeError('falha de teste')")

        self.assertFalse(resultado.valido)
        self.assertEqual(resultado.etapa, "execucao")

    def test_interrompe_loop_infinito_no_processo_filho(self):
        resultado = validar_execucao_isolada(
            "while True:\n    pass\n",
            timeout_segundos=0.1,
        )

        self.assertFalse(resultado.valido)
        self.assertEqual(resultado.etapa, "execucao")
        self.assertIn("tempo limite", resultado.mensagem)

    def test_valida_arquivo_sem_altera_lo(self):
        with tempfile.TemporaryDirectory() as pasta:
            caminho = Path(pasta) / "modulo.py"
            caminho.write_text("resposta = 'ok'\n", encoding="utf-8")
            antes = caminho.read_text(encoding="utf-8")

            resultado = validar(caminho=caminho)

            self.assertTrue(resultado.valido)
            self.assertEqual(caminho.read_text(encoding="utf-8"), antes)


class TestVersionamento(unittest.TestCase):
    def test_cria_commit_real_em_repositorio_temporario(self):
        with tempfile.TemporaryDirectory() as pasta:
            diretorio = Path(pasta)
            subprocess.run(["git", "init"], cwd=diretorio, check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "teste@hen-isana.local"],
                cwd=diretorio,
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Teste hen-isana"],
                cwd=diretorio,
                check=True,
                capture_output=True,
            )
            arquivo = diretorio / "alteracao.py"
            arquivo.write_text("valor = 1\n", encoding="utf-8")

            resultado = registrar_alteracao(
                [arquivo],
                "Adicionar alteração de teste",
                diretorio=diretorio,
            )

            self.assertTrue(resultado.criado, resultado.mensagem)
            log = subprocess.run(
                ["git", "log", "-1", "--pretty=%s"],
                cwd=diretorio,
                check=True,
                capture_output=True,
                text=True,
            )
            self.assertEqual(log.stdout.strip(), "Adicionar alteração de teste")

    def test_recusa_commit_fora_de_repositorio(self):
        with tempfile.TemporaryDirectory() as pasta:
            resultado = registrar_alteracao(
                [Path(pasta) / "arquivo.py"],
                "teste",
                diretorio=Path(pasta),
            )

            self.assertFalse(resultado.criado)
            self.assertIn("não é um repositório Git", resultado.mensagem)

    def test_recusa_commit_sem_arquivos(self):
        resultado = registrar_alteracao([], "teste")

        self.assertFalse(resultado.criado)
        self.assertIn("nenhum arquivo", resultado.mensagem)
