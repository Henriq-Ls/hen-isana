import contextlib
import io
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aplicacao.aprendizagem.cascata import CascataAprendizagem
from aplicacao.aprendizagem.sessao import executar_modo_professor
from aplicacao.conversa.sessao import executar_conversa_pessoal
from bancos.conhecimento import ConhecimentoDB
from bancos.relacoes import RelacoesDB
from protocolo.regras import (
    ALVO_CONHECIMENTO,
    ALVO_RELACOES,
    TipoAcao,
)
from protocolo.verificador import emitir_permissao


class TestCascataAprendizagem(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        raiz = Path(self.pasta.name)
        self.banco = ConhecimentoDB(raiz / "conhecimento.db")
        self.relacoes = RelacoesDB(raiz / "relacoes.db")
        self.permissao_memoria = emitir_permissao(
            TipoAcao.SALVAR_CONHECIMENTO,
            ALVO_CONHECIMENTO,
        )
        self.permissao_relacao = emitir_permissao(
            TipoAcao.SALVAR_RELACAO,
            ALVO_RELACOES,
        )

    def tearDown(self):
        self.relacoes.fechar()
        self.banco.fechar()
        self.pasta.cleanup()

    def _nova_cascata(self):
        return CascataAprendizagem(
            self.banco,
            self.relacoes,
            origem_resposta="usuario",
            permissao_memoria=self.permissao_memoria,
            permissao_relacao=self.permissao_relacao,
            componente_log="aprendizagem",
        )

    def test_aprendizagem_manual_encadeia_termo_novo_da_resposta(self):
        prompts = []
        entradas_terminal = iter(("termo: aracnox", "sair"))

        def responder(prompt):
            prompts.append(prompt)
            if prompt.strip() == "hen-isana>":
                return next(entradas_terminal)

            encontrado = re.search(r"'([^']+)'", prompt)
            termo = encontrado.group(1) if encontrado else "aracnox"
            if "significa" in prompt and termo == "aracnox":
                return "quasifoton"
            return "ok"

        with (
            patch("builtins.input", side_effect=responder),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            executar_conversa_pessoal(
                self.banco,
                self.relacoes,
                modo_aprendizagem=True,
                usar_internet=False,
                permissao_memoria=self.permissao_memoria,
                permissao_relacao=self.permissao_relacao,
            )

        termo_em_cascata = self.banco.buscar_termo("quasifoton")
        self.assertEqual(len(termo_em_cascata), 1)
        self.assertTrue(termo_em_cascata[0].completa)
        self.assertTrue(
            any(
                "quasifoton" in prompt and "significa" in prompt
                for prompt in prompts
            )
        )

    def test_assunto_composto_aprendido_gera_cascata_da_resposta(self):
        prompts = []
        entradas_terminal = iter(("uma vez", "sair"))

        def responder(prompt):
            prompts.append(prompt)
            if prompt.strip() == "hen-isana>":
                return next(entradas_terminal)
            if "significa" in prompt and "'uma vez'" in prompt:
                return "quasifoton"
            if "significa" in prompt and "'quasifoton'" in prompt:
                return "ok"
            if "exemplo" in prompt:
                return "ok"
            return "sim"

        with (
            patch("builtins.input", side_effect=responder),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            executar_conversa_pessoal(
                self.banco,
                self.relacoes,
                modo_aprendizagem=True,
                usar_internet=False,
                permissao_memoria=self.permissao_memoria,
                permissao_relacao=self.permissao_relacao,
            )

        assunto = self.banco.buscar_termo("uma vez")
        termo_em_cascata = self.banco.buscar_termo("quasifoton")
        self.assertEqual(len(assunto), 1)
        self.assertTrue(assunto[0].completa)
        self.assertEqual(len(termo_em_cascata), 1)
        self.assertTrue(termo_em_cascata[0].completa)
        self.assertTrue(
            any(
                "quasifoton" in prompt and "significa" in prompt
                for prompt in prompts
            )
        )

    def test_modo_professor_continua_usando_a_mesma_cascata(self):
        prompts = []
        professor = Mock()
        professor.configurado = True

        def responder_professor(pergunta):
            prompts.append(pergunta)
            encontrado = re.search(r"'([^']+)'", pergunta)
            termo = encontrado.group(1) if encontrado else "aracnox"
            if "significa" in pergunta and termo == "uma vez":
                return "quasifoton"
            return "ok"

        professor.responder.side_effect = responder_professor

        with (
            patch("builtins.input", side_effect=("uma vez", "sair")),
            patch(
                "aplicacao.aprendizagem.sessao.Professor",
                return_value=professor,
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            executar_modo_professor(
                self.banco,
                self.relacoes,
                permissao_memoria=self.permissao_memoria,
                permissao_relacao=self.permissao_relacao,
            )

        assunto = self.banco.buscar_termo("uma vez")
        termo_em_cascata = self.banco.buscar_termo("quasifoton")
        self.assertEqual(len(assunto), 1)
        self.assertTrue(assunto[0].completa)
        self.assertEqual(len(termo_em_cascata), 1)
        self.assertTrue(termo_em_cascata[0].completa)
        self.assertTrue(
            any(
                "quasifoton" in prompt and "significa" in prompt
                for prompt in prompts
            )
        )

    def test_modo_llama_local_usa_a_mesma_cascata(self):
        prompts = []

        def responder_llama(pergunta):
            prompts.append(pergunta)
            encontrado = re.search(r"'([^']+)'", pergunta)
            termo = encontrado.group(1) if encontrado else "aracnox"
            if "significa" in pergunta and termo == "aracnox":
                return "quasifoton"
            return "ok"

        class ProfessorLlamaTeste:
            configurado = True

            def responder(self, pergunta):
                return responder_llama(pergunta)

        with (
            patch("builtins.input", side_effect=("aracnox", "sair")),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            executar_modo_professor(
                self.banco,
                self.relacoes,
                permissao_memoria=self.permissao_memoria,
                permissao_relacao=self.permissao_relacao,
                professor_cls=ProfessorLlamaTeste,
                nome_professor="Professor Llama",
            )

        termo_em_cascata = self.banco.buscar_termo("quasifoton")
        self.assertEqual(len(termo_em_cascata), 1)
        self.assertTrue(termo_em_cascata[0].completa)
        self.assertTrue(
            any("quasifoton" in prompt for prompt in prompts)
        )

    def test_aprendizagem_internet_cascateia_resumo_aceito(self):
        consultas = []
        prompts = []

        def consultar(termo):
            consultas.append(termo)
            if termo == "aracnox":
                return Mock(
                    resumo="quasifoton",
                    titulo="Fonte de teste",
                    url="https://example.invalid/quasifoton",
                )
            return None

        entradas_terminal = iter(("aracnox", "sair"))

        def responder(pergunta):
            prompts.append(pergunta)
            if pergunta.strip() == "hen-isana>":
                return next(entradas_terminal)
            if "[s/n]" in pergunta.casefold():
                return "sim"
            return "ok"

        with (
            patch("builtins.input", side_effect=responder),
            patch(
                "aplicacao.fluxo.consultar_definicao",
                side_effect=consultar,
            ),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            executar_conversa_pessoal(
                self.banco,
                self.relacoes,
                modo_aprendizagem=True,
                usar_internet=True,
                permissao_memoria=self.permissao_memoria,
                permissao_relacao=self.permissao_relacao,
            )

        termo_em_cascata = self.banco.buscar_termo("quasifoton")
        self.assertEqual(consultas, ["aracnox", "quasifoton"])
        self.assertEqual(len(termo_em_cascata), 1)
        self.assertTrue(termo_em_cascata[0].completa)
        self.assertTrue(
            any("quasifoton" in prompt for prompt in prompts)
        )

    def test_resposta_de_tipo_analisa_todos_os_termos_desconhecidos(self):
        cascata = self._nova_cascata()
        cascata.registrar_entrada("assunto raiz")

        cascata.registrar_resposta(
            "Qual é o tipo de 'assunto raiz'?",
            "palavra alfa",
        )

        self.assertEqual(cascata.termos_pendentes, ["palavra", "alfa"])

    def test_cascata_continua_com_respostas_dos_termos_enfileirados(self):
        cascata = self._nova_cascata()
        cascata.registrar_entrada("assunto raiz")
        cascata.registrar_resposta(
            "O que significa 'assunto raiz'?",
            "quasifoton",
        )

        def responder(pergunta):
            encontrado = re.search(r"'([^']+)'", pergunta)
            termo = encontrado.group(1) if encontrado else ""
            if "significa" in pergunta and termo == "quasifoton":
                return "zqvantar"
            return "ok"

        with contextlib.redirect_stdout(io.StringIO()):
            cascata.processar_pendentes(responder)

        for termo in ("quasifoton", "zqvantar"):
            entradas = self.banco.buscar_termo(termo)
            self.assertEqual(len(entradas), 1)
            self.assertTrue(entradas[0].completa)

    def test_limita_a_quatro_termos_descobertos_em_uma_resposta(self):
        cascata = self._nova_cascata()
        cascata.registrar_entrada("assunto raiz")
        resposta = (
            "zqvantar xylophium quorvex blorbium tantarix"
        )

        with contextlib.redirect_stdout(io.StringIO()):
            cascata.registrar_resposta(
                "O que 'assunto raiz' significa?",
                resposta,
            )

        self.assertEqual(
            cascata.termos_pendentes,
            ["zqvantar", "xylophium", "quorvex", "blorbium"],
        )

    def test_respostas_de_controle_nao_entram_na_cascata(self):
        cascata = self._nova_cascata()
        cascata.registrar_entrada("assunto raiz")

        cascata.registrar_resposta(
            "O que 'assunto raiz' significa?",
            "sair",
        )
        cascata.registrar_resposta(
            "É sinônimo? [s/n]",
            "não",
        )
        cascata.registrar_resposta(
            "É uma relação? [s/n]",
            "Sim, a relação parece correta e pode ser usada.",
        )

        self.assertEqual(cascata.termos_pendentes, [])

    def test_interrompe_a_cascata_ao_atingir_sessenta_e_quatro_termos(self):
        cascata = self._nova_cascata()
        cascata.termos_em_cadeia.update(
            f"termo{i:02d}" for i in range(64)
        )

        with contextlib.redirect_stdout(io.StringIO()) as saida:
            cascata.registrar_resposta(
                "O que 'termo00' significa?",
                "novotermo",
            )

        self.assertEqual(cascata.termos_pendentes, [])
        self.assertIn(
            "limite de aprendizagem em cascata",
            saida.getvalue().casefold(),
        )


if __name__ == "__main__":
    unittest.main()