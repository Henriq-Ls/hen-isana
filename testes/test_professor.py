import unittest

from professor.professor import Professor


class TestRespostaDoProfessor(unittest.TestCase):
    def test_rejeita_metadado_de_seguranca_mesmo_sem_response_safety(self):
        self.assertTrue(
            Professor._parece_metadado_de_seguranca("User Safety: safe")
        )
        self.assertTrue(
            Professor._parece_metadado_de_seguranca("Response Safety: safe")
        )

    def test_rejeita_raciocinio_exposto_no_conteudo(self):
        self.assertTrue(
            Professor._parece_raciocinio_exposto(
                "Okay, the user is asking for a short definition."
            )
        )
        self.assertFalse(
            Professor._parece_raciocinio_exposto(
                "É uma saudação informal usada no início da conversa."
            )
        )

    def test_categoria_precisa_ser_curta_e_sem_explicacao(self):
        self.assertTrue(Professor._categoria_curta_valida("Interjeição"))
        self.assertTrue(
            Professor._categoria_curta_valida(
                "Interjeição ou saudação informal."
            )
        )
        self.assertTrue(
            Professor._categoria_curta_valida("Classe gramatical")
        )
        self.assertFalse(
            Professor._categoria_curta_valida(
                "We need to answer: the category is a noun because this is "
                "a grammar question."
            )
        )
        self.assertFalse(
            Professor._categoria_curta_valida("User Safety: safe")
        )

    def test_responder_descarta_metadado_e_tenta_novamente(self):
        professor = Professor(
            url_http="http://localhost:11434",
            modelo="teste",
        )
        professor._cache_respostas = {}
        professor._guardar_cache = lambda _chave, _resposta: None  # type: ignore[method-assign]
        professor._salvar_historico = lambda: None  # type: ignore[method-assign]
        respostas = iter(["User Safety: safe", "adjetivo"])
        professor.conversar = lambda _texto: next(respostas)  # type: ignore[method-assign]

        resultado = professor.responder(
            "Qual é o tipo ou categoria de 'bom'?"
        )

        self.assertEqual(resultado, "adjetivo")

    def test_responder_descarta_raciocinio_e_tenta_novamente(self):
        professor = Professor(
            url_http="http://localhost:11434",
            modelo="teste",
        )
        professor._cache_respostas = {}
        professor._guardar_cache = lambda _chave, _resposta: None  # type: ignore[method-assign]
        professor._salvar_historico = lambda: None  # type: ignore[method-assign]
        respostas = iter(
            [
                "Okay, the user is asking for a short definition.",
                "É uma saudação informal.",
            ]
        )
        professor.conversar = lambda _texto: next(respostas)  # type: ignore[method-assign]

        resultado = professor.responder("O que 'ola' significa?")

        self.assertEqual(resultado, "É uma saudação informal.")

    def test_reutiliza_cache_sem_chamar_professor(self):
        professor = Professor(
            url_http="http://localhost:11434",
            modelo="teste",
        )
        professor._salvar_historico = lambda: None  # type: ignore[method-assign]
        pergunta = "O que 'cache-local' significa?"
        professor._cache_respostas = {
            professor._chave_cache(pergunta): "Resposta salva localmente."
        }
        professor.conversar = lambda _texto: (_ for _ in ()).throw(  # type: ignore[method-assign]
            AssertionError("o professor externo não deveria ser chamado")
        )

        self.assertEqual(
            professor.responder(pergunta),
            "Resposta salva localmente.",
        )

    def test_extrai_resposta_compatível_com_chat(self):
        resposta = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": "pronome"},
                }
            ]
        }

        self.assertEqual(Professor._extrair_texto(resposta), "pronome")

    def test_identifica_limite_de_tokens_sem_mascarar_a_causa(self):
        resposta = {
            "choices": [
                {
                    "finish_reason": "length",
                    "message": {
                        "content": "",
                        "reasoning": "raciocínio consumiu o orçamento",
                    },
                }
            ],
            "usage": {
                "completion_tokens": 512,
                "completion_tokens_details": {"reasoning_tokens": 512},
            },
        }

        with self.assertRaisesRegex(RuntimeError, "esgotou o limite de tokens"):
            Professor._extrair_texto(resposta)

        self.assertTrue(Professor._resposta_sem_texto_visivel(resposta))
        diagnostico = Professor._metadados_resposta(resposta)
        self.assertEqual(diagnostico["finish_reason"], "length")
        self.assertEqual(diagnostico["reasoning_tokens"], 512)

    def test_monta_controle_de_raciocinio_somente_para_openrouter(self):
        professor = Professor(
            url_http="https://openrouter.ai/api/v1",
            modelo="openrouter/free",
        )
        professor._historico = [
            {"role": "system", "content": "instrução"},
            {"role": "user", "content": "pergunta"},
        ]

        payload = professor._montar_payload(512)

        self.assertEqual(payload["max_tokens"], 512)
        self.assertEqual(
            payload["reasoning"],
            {"effort": "minimal", "exclude": True},
        )

    def test_limita_contexto_sem_remover_a_instrucao_do_sistema(self):
        professor = Professor(
            url_http="http://localhost:11434",
            modelo="teste",
        )
        professor._historico = [
            {"role": "system", "content": "instrução"},
            *[
                {"role": "user", "content": f"pergunta-{indice}"}
                for indice in range(8)
            ],
        ]

        contexto = professor._historico_para_payload()

        self.assertEqual(contexto[0]["content"], "instrução")
        self.assertEqual(len(contexto), 7)
        self.assertEqual(contexto[-1]["content"], "pergunta-7")