"""Regressões de conversa contextual, estado de sessão e leitura do SQLite."""

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aplicacao.fluxo import processar_frase
from bancos.conhecimento import ConhecimentoDB
from core.contexto_conversa import ContextoConversa
from protocolo.regras import ALVO_CONHECIMENTO, TipoAcao
from protocolo.verificador import emitir_permissao


class TestConversaRegressao(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.banco = ConhecimentoDB(Path(self.pasta.name) / "conhecimento.db")
        self.permissao = emitir_permissao(
            TipoAcao.SALVAR_CONHECIMENTO,
            ALVO_CONHECIMENTO,
        )
        self._salvar(
            "bom dia",
            tipo="saudação",
            significado="FICHA DE BOM DIA.",
            contexto_uso="Cumprimento pela manhã.",
            exemplo_uso="A: Bom dia. B: Bom dia, como posso ajudar?",
        )
        self._salvar(
            "com licença",
            tipo="expressão de cortesia",
            significado="Pedido educado de passagem ou atenção.",
            contexto_uso="Ao passar por alguém ou pedir atenção.",
        )
        self._salvar(
            "qual é o seu nome",
            tipo="pergunta conversacional",
            significado="Pergunta o nome da pessoa.",
            contexto_uso="Durante uma apresentação.",
            exemplo_uso=(
                "A: Qual é o seu nome? "
                "B: Meu nome é Isana. E o seu?"
            ),
        )
        self._salvar(
            "prazer em conhecer",
            tipo="expressão conversacional",
            significado="Expressão de cortesia ao conhecer alguém.",
            contexto_uso="Durante uma apresentação.",
            exemplo_uso=(
                "A: Meu nome é Pedro. "
                "B: Prazer em conhecer, Pedro."
            ),
        )
        self._salvar(
            "estou triste",
            tipo="sentimento",
            significado="Uma forma de dizer que estou sentindo tristeza.",
            contexto_uso="Quando alguém comunica tristeza.",
            resposta_padrao="Sinto muito. Quer conversar?",
        )
        self._salvar(
            "manga",
            significado="Fruta tropical.",
            contexto_uso="Fruta tropical.",
        )
        self._salvar(
            "manga",
            significado="Parte da roupa que cobre o braço.",
            contexto_uso="Vestuário.",
        )
        self._salvar(
            "chuva",
            significado="Gotas de água que caem das nuvens até o chão.",
            contexto_uso="Fenômeno meteorológico.",
        )
        self.termos_antes_da_conversa = self.banco.listar_termos()
        self.alteracoes_antes_da_conversa = self.banco.conn.total_changes

    def tearDown(self):
        try:
            self.assertEqual(
                self.banco.conn.total_changes,
                self.alteracoes_antes_da_conversa,
                "o modo conversa alterou o SQLite",
            )
        finally:
            self.banco.fechar()
            self.pasta.cleanup()

    def _salvar(self, termo, **campos):
        self.banco.salvar_termo(
            termo,
            permissao=self.permissao,
            **campos,
        )

    def _conversar(self, frase, contexto):
        return processar_frase(
            frase,
            self.banco,
            modo_aprendizagem=False,
            contexto=contexto,
        )

    def test_tema_anterior_nao_vaza_para_fragmento_ou_assunto_desconhecido(self):
        contexto = ContextoConversa()

        saudacao = self._conversar("bom dia", contexto)
        fragmento_bom = self._conversar("bom", contexto)
        fragmento = self._conversar("licença", contexto)
        desconhecido = self._conversar("Quem é Pedro?", contexto)

        self.assertEqual(
            saudacao,
            ["Bom dia, como posso ajudar?"],
        )
        self.assertNotIn("FICHA DE BOM DIA", fragmento_bom[0])
        self.assertNotIn("Cumprimento pela manhã", fragmento_bom[0])
        self.assertIn("Ainda não sei", fragmento_bom[0])
        self.assertNotIn("FICHA DE BOM DIA", fragmento[0])
        self.assertNotIn("Cumprimento pela manhã", fragmento[0])
        self.assertIn("Ainda não sei", fragmento[0])
        self.assertNotIn("FICHA DE BOM DIA", desconhecido[0])
        self.assertNotIn("expressão conversacional", desconhecido[0])
        self.assertIn("Ainda não sei", desconhecido[0])

    def test_pergunta_explicita_recupera_o_termo_pedido_sem_topico_antigo(self):
        contexto = ContextoConversa()
        self._conversar("bom dia", contexto)

        resposta = self._conversar(
            "O que significa com licença?",
            contexto,
        )

        self.assertIn(
            "Pedido educado de passagem ou atenção.",
            resposta[0],
        )
        self.assertNotIn("FICHA DE BOM DIA", resposta[0])

    def test_nome_responde_pergunta_fica_na_sessao_e_substitui_nome_do_exemplo(self):
        contexto = ContextoConversa()
        antes = self.banco.conn.total_changes

        pergunta = self._conversar("Qual é o seu nome?", contexto)
        self.assertEqual(contexto.pergunta_pendente, "nome_interlocutor")
        resposta_nome = self._conversar("Henrique", contexto)
        cumprimento = self._conversar("prazer em conhecer", contexto)
        consulta_pessoa = self._conversar("Quem é Pedro?", contexto)

        self.assertIn("E o seu?", pergunta[0])
        self.assertEqual(contexto.turnos_recentes[0], "qual é o seu nome?")
        self.assertEqual(contexto.nome_interlocutor, "Henrique")
        self.assertIsNone(contexto.pergunta_pendente)
        self.assertNotIn("qual é o seu nome:", resposta_nome[0].casefold())
        self.assertIn("Henrique", cumprimento[0])
        self.assertNotIn("Pedro", cumprimento[0])
        self.assertIn("Ainda não sei", consulta_pessoa[0])
        self.assertNotIn("expressão conversacional", consulta_pessoa[0])
        self.assertEqual(self.banco.conn.total_changes, antes)
        self.assertEqual(
            self.banco.listar_termos(),
            self.termos_antes_da_conversa,
        )
        nova_sessao = ContextoConversa()
        self.assertEqual(nova_sessao.turnos_recentes, [])
        self.assertIsNone(nova_sessao.topico_atual)
        self.assertIsNone(nova_sessao.nome_interlocutor)
        self.assertIsNone(nova_sessao.pergunta_pendente)
        self.assertFalse(nova_sessao.resolver_pronome("ele").resolvida)

    def test_apresentacao_explicita_guarda_nome_apenas_no_contexto(self):
        contexto = ContextoConversa()
        antes = self.banco.conn.total_changes

        resposta = self._conversar("Meu nome é Ana Silva.", contexto)

        self.assertEqual(contexto.nome_interlocutor, "Ana Silva")
        self.assertIn("Ana Silva", resposta[0])
        self.assertEqual(self.banco.conn.total_changes, antes)
        self.assertEqual(
            self.banco.buscar_termo("Ana Silva"),
            [],
        )

    def test_pergunta_sem_registro_nao_usa_exemplo_como_fato_biografico(self):
        contexto = ContextoConversa()
        apresentacao = self._conversar("prazer em conhecer", contexto)

        resposta = self._conversar("Quem é Pedro?", contexto)

        self.assertNotIn("Pedro", apresentacao[0])
        self.assertIn("Ainda não sei", resposta[0])
        self.assertNotIn("Pedro", resposta[0])
        self.assertNotIn("Prazer em conhecer", resposta[0])

    def test_mudanca_de_assunto_cancela_pergunta_de_nome_pendente(self):
        contexto = ContextoConversa()
        self._conversar("Qual é o seu nome?", contexto)

        resposta = self._conversar(
            "O que significa com licença?",
            contexto,
        )

        self.assertIsNone(contexto.pergunta_pendente)
        self.assertIsNone(contexto.nome_interlocutor)
        self.assertIn(
            "Pedido educado de passagem ou atenção.",
            resposta[0],
        )

    def test_frase_de_assunto_nao_e_armazenada_como_nome(self):
        contexto = ContextoConversa()
        self._conversar("Qual é o seu nome?", contexto)

        resposta = self._conversar("Estou triste.", contexto)

        self.assertIsNone(contexto.pergunta_pendente)
        self.assertIsNone(contexto.nome_interlocutor)
        self.assertEqual(resposta, ["Sinto muito. Quer conversar?"])

    def test_erros_de_digitacao_pedem_confirmacao_antes_da_resposta(self):
        casos = ("chuv", "chvua", "chuvaa")
        alteracoes_antes = self.banco.conn.total_changes

        for digitacao in casos:
            with self.subTest(digitacao=digitacao):
                contexto = ContextoConversa()
                pergunta = self._conversar(digitacao, contexto)

                self.assertIn("Você quis dizer 'chuva'?", pergunta[0])
                self.assertNotIn("Gotas de água", pergunta[0])
                self.assertIsNotNone(contexto.correcao_digitacao_pendente)

                resposta = self._conversar("sim", contexto)

                self.assertIn("Gotas de água", resposta[0])
                self.assertIsNone(contexto.correcao_digitacao_pendente)

        self.assertEqual(self.banco.conn.total_changes, alteracoes_antes)

    def test_varios_candidatos_proximos_exigem_escolha_explicita(self):
        self._salvar(
            "casa",
            significado="Construção destinada à moradia.",
            contexto_uso="Habitação.",
        )
        self._salvar(
            "caso",
            significado="Situação ou ocorrência.",
            contexto_uso="Exemplo ou acontecimento.",
        )
        contexto = ContextoConversa()
        alteracoes_antes = self.banco.conn.total_changes
        self.termos_antes_da_conversa = self.banco.listar_termos()
        self.alteracoes_antes_da_conversa = alteracoes_antes

        pergunta = self._conversar("cas", contexto)

        self.assertIn("Encontrei mais de um termo próximo", pergunta[0])
        self.assertIn("1. 'casa'", pergunta[0])
        self.assertIn("2. 'caso'", pergunta[0])
        self.assertIsNotNone(contexto.correcao_digitacao_pendente)

        resposta = self._conversar("1", contexto)

        self.assertIn("Construção destinada à moradia.", resposta[0])
        self.assertIsNone(contexto.correcao_digitacao_pendente)
        self.assertEqual(self.banco.conn.total_changes, alteracoes_antes)

    def test_sem_candidato_proximo_a_conversa_admite_desconhecimento(self):
        contexto = ContextoConversa()

        resposta = self._conversar("xyzq", contexto)

        self.assertIn("Ainda não sei", resposta[0])
        self.assertNotIn("Você quis dizer", resposta[0])
        self.assertIsNone(contexto.correcao_digitacao_pendente)

    def test_saudacao_confirmada_no_inicio_de_frase_com_varios_termos(self):
        self._salvar(
            "olá",
            tipo="saudação",
            significado="Cumprimento para iniciar uma conversa.",
            contexto_uso="Ao cumprimentar alguém.",
        )
        self._salvar(
            "conversa",
            tipo="substantivo",
            significado="Troca de palavras e ideias entre pessoas.",
            contexto_uso="Durante uma interação.",
        )
        self.termos_antes_da_conversa = self.banco.listar_termos()
        self.alteracoes_antes_da_conversa = self.banco.conn.total_changes
        self.assertTrue(self.banco.buscar_termo_confirmado("olá")[0].significado)
        self.assertTrue(
            self.banco.buscar_termo_confirmado("conversa")[0].significado
        )

        resposta = self._conversar(
            "olá! quero testar a conversa.",
            ContextoConversa(),
        )

        self.assertEqual(resposta, ["Olá! Como posso ajudar?"])
        self.assertNotIn("Ainda não sei responder", resposta[0])

    def test_sequencia_autorizada_de_conversa_sem_escrita(self):
        contexto = ContextoConversa()
        entradas = (
            "ola",
            "Olá, bom dia",
            "Olá, bom dia!",
            "Como você está?",
            "Meu nome é Carlos. Qual é o seu nome?",
            "Até logo!",
            "chuva",
            "esta com chuva",
        )
        alteracoes_antes = self.banco.conn.total_changes

        respostas = [
            self._conversar(entrada, contexto)[0]
            for entrada in entradas
        ]

        self.assertEqual(respostas[0], "Olá! Como posso ajudar?")
        self.assertEqual(respostas[1], "Olá! Bom dia! Como posso ajudar?")
        self.assertEqual(respostas[2], "Olá! Bom dia! Como posso ajudar?")
        self.assertIn("Tudo certo", respostas[3])
        self.assertEqual(
            respostas[4],
            "Meu nome é Isana. Prazer, Carlos.",
        )
        self.assertEqual(respostas[5], "Até logo!")
        self.assertIn("Gotas de água", respostas[6])
        self.assertNotIn("chuva com chuva", respostas[7].casefold())
        self.assertEqual(contexto.nome_interlocutor, "Carlos")
        self.assertEqual(self.banco.conn.total_changes, alteracoes_antes)

    def test_pares_acentuados_nao_se_unem_no_mesmo_contexto(self):
        pares = (
            ("por", "pôr"),
            ("esta", "está"),
            ("sabia", "sábia"),
        )
        for simples, acentuado in pares:
            with self.subTest(simples=simples):
                self._salvar(
                    simples,
                    significado=f"sentido de {simples}",
                    contexto_uso="contexto ambíguo",
                )
                self._salvar(
                    acentuado,
                    significado=f"sentido de {acentuado}",
                    contexto_uso="contexto ambíguo",
                )
        self.termos_antes_da_conversa = self.banco.listar_termos()
        self.alteracoes_antes_da_conversa = self.banco.conn.total_changes

        for simples, acentuado in pares:
            with self.subTest(simples=simples):
                resultados_simples = self.banco.buscar_termo(simples)
                resultados_acentuados = self.banco.buscar_termo(acentuado)

                self.assertEqual(
                    [entrada.termo for entrada in resultados_simples],
                    [simples],
                )
                self.assertEqual(
                    [entrada.termo for entrada in resultados_acentuados],
                    [acentuado],
                )

    def test_topico_anterior_nao_resolve_uma_consulta_ambigua_nova(self):
        contexto = ContextoConversa()
        contexto.registrar_turno(
            "Falamos sobre fruta tropical.",
            topico="fruta",
        )

        resposta = self._conversar("manga", contexto)

        self.assertIn("mais de um sentido", resposta[0])
        self.assertIn("Fruta tropical.", resposta[0])
        self.assertIn("Vestuário.", resposta[0])
        self.assertIsNotNone(contexto.desambiguacao_pendente)


if __name__ == "__main__":
    unittest.main()