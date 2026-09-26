import sys
import tempfile
import unittest
import re
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bancos.conhecimento import ConhecimentoDB
from bancos.relacoes import RelacoesDB
from core.controlador import aplicar_codigo_gerado
from core.contexto_conversa import ContextoConversa, Mencao
from core.linguagem import (
    EXPRESSOES_CONVERSACIONAIS,
    PALAVRAS_FUNCIONAIS,
    PALAVRAS_IGNORADAS_AO_APRENDER_RESPOSTA,
)
from core.normalizador import normalizar_frase
from main import (
    aprender_termo,
    interpretar_pergunta,
    processar_frase,
    _escolher_fonte_aprendizagem,
    _escolher_modo,
    termos_desconhecidos_no_texto,
    tokenizar,
)
from protocolo.regras import TipoAcao
from protocolo.regras import ALVO_CONHECIMENTO, ALVO_GERADO_ROOT, ALVO_RELACOES
from protocolo.verificador import (
    emitir_permissao,
    validar_codigo_gerado,
    verificar_acao,
)


def permissao_memoria():
    return emitir_permissao(
        TipoAcao.SALVAR_CONHECIMENTO,
        ALVO_CONHECIMENTO,
    )


def permissao_relacao():
    return emitir_permissao(
        TipoAcao.SALVAR_RELACAO,
        ALVO_RELACOES,
    )


class TestAprendizagemCompleta(unittest.TestCase):
    def test_contexto_resolve_ele_para_o_sujeito_da_frase_anterior(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            for termo, resposta in (
                ("cachorro", "Cachorro é o animal mencionado."),
                ("parque", "Parque é o lugar mencionado."),
            ):
                banco.salvar_termo(
                    termo,
                    tipo="substantivo",
                    significado=f"Significado de {termo}.",
                    contexto_uso=f"Quando se fala de {termo}.",
                    resposta_padrao=resposta,
                    permissao=permissao_memoria(),
                )
            alteracoes_antes = banco.conn.total_changes
            contexto = ContextoConversa()

            processar_frase(
                "O cachorro correu até o parque.",
                banco,
                modo_aprendizagem=False,
                projeto_dir=Path(pasta),
                contexto=contexto,
            )
            resultado = processar_frase(
                "Ele estava cansado.",
                banco,
                modo_aprendizagem=False,
                projeto_dir=Path(pasta),
                contexto=contexto,
            )

            self.assertIn("Ainda não sei", resultado[0])
            self.assertNotIn("Significado de cachorro.", resultado[0])
            self.assertNotIn("Cachorro é o animal mencionado.", resultado[0])
            self.assertEqual(contexto.topico_atual, "cachorro")
            self.assertEqual(banco.conn.total_changes, alteracoes_antes)
            banco.fechar()

    def test_contexto_pede_esclarecimento_quando_referencia_e_ambigua(self):
        contexto = ContextoConversa()
        contexto.registrar_turno(
            "cachorro parque",
            [
                Mencao("cachorro", "cachorro", posicao_na_frase=0),
                Mencao("parque", "parque", posicao_na_frase=1),
            ],
        )

        resultado = contexto.resolver_frase("Ele está lá.")

        self.assertTrue(resultado.ambiguidades)
        self.assertEqual(resultado.frase_resolvida, "Ele está lá.")

    def test_processar_frase_pede_esclarecimento_para_pronome_ambiguo(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            contexto = ContextoConversa()
            contexto.registrar_turno(
                "cachorro parque",
                [
                    Mencao("cachorro", "cachorro"),
                    Mencao("parque", "parque"),
                ],
            )

            resultado = processar_frase(
                "Ele está lá.",
                banco,
                modo_aprendizagem=False,
                projeto_dir=Path(pasta),
                contexto=contexto,
            )

            self.assertEqual(len(resultado), 1)
            self.assertIn("Não consegui identificar", resultado[0])
            self.assertIn("'cachorro'", resultado[0])
            self.assertIn("'parque'", resultado[0])
            banco.fechar()

    def test_contexto_nao_persiste_entre_instancias(self):
        contexto = ContextoConversa()
        contexto.registrar_turno(
            "o cachorro",
            [Mencao("cachorro", "cachorro", eh_sujeito=True)],
        )

        novo_contexto = ContextoConversa()

        self.assertFalse(novo_contexto.resolver_pronome("ele").resolvida)

    def test_normaliza_abreviacoes_antes_do_roteamento(self):
        self.assertEqual(normalizar_frase("QT horas"), "quantas horas")
        self.assertEqual(normalizar_frase("vc tbm pode"), "você também pode")

    def test_vocativo_nao_aparece_como_desconhecido(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            banco.salvar_termo(
                "estou triste",
                tipo="sentimento",
                significado="Uma forma de dizer que estou sentindo tristeza.",
                contexto_uso="Quando alguém comunica tristeza.",
                resposta_padrao="Sinto muito. Quer conversar?",
                permissao=permissao_memoria(),
            )

            resultado = processar_frase(
                "Mano estou triste",
                banco,
                modo_aprendizagem=False,
                projeto_dir=Path(pasta),
            )

            self.assertIn("Sinto muito. Quer conversar?", resultado[0])
            self.assertNotIn("Uma forma de dizer", resultado[0])
            banco.fechar()

    def test_abreviacao_de_hora_nao_inicia_aprendizagem(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            resultado = processar_frase(
                "qt horas",
                banco,
                modo_aprendizagem=False,
                projeto_dir=Path(pasta),
            )

            self.assertEqual(len(resultado), 1)
            self.assertIn("Agora são", resultado[0])
            self.assertEqual(banco.listar_termos(), [])
            banco.fechar()

    def test_regras_linguisticas_vem_do_arquivo_e_dev_pode_ser_aprendido(self):
        self.assertIn("que", PALAVRAS_FUNCIONAIS)
        self.assertIn("que", PALAVRAS_IGNORADAS_AO_APRENDER_RESPOSTA)
        self.assertIn("bom dia", EXPRESSOES_CONVERSACIONAIS)
        self.assertNotIn("dev", PALAVRAS_FUNCIONAIS)
        self.assertNotIn("dev", PALAVRAS_IGNORADAS_AO_APRENDER_RESPOSTA)

        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            respostas = iter(
                [
                    "uma pessoa desenvolvedora",
                    "A frase 'dev trabalha no projeto' usa esse termo.",
                ]
            )

            resultado = processar_frase(
                "dev",
                banco,
                perguntar=lambda _mensagem: next(respostas),
                permissao_memoria=permissao_memoria(),
                projeto_dir=Path(pasta),
                modo_aprendizagem=True,
            )

            self.assertEqual(
                resultado,
                ["uma pessoa desenvolvedora"],
            )
            self.assertTrue(banco.buscar_termo("dev")[0].completa)
            banco.fechar()

    def test_modo_conversa_nao_aprende_termo_desconhecido(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            perguntas = []

            resultado = processar_frase(
                "Fala aí, mano, tudo bem?",
                banco,
                perguntar=lambda mensagem: perguntas.append(mensagem) or "",
                projeto_dir=Path(pasta),
                modo_aprendizagem=False,
            )

            self.assertEqual(perguntas, [])
            self.assertTrue(
                any("Ainda não sei" in item for item in resultado)
            )
            self.assertEqual(banco.buscar_termo("fala"), [])
            self.assertEqual(banco.buscar_termo("mano"), [])
            banco.fechar()

    def test_menu_separa_conversa_aprendizagem_e_fontes(self):
        with patch("builtins.input", side_effect=["2"]):
            self.assertEqual(_escolher_modo(), "aprendizagem")
        with patch("builtins.input", side_effect=["3"]):
            self.assertEqual(_escolher_fonte_aprendizagem(), "internet")
        with patch("builtins.input", side_effect=["4"]):
            self.assertEqual(_escolher_fonte_aprendizagem(), "llama")

    def test_aprendizagem_adaptativa_nao_exige_categoria(self):
        with tempfile.TemporaryDirectory() as pasta:
            projeto = Path(pasta)
            banco = ConhecimentoDB(projeto / "conhecimento.db")
            perguntas = []
            respostas = iter(
                [
                    "Uma forma de cumprimentar.",
                    "Olá! Como vai?",
                ]
            )

            resultado = processar_frase(
                "olá",
                banco,
                perguntar=lambda mensagem: perguntas.append(mensagem)
                or next(respostas),
                projeto_dir=projeto,
                permissao_memoria=permissao_memoria(),
                permissao_relacao=permissao_relacao(),
            )

            self.assertEqual(resultado, ["Uma forma de cumprimentar."])
            self.assertEqual(len(perguntas), 2)
            self.assertIn("significa", perguntas[0])
            self.assertIn("exemplo", perguntas[1])
            arquivo = projeto / "aprendizado" / "gerado" / "saudacao.py"
            self.assertFalse(arquivo.exists())
            banco.fechar()

    def test_aprende_um_termo_e_depois_responde_sem_repetir_perguntas(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            respostas = iter(
                [
                    "uma forma de cumprimentar",
                    "Olá! Como vai?",
                ]
            )

            entrada = aprender_termo(
                "olá",
                banco,
                perguntar=lambda _mensagem: next(respostas),
                permissao_memoria=permissao_memoria(),
            )

            self.assertTrue(entrada.completa)
            self.assertEqual(
                entrada.exemplo_uso,
                "Olá! Como vai?",
            )

            def nao_deveria_perguntar(_mensagem: str) -> str:
                raise AssertionError("o termo completo não deveria ser perguntado")

            resultado = processar_frase(
                "olá",
                banco,
                perguntar=nao_deveria_perguntar,
                projeto_dir=Path(pasta),
            )
            self.assertEqual(resultado, ["uma forma de cumprimentar"])
            banco.fechar()

    def test_expressao_composta_e_preservada(self):
        resultado = tokenizar(
            "tudo bem hoje",
            ["tudo bem"],
        )

        self.assertEqual(resultado, ["tudo bem", "hoje"])

    def test_expressoes_de_conversa_sao_aprendidas_como_unidade(self):
        casos = (
            ("Bom dia", "Bom dia!"),
            ("olá, tudo bem?", "Olá! Tudo ótimo."),
            ("por favor", "Claro, pois não."),
            ("até logo", "Até logo!"),
        )
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            for frase, resposta in casos:
                respostas = iter(
                    [
                        "Uma expressão usada em conversa.",
                        f"Exemplo: {frase}.",
                    ]
                )
                resultado = processar_frase(
                    frase,
                    banco,
                    perguntar=lambda _mensagem: next(respostas),
                    projeto_dir=Path(pasta),
                    permissao_memoria=permissao_memoria(),
                    permissao_relacao=permissao_relacao(),
                )

                termo = " ".join(
                    re.findall(r"\w+", frase.casefold(), flags=re.UNICODE)
                )
                self.assertEqual(resultado, ["Uma expressão usada em conversa."])
                self.assertTrue(banco.buscar_termo(frase)[0].completa)
                self.assertIn(termo, banco.listar_termos())
                for palavra in termo.split():
                    self.assertEqual(
                        banco.buscar_termo(palavra),
                        [],
                        f"o trecho {palavra!r} não deveria ser aprendido sozinho",
                    )

                def nao_deveria_perguntar(_mensagem: str) -> str:
                    raise AssertionError(
                        "uma expressão já ensinada não deveria repetir perguntas"
                    )

                self.assertEqual(
                    processar_frase(
                        frase.upper(),
                        banco,
                        perguntar=nao_deveria_perguntar,
                        projeto_dir=Path(pasta),
                    ),
                    ["Uma expressão usada em conversa."],
                )
            banco.fechar()

    def test_pergunta_direta_responde_o_campo_solicitado(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            banco.salvar_termo(
                "academia",
                tipo="instituição",
                significado="Um lugar de estudo ou treino.",
                contexto_uso="Em conversas sobre educação ou exercício.",
                resposta_padrao="A academia está aberta.",
                permissao=permissao_memoria(),
            )

            self.assertEqual(
                interpretar_pergunta("O que significa academia?"),
                ("significado", "academia"),
            )
            self.assertEqual(
                processar_frase("O que significa academia?", banco),
                ["Um lugar de estudo ou treino."],
            )
            self.assertEqual(
                processar_frase("academia", banco),
                ["A academia está aberta."],
            )
            banco.fechar()

    def test_conversa_retorna_fala_b_e_pergunta_de_significado_e_estruturada(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            banco.salvar_termo(
                "bom dia",
                tipo="saudação",
                significado="Uma expressão usada para cumprimentar pela manhã.",
                contexto_uso="Usada ao encontrar alguém pela manhã.",
                exemplo_uso=(
                    "A: Como cumprimento alguém pela manhã? "
                    "B: Bom dia, como posso ajudar?"
                ),
                resposta_padrao="RESPOSTA FIXA QUE NÃO DEVE SER USADA.",
                permissao=permissao_memoria(),
            )

            saudacao = processar_frase(
                "bom dia",
                banco,
                modo_aprendizagem=False,
                contexto=ContextoConversa(),
            )
            explicacao = processar_frase(
                "O que significa bom dia?",
                banco,
                modo_aprendizagem=False,
                contexto=ContextoConversa(),
            )

            self.assertEqual(saudacao, ["Bom dia, como posso ajudar?"])
            self.assertNotIn("significado:", saudacao[0])
            self.assertIn("significado:", explicacao[0])
            self.assertIn("contexto de uso:", explicacao[0])
            self.assertIn(
                "Uma expressão usada para cumprimentar pela manhã.",
                explicacao[0],
            )
            self.assertNotIn("RESPOSTA FIXA", explicacao[0])
            banco.fechar()

    def test_conversa_normal_nao_expoe_a_ficha_do_termo(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            banco.salvar_termo(
                "aprendizado de máquina",
                significado="Método que identifica padrões em dados.",
                contexto_uso="Em inteligência artificial.",
                exemplo_uso="O aprendizado de máquina classifica imagens.",
                resposta_padrao="RESPOSTA FIXA QUE NÃO DEVE SER USADA.",
                permissao=permissao_memoria(),
            )

            resultado = processar_frase(
                "aprendizado de máquina",
                banco,
                modo_aprendizagem=False,
                contexto=ContextoConversa(),
            )

            self.assertIn("Ainda não sei", resultado[0])
            self.assertNotIn(
                "Método que identifica padrões em dados.",
                resultado[0],
            )
            self.assertNotIn("Em inteligência artificial.", resultado[0])
            self.assertNotIn(
                "O aprendizado de máquina classifica imagens.",
                resultado[0],
            )
            self.assertNotIn("RESPOSTA FIXA", resultado[0])
            self.assertEqual(banco.buscar_termo("aprendizado"), [])
            banco.fechar()

    def test_conversa_esclarece_sentido_e_usa_a_resposta_seguinte(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            banco.salvar_termo(
                "manga",
                significado="Fruta tropical.",
                contexto_uso="Alimentação.",
                permissao=permissao_memoria(),
            )
            banco.salvar_termo(
                "manga",
                significado="Parte da roupa que cobre o braço.",
                contexto_uso="Vestuário.",
                permissao=permissao_memoria(),
            )
            contexto = ContextoConversa()

            pergunta = processar_frase(
                "O que significa manga?",
                banco,
                modo_aprendizagem=False,
                contexto=contexto,
            )
            self.assertIsNotNone(contexto.desambiguacao_pendente)
            resposta = processar_frase(
                "vestuário",
                banco,
                modo_aprendizagem=False,
                contexto=contexto,
            )

            self.assertIn("mais de um sentido", pergunta[0])
            self.assertIn("1. Alimentação", pergunta[0])
            self.assertIn("Parte da roupa", resposta[0])
            self.assertNotIn("Fruta tropical", resposta[0])
            self.assertEqual(contexto.topico_atual, "manga")
            self.assertIsNone(contexto.desambiguacao_pendente)
            banco.fechar()

    def test_conversa_recupera_fato_pelo_contexto_dos_turnos_recentes(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            fato = banco.salvar_fato(
                "A capital do Brasil é Brasília.",
                "geografia",
                permissao=permissao_memoria(),
            )
            contexto = ContextoConversa()
            contexto.registrar_turno(
                "Falamos sobre o Brasil.",
                [Mencao("Brasil", "brasil", eh_sujeito=True)],
                topico="brasil",
            )

            resultado = processar_frase(
                "E mais?",
                banco,
                modo_aprendizagem=False,
                contexto=contexto,
            )

            self.assertIn(fato.afirmacao, resultado[0])
            self.assertIn("geografia", resultado[0])
            self.assertEqual(banco.buscar_fatos_confirmados(), [fato])
            banco.fechar()

    def test_conversa_nao_inventa_resposta_quando_nao_ha_conhecimento(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")

            resultado = processar_frase(
                "Qual é a capital de Noveria?",
                banco,
                modo_aprendizagem=False,
            )

            self.assertIn("Ainda não sei", resultado[0])
            self.assertIn("conhecimento confirmado", resultado[0])
            self.assertEqual(banco.listar_termos(), [])
            self.assertEqual(banco.buscar_fatos(), [])
            banco.fechar()

    def test_conversa_ignora_fato_nao_confirmado(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            banco.salvar_fato(
                "A capital de Noveria é Zal.",
                "geografia",
                origem="professor",
                estado="proposta",
                permissao=permissao_memoria(),
            )

            resultado = processar_frase(
                "Qual é a capital de Noveria?",
                banco,
                modo_aprendizagem=False,
            )

            self.assertIn("Ainda não sei", resultado[0])
            self.assertNotIn("Zal", resultado[0])
            self.assertEqual(banco.buscar_fatos_confirmados(), [])
            banco.fechar()

    def test_conversa_nao_expõe_significado_nao_confirmado(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            banco.salvar_termo(
                "noveria",
                significado="Um país inventado que parece real.",
                proveniencias={
                    "significado": ("professor", "proposta"),
                },
                permissao=permissao_memoria(),
            )

            resultado = processar_frase(
                "noveria",
                banco,
                modo_aprendizagem=False,
            )

            self.assertIn("Ainda não sei", resultado[0])
            self.assertNotIn("país inventado", resultado[0])
            banco.fechar()

    def test_conversa_inclui_relacoes_confirmadas_relevantes(self):
        with tempfile.TemporaryDirectory() as pasta:
            projeto = Path(pasta)
            banco = ConhecimentoDB(projeto / "conhecimento.db")
            cachorro = banco.salvar_termo(
                "cachorro",
                significado="Animal doméstico.",
                contexto_uso="Em conversas sobre animais.",
                permissao=permissao_memoria(),
            )
            animal = banco.salvar_termo(
                "animal",
                significado="Ser vivo capaz de se mover.",
                contexto_uso="Em biologia.",
                permissao=permissao_memoria(),
            )
            relacoes = RelacoesDB(projeto / "relacoes.db")
            relacoes.adicionar(
                cachorro.id,
                animal.id,
                tipo="categoria",
                permissao=permissao_relacao(),
            )

            resultado = processar_frase(
                "cachorro",
                banco,
                relacoes=relacoes,
                modo_aprendizagem=False,
            )

            self.assertIn("Relações registradas: animal", resultado[0])
            relacoes.fechar()
            banco.fechar()

    def test_consulta_de_hora_usa_a_frase_inteira_antes_dos_tokens(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")

            resultado = processar_frase(
                "quero saber quantas horas?",
                banco,
                modo_aprendizagem=False,
            )

            self.assertEqual(len(resultado), 1)
            self.assertIn("Agora são", resultado[0])
            self.assertEqual(banco.buscar_termo("quero"), [])
            self.assertEqual(banco.buscar_termo("horas"), [])
            banco.fechar()

    def test_consulta_de_hora_com_prefixo_nao_inicia_aprendizagem(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            perguntas = []

            resultado = processar_frase(
                "ola mano quantas horas?",
                banco,
                perguntar=lambda mensagem: perguntas.append(mensagem) or "",
                modo_aprendizagem=True,
            )

            self.assertEqual(len(resultado), 1)
            self.assertIn("Agora são", resultado[0])
            self.assertEqual(perguntas, [])
            self.assertEqual(banco.buscar_termo("mano"), [])
            banco.fechar()

    def test_expressao_com_palavra_funcional_e_aprendida_como_um_assunto(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            perguntas = []

            def responder(mensagem: str) -> str:
                perguntas.append(mensagem)
                if "significa" in mensagem:
                    return "Uma expressão que indica uma única ocorrência."
                if "exemplo" in mensagem:
                    return "Aconteceu uma vez."
                raise AssertionError(f"pergunta inesperada: {mensagem}")

            resultado = processar_frase(
                "uma vez",
                banco,
                perguntar=responder,
                projeto_dir=Path(pasta),
                modo_aprendizagem=True,
                permissao_memoria=permissao_memoria(),
                permissao_relacao=permissao_relacao(),
            )

            self.assertEqual(resultado, ["Uma expressão que indica uma única ocorrência."])
            self.assertTrue(
                any("'uma vez'" in pergunta for pergunta in perguntas)
            )
            self.assertTrue(banco.buscar_termo("uma vez")[0].completa)
            self.assertEqual(banco.buscar_termo("uma"), [])
            self.assertEqual(banco.buscar_termo("vez"), [])
            banco.fechar()

    def test_fonte_online_consulta_a_expressao_inteira_e_continua_perguntando(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            perguntas = []

            def responder(mensagem: str) -> str:
                perguntas.append(mensagem)
                if "significa" in mensagem:
                    return "Uma expressão para indicar uma única ocorrência."
                if "exemplo" in mensagem:
                    return "Isso aconteceu uma vez."
                raise AssertionError(f"pergunta inesperada: {mensagem}")

            with patch("main.consultar_definicao") as consulta:
                consulta.return_value = None
                resultado = processar_frase(
                    "uma vez",
                    banco,
                    perguntar=responder,
                    projeto_dir=Path(pasta),
                    usar_internet=True,
                    origem_resposta="professor",
                    modo_aprendizagem=True,
                    permissao_memoria=permissao_memoria(),
                    permissao_relacao=permissao_relacao(),
                )

            consulta.assert_called_once_with("uma vez")
            self.assertTrue(
                any("'uma vez'" in pergunta for pergunta in perguntas)
            )
            self.assertTrue(banco.buscar_termo("uma vez"))
            self.assertNotIn("termo claro", " ".join(resultado))
            banco.fechar()

    def test_pergunta_completa_aprende_o_assunto_e_nao_a_palavra_que(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            respostas = iter(
                [
                    "lugar de estudo",
                    "Biblioteca é um lugar de estudo.",
                ]
            )

            resultado = processar_frase(
                "o que é biblioteca?",
                banco,
                perguntar=lambda _mensagem: next(respostas),
                projeto_dir=Path(pasta),
                modo_aprendizagem=True,
                permissao_memoria=permissao_memoria(),
                permissao_relacao=permissao_relacao(),
            )

            self.assertEqual(resultado, ["lugar de estudo"])
            self.assertEqual(banco.buscar_termo("que"), [])
            self.assertTrue(banco.buscar_termo("biblioteca")[0].completa)
            banco.fechar()

    def test_modo_professor_estuda_assunto_que_termina_com_interrogacao(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            perguntas = []
            respostas = iter(
                [
                    "Um termo usado para teste.",
                    "Exemplo: termo em uma frase de teste.",
                ]
            )

            def professor(pergunta: str) -> str:
                perguntas.append(pergunta)
                return next(respostas)

            resultado = processar_frase(
                "termo?",
                banco,
                perguntar=professor,
                projeto_dir=Path(pasta),
                origem_resposta="professor",
                permissao_memoria=permissao_memoria(),
                permissao_relacao=permissao_relacao(),
            )

            self.assertEqual(resultado, ["Um termo usado para teste."])
            self.assertEqual(len(perguntas), 2)
            self.assertTrue(perguntas[0].startswith("O que"))
            self.assertIn("exemplo", perguntas[1])
            self.assertNotIn("termo?", perguntas[0])
            self.assertTrue(banco.buscar_termo("termo")[0].completa)
            banco.fechar()

    def test_modo_professor_nao_confirma_sua_propria_correcao(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            original = banco.salvar_termo(
                "olá",
                tipo="Saudação",
                significado="Um cumprimento.",
                contexto_uso="Em conversas.",
                resposta_padrao="Olá é um cumprimento informal.",
                permissao=permissao_memoria(),
            )
            perguntas = []

            def professor(mensagem: str) -> str:
                perguntas.append(mensagem)
                return "Olá! Como posso ajudar?"

            entrada = aprender_termo(
                "olá",
                banco,
                perguntar=professor,
                origem_resposta="professor",
                permissao_memoria=permissao_memoria(),
            )

            self.assertIsNone(entrada)
            self.assertEqual(len(banco.buscar_termo("olá")), 1)
            self.assertEqual(
                banco.buscar_termo("olá")[0].resposta_padrao,
                original.resposta_padrao,
            )
            self.assertEqual(len(perguntas), 1)
            self.assertIn("resposta direta", perguntas[0])
            banco.fechar()

    def test_identifica_palavras_relevantes_desconhecidas(self):
        with tempfile.TemporaryDirectory() as pasta:
            banco = ConhecimentoDB(Path(pasta) / "conhecimento.db")
            banco.salvar_termo(
                "academia",
                tipo="instituição",
                significado="Um lugar.",
                contexto_uso="Em conversas.",
                resposta_padrao="A academia está aberta.",
                permissao=permissao_memoria(),
            )

            desconhecidas = termos_desconhecidos_no_texto(
                "Academia é uma instituição educacional.",
                banco,
                ignorar={"academia"},
            )

            self.assertEqual(desconhecidas, ["instituição", "educacional"])
            banco.fechar()


class TestIsolamentoEEscrita(unittest.TestCase):
    def test_escritas_recusam_permissao_ausente(self):
        with tempfile.TemporaryDirectory() as pasta:
            projeto = Path(pasta)
            banco = ConhecimentoDB(projeto / "conhecimento.db")
            with self.assertRaises(PermissionError):
                banco.salvar_termo("sem autorização")

            relacoes = RelacoesDB(projeto / "relacoes.db")
            with self.assertRaises(PermissionError):
                relacoes.adicionar(1, 2)

            resultado = aplicar_codigo_gerado(
                "sem_autorizacao.py",
                "class SemAutorizacao:\n    pass\n",
                projeto_dir=projeto,
            )
            self.assertFalse(resultado.sucesso)
            self.assertIn("permissão", resultado.mensagem)
            banco.fechar()
            relacoes.fechar()

    def test_protocolo_bloqueia_acesso_a_core(self):
        resultado = verificar_acao(
            TipoAcao.CRIAR_ARQUIVO,
            "core/novo.py",
        )

        self.assertFalse(resultado.permitida)

    def test_codigo_gerado_nao_pode_importar_core(self):
        resultado = validar_codigo_gerado(
            "from core.validador import validar\n"
        )

        self.assertFalse(resultado.permitida)
        self.assertIn("core", resultado.mensagem)

    def test_ferramentas_nao_importam_core(self):
        pasta_ferramentas = Path(__file__).resolve().parents[1] / "ferramentas"
        for arquivo in pasta_ferramentas.glob("*.py"):
            texto = arquivo.read_text(encoding="utf-8")
            self.assertNotIn("import core", texto, str(arquivo))
            self.assertNotIn("from core", texto, str(arquivo))

    def test_controlador_cria_modulo_e_restauracao_reverte_falha(self):
        with tempfile.TemporaryDirectory() as pasta:
            projeto = Path(pasta)
            codigo_original = (
                "class CategoriaTeste:\n"
                "    valor = 'estável'\n"
            )
            criado = aplicar_codigo_gerado(
                "teste.py",
                codigo_original,
                projeto_dir=projeto,
                permissao=emitir_permissao(
                    TipoAcao.CRIAR_ARQUIVO,
                    f"{ALVO_GERADO_ROOT}/teste.py",
                ),
            )
            self.assertTrue(criado.sucesso, criado.mensagem)
            self.assertEqual(
                (projeto / "aprendizado" / "gerado" / "teste.py").read_text(
                    encoding="utf-8"
                ),
                codigo_original,
            )

            falho = aplicar_codigo_gerado(
                "teste.py",
                "raise RuntimeError('erro proposital')\n",
                projeto_dir=projeto,
                permissao=emitir_permissao(
                    TipoAcao.EDITAR_ARQUIVO,
                    f"{ALVO_GERADO_ROOT}/teste.py",
                ),
            )
            self.assertFalse(falho.sucesso)
            self.assertEqual(
                (projeto / "aprendizado" / "gerado" / "teste.py").read_text(
                    encoding="utf-8"
                ),
                codigo_original,
            )
