import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bancos.conhecimento import ConhecimentoDB
from main import aprender_termo, processar_frase, tokenizar
from protocolo.regras import ALVO_CONHECIMENTO, TipoAcao
from protocolo.verificador import emitir_permissao


class TestAprendizagemAdaptativa(unittest.TestCase):
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

    def test_termo_novo_pergunta_somente_significado_e_exemplo(self):
        perguntas = []
        respostas = iter(
            [
                "Um instrumento de medição.",
                "O termômetro indica a temperatura.",
            ]
        )

        entrada = aprender_termo(
            "termômetro",
            self.banco,
            perguntar=lambda mensagem: perguntas.append(mensagem)
            or next(respostas),
            permissao_memoria=self._permissao_memoria(),
        )

        self.assertEqual(len(perguntas), 2)
        self.assertIn("significa", perguntas[0])
        self.assertIn("exemplo", perguntas[1])
        self.assertTrue(entrada.completa)
        self.assertEqual(entrada.significado, "Um instrumento de medição.")
        self.assertEqual(
            entrada.exemplo_uso,
            "O termômetro indica a temperatura.",
        )
        self.assertIsNone(entrada.tipo)
        self.assertIsNone(entrada.resposta_padrao)

    def test_pergunta_apenas_a_lacuna_que_ainda_falta(self):
        self.banco.salvar_termo(
            "bússola",
            significado="Instrumento de orientação.",
            permissao=self._permissao_memoria(),
        )
        perguntas = []

        entrada = aprender_termo(
            "bússola",
            self.banco,
            perguntar=lambda mensagem: perguntas.append(mensagem)
            or "A bússola aponta direções.",
            permissao_memoria=self._permissao_memoria(),
        )

        self.assertEqual(len(perguntas), 1)
        self.assertIn("exemplo", perguntas[0])
        self.assertEqual(entrada.significado, "Instrumento de orientação.")
        self.assertEqual(entrada.exemplo_uso, "A bússola aponta direções.")

    def test_aprendizagem_pede_escolha_entre_sentidos_existentes(self):
        self.banco.salvar_termo(
            "manga",
            significado="Fruta tropical.",
            contexto_uso="alimentação",
            permissao=self._permissao_memoria(),
        )
        self.banco.salvar_termo(
            "manga",
            significado="Parte da roupa que cobre o braço.",
            contexto_uso="vestuário",
            permissao=self._permissao_memoria(),
        )
        perguntas = []

        entrada = aprender_termo(
            "manga",
            self.banco,
            perguntar=lambda mensagem: perguntas.append(mensagem) or "2",
            permissao_memoria=self._permissao_memoria(),
        )

        self.assertEqual(len(perguntas), 1)
        self.assertIn("mais de um sentido", perguntas[0])
        self.assertEqual(entrada.contexto_uso, "vestuário")
        self.assertEqual(
            entrada.significado,
            "Parte da roupa que cobre o braço.",
        )

    def test_modo_conversa_exibe_ambiguidade_sem_escolher_sentido(self):
        self.banco.salvar_termo(
            "manga",
            significado="Fruta tropical.",
            contexto_uso="alimentação",
            permissao=self._permissao_memoria(),
        )
        self.banco.salvar_termo(
            "manga",
            significado="Parte da roupa que cobre o braço.",
            contexto_uso="vestuário",
            permissao=self._permissao_memoria(),
        )
        perguntas = []

        respostas = processar_frase(
            "manga",
            self.banco,
            perguntar=lambda mensagem: perguntas.append(mensagem) or "1",
            modo_aprendizagem=False,
            projeto_dir=self.projeto,
        )

        self.assertEqual(perguntas, [])
        self.assertEqual(len(respostas), 1)
        self.assertIn("mais de um sentido", respostas[0])
        self.assertIn("alimentação", respostas[0])
        self.assertIn("vestuário", respostas[0])
        self.assertEqual(len(self.banco.buscar_termo("manga")), 2)

    def test_respostas_vazias_repetem_a_pergunta_da_lacuna(self):
        respostas = iter(
            [
                "",
                "Uma forma de comunicação.",
                "",
                "A mensagem chegou pelo rádio.",
            ]
        )
        perguntas = []

        entrada = aprender_termo(
            "mensagem",
            self.banco,
            perguntar=lambda mensagem: perguntas.append(mensagem)
            or next(respostas),
            permissao_memoria=self._permissao_memoria(),
        )

        self.assertEqual(len(perguntas), 4)
        self.assertEqual(perguntas[0], perguntas[1])
        self.assertEqual(perguntas[2], perguntas[3])
        self.assertEqual(entrada.significado, "Uma forma de comunicação.")
        self.assertEqual(
            entrada.exemplo_uso,
            "A mensagem chegou pelo rádio.",
        )

    def test_rejeita_comando_desalinhado_antes_de_gravar_o_termo(self):
        perguntas = []
        respostas = iter(
            [
                "termo: latitude",
                "Uma coordenada geográfica.",
                "A latitude indica a posição ao norte ou ao sul.",
            ]
        )

        entrada = aprender_termo(
            "latitude",
            self.banco,
            perguntar=lambda mensagem: perguntas.append(mensagem)
            or next(respostas),
            permissao_memoria=self._permissao_memoria(),
        )

        self.assertEqual(len(perguntas), 3)
        self.assertEqual(entrada.significado, "Uma coordenada geográfica.")
        self.assertNotIn("termo:", entrada.significado)
        self.assertEqual(
            self.banco.buscar_termo("latitude")[0].exemplo_uso,
            "A latitude indica a posição ao norte ou ao sul.",
        )

    def test_rejeita_eco_do_termo_e_nome_do_campo(self):
        respostas = iter(
            [
                "latitude",
                "significado",
                "Uma coordenada geográfica.",
                "A latitude indica a posição ao norte ou ao sul.",
            ]
        )

        entrada = aprender_termo(
            "latitude",
            self.banco,
            perguntar=lambda _mensagem: next(respostas),
            permissao_memoria=self._permissao_memoria(),
        )

        self.assertEqual(entrada.significado, "Uma coordenada geográfica.")
        self.assertEqual(
            entrada.exemplo_uso,
            "A latitude indica a posição ao norte ou ao sul.",
        )
        self.assertNotEqual(entrada.significado, "latitude")
        self.assertNotEqual(entrada.significado, "significado")

    def test_expressao_composta_e_preservada_no_modo_explicito(self):
        respostas = iter(
            [
                "Método para fazer sistemas aprenderem com dados.",
                "Aprendizado de máquina identifica padrões em exemplos.",
            ]
        )

        resultado = processar_frase(
            "termo: aprendizado de máquina",
            self.banco,
            perguntar=lambda _mensagem: next(respostas),
            projeto_dir=self.projeto,
            permissao_memoria=self._permissao_memoria(),
        )

        entrada = self.banco.buscar_termo("aprendizado de máquina")
        self.assertEqual(len(entrada), 1)
        self.assertEqual(entrada[0].termo, "aprendizado de máquina")
        self.assertEqual(
            entrada[0].significado,
            "Método para fazer sistemas aprenderem com dados.",
        )
        self.assertEqual(
            tokenizar(
                "aprendizado de máquina",
                self.banco.listar_expressoes_compostas(),
            ),
            ["aprendizado de máquina"],
        )
        self.assertIn("Termo registrado", resultado[0])

    def test_fato_novo_e_exibido_estruturado_antes_da_confirmacao(self):
        perguntas = []
        respostas = iter(["geografia", "sim"])

        resultado = processar_frase(
            "fato: A capital do Brasil é Brasília.",
            self.banco,
            perguntar=lambda mensagem: perguntas.append(mensagem)
            or next(respostas),
            projeto_dir=self.projeto,
            permissao_memoria=self._permissao_memoria(),
        )

        fatos = self.banco.buscar_fatos("geografia")
        self.assertEqual(len(fatos), 1)
        self.assertEqual(
            fatos[0].afirmacao,
            "A capital do Brasil é Brasília.",
        )
        self.assertEqual(self.banco.buscar_termo("capital"), [])
        self.assertIn("Proposta estruturada", perguntas[-1])
        self.assertIn("afirmação:", perguntas[-1])
        self.assertIn("contexto:", perguntas[-1])
        self.assertIn("Confirma?", perguntas[-1])
        self.assertIn("Fato registrado", resultado[0])

    def test_correcao_de_fato_exibe_valor_anterior_e_atualiza_com_confirmacao(self):
        original = self.banco.salvar_fato(
            "A capital do Brasil é Rio de Janeiro.",
            "geografia",
            permissao=self._permissao_memoria(),
        )
        perguntas = []
        respostas = iter(["geografia", "1", "sim"])

        processar_frase(
            "fato: A capital do Brasil é Brasília.",
            self.banco,
            perguntar=lambda mensagem: perguntas.append(mensagem)
            or next(respostas),
            projeto_dir=self.projeto,
            permissao_memoria=self._permissao_memoria(),
        )

        fatos = self.banco.buscar_fatos("geografia")
        self.assertEqual(len(fatos), 1)
        self.assertEqual(fatos[0].id, original.id)
        self.assertEqual(
            fatos[0].afirmacao,
            "A capital do Brasil é Brasília.",
        )
        self.assertIn("Corrigir:", perguntas[1])
        self.assertIn(
            "A capital do Brasil é Rio de Janeiro.",
            perguntas[-1],
        )
        self.assertIn("→", perguntas[-1])
        self.assertEqual(len(self.banco.listar_evidencias_fato(original.id)), 2)

    def test_escolha_ambigua_de_fato_permite_adicionar_sem_sobrescrever(self):
        primeiro = self.banco.salvar_fato(
            "A água ferve a 100 graus Celsius.",
            "ciência",
            permissao=self._permissao_memoria(),
        )
        segundo = self.banco.salvar_fato(
            "A água congela a 0 graus Celsius.",
            "ciência",
            permissao=self._permissao_memoria(),
        )
        respostas = iter(["ciência", "não é número", "0", "sim"])

        processar_frase(
            "fato: A água evapora com o calor.",
            self.banco,
            perguntar=lambda _mensagem: next(respostas),
            projeto_dir=self.projeto,
            permissao_memoria=self._permissao_memoria(),
        )

        fatos = self.banco.buscar_fatos("ciência")
        self.assertEqual(len(fatos), 3)
        self.assertEqual(fatos[0].id, primeiro.id)
        self.assertEqual(fatos[0].afirmacao, "A água ferve a 100 graus Celsius.")
        self.assertEqual(fatos[1].id, segundo.id)

    def test_cancelamento_de_informacao_incompleta_nao_grava_fato(self):
        respostas = iter(["", "cancelar"])

        resultado = processar_frase(
            "fato: Uma afirmação ainda sem contexto.",
            self.banco,
            perguntar=lambda _mensagem: next(respostas),
            projeto_dir=self.projeto,
            permissao_memoria=self._permissao_memoria(),
        )

        self.assertIn("cancelada", resultado[0].casefold())
        self.assertEqual(self.banco.buscar_fatos(), [])

    def test_cancelamento_da_confirmacao_nao_grava_fato(self):
        respostas = iter(["geografia", "cancelar"])

        resultado = processar_frase(
            "fato: Uma afirmação para confirmação.",
            self.banco,
            perguntar=lambda _mensagem: next(respostas),
            projeto_dir=self.projeto,
            permissao_memoria=self._permissao_memoria(),
        )

        self.assertIn("foi gravado", resultado[0].casefold())
        self.assertEqual(self.banco.buscar_fatos(), [])

    def test_proposta_de_termo_incerta_recusada_nao_e_gravada(self):
        perguntas = []
        respostas = iter(
            [
                "Talvez seja um instrumento de navegação.",
                "A bússola aparece em mapas antigos.",
                "não",
            ]
        )

        entrada = aprender_termo(
            "bússola",
            self.banco,
            perguntar=lambda mensagem: perguntas.append(mensagem)
            or next(respostas),
            permissao_memoria=self._permissao_memoria(),
        )

        self.assertIsNone(entrada)
        self.assertEqual(self.banco.buscar_termo("bússola"), [])
        self.assertIn("Proposta estruturada", perguntas[-1])
        self.assertIn("marcador de incerteza", perguntas[-1])

    def test_cancelamento_durante_termo_nao_persiste_respostas_parciais(self):
        respostas = iter(
            [
                "Um conceito em construção.",
                "cancelar",
            ]
        )

        resultado = processar_frase(
            "termo: conceito incompleto",
            self.banco,
            perguntar=lambda _mensagem: next(respostas),
            projeto_dir=self.projeto,
            permissao_memoria=self._permissao_memoria(),
        )

        self.assertIn("cancelada", resultado[0].casefold())
        self.assertEqual(self.banco.buscar_termo("conceito incompleto"), [])


if __name__ == "__main__":
    unittest.main()