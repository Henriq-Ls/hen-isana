import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bancos.conhecimento import ConhecimentoDB
from bancos.propostas_aprendizagem import PropostasAprendizagem
from main import processar_frase
from protocolo.regras import ALVO_CONHECIMENTO, TipoAcao
from protocolo.verificador import emitir_permissao


class TestPropostasAprendizagem(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.caminho_db = Path(self.pasta.name) / "conhecimento.db"
        self.banco = ConhecimentoDB(self.caminho_db)
        self.propostas = PropostasAprendizagem(self.banco)

    def tearDown(self):
        self.banco.fechar()
        self.pasta.cleanup()

    @staticmethod
    def permissao():
        return emitir_permissao(
            TipoAcao.SALVAR_CONHECIMENTO,
            ALVO_CONHECIMENTO,
        )

    def test_proposta_de_termo_nao_grava_antes_de_aprovacao_e_aplicacao(self):
        proposta = self.propostas.propor_termo(
            "bússola",
            {"significado": "Instrumento de orientação."},
            motivo="Uma conversa indicou esta definição.",
            origem="conversa: usuário",
        )

        self.assertEqual(proposta.estado, "proposta")
        self.assertEqual(proposta.acao, "inclusao")
        self.assertEqual(proposta.motivo, "Uma conversa indicou esta definição.")
        self.assertEqual(proposta.origem, "conversa: usuário")
        self.assertEqual(self.banco.buscar_termo("bússola"), [])

        aprovada = self.propostas.aprovar(proposta.id)
        self.assertEqual(aprovada.estado, "aprovada")
        self.assertEqual(self.banco.buscar_termo("bússola"), [])

        aplicada = self.propostas.aplicar(
            proposta.id,
            permissao=self.permissao(),
        )
        self.assertEqual(aplicada.estado, "aplicada")
        self.assertEqual(
            self.banco.buscar_termo_confirmado("bússola")[0].significado,
            "Instrumento de orientação.",
        )
        self.assertEqual(
            self.banco.identificar_lacunas("bússola"),
            ["exemplo_uso"],
        )
        resposta = processar_frase(
            "bússola",
            self.banco,
            modo_aprendizagem=False,
        )
        self.assertIn("Instrumento de orientação.", resposta[0])

    def test_correcao_de_termo_tem_reversao_auditavel(self):
        original = self.banco.salvar_termo(
            "bússola",
            significado="Instrumento para ler mapas.",
            contexto_uso="navegação",
            permissao=self.permissao(),
        )
        proposta = self.propostas.propor_termo(
            "bússola",
            {"significado": "Instrumento de orientação."},
            contexto_alvo="navegação",
            motivo="A definição anterior foi corrigida.",
            origem="conversa: usuário",
        )

        self.assertEqual(proposta.acao, "correcao")
        self.assertEqual(proposta.entidade_id, original.id)
        self.propostas.aprovar(proposta.id)
        self.propostas.aplicar(proposta.id, permissao=self.permissao())
        self.assertEqual(
            self.banco.buscar_termo_confirmado("bússola", "navegação")[0]
            .significado,
            "Instrumento de orientação.",
        )

        revertida = self.propostas.reverter(
            proposta.id,
            permissao=self.permissao(),
        )
        self.assertEqual(revertida.estado, "revertida")
        self.assertEqual(
            self.banco.buscar_termo_confirmado("bússola", "navegação")[0]
            .significado,
            "Instrumento para ler mapas.",
        )
        self.assertTrue(
            any(
                evidencia.valor == "Instrumento de orientação."
                and evidencia.estado == "revertida"
                for evidencia in self.banco.listar_evidencias("bússola")
            )
        )

    def test_fato_proposto_so_fica_consultavel_depois_da_aplicacao(self):
        proposta = self.propostas.propor_fato(
            "A capital do Brasil é Brasília.",
            "geografia",
            motivo="A conversa corrigiu a informação.",
            origem="conversa: usuário",
        )
        self.assertEqual(self.banco.buscar_fatos(), [])

        self.propostas.aprovar(proposta.id)
        self.assertEqual(self.banco.buscar_fatos_confirmados(), [])
        aplicada = self.propostas.aplicar(
            proposta.id,
            permissao=self.permissao(),
        )
        self.assertEqual(aplicada.estado, "aplicada")
        fato = self.banco.buscar_fatos_confirmados("geografia")[0]
        self.assertEqual(fato.afirmacao, "A capital do Brasil é Brasília.")
        self.assertEqual(fato.origem, "proposta:1:conversa: usuário")
        resposta = processar_frase(
            "Qual é a capital do Brasil?",
            self.banco,
            modo_aprendizagem=False,
        )
        self.assertIn("Brasília", resposta[0])

        revertida = self.propostas.reverter(
            proposta.id,
            permissao=self.permissao(),
        )
        self.assertEqual(revertida.estado, "revertida")
        self.assertEqual(self.banco.buscar_fatos_confirmados(), [])
        self.assertEqual(self.banco.buscar_fatos()[0].estado, "revertida")

    def test_correcao_de_fato_preserva_a_versao_anterior_e_reverte(self):
        anterior = self.banco.salvar_fato(
            "A capital do Brasil é Rio de Janeiro.",
            "geografia",
            permissao=self.permissao(),
        )
        proposta = self.propostas.propor_fato(
            "A capital do Brasil é Brasília.",
            "geografia",
            fato_id=anterior.id,
            motivo="Foi identificada uma informação anterior incorreta.",
            origem="conversa: usuário",
        )
        self.assertEqual(proposta.antes["afirmacao"], anterior.afirmacao)
        self.assertEqual(
            self.banco.buscar_fatos_confirmados()[0].afirmacao,
            anterior.afirmacao,
        )

        self.propostas.aprovar(proposta.id)
        self.propostas.aplicar(proposta.id, permissao=self.permissao())
        self.assertEqual(
            self.banco.buscar_fatos_confirmados()[0].afirmacao,
            "A capital do Brasil é Brasília.",
        )
        self.assertEqual(len(self.banco.listar_evidencias_fato(anterior.id)), 2)

        self.propostas.reverter(proposta.id, permissao=self.permissao())
        self.assertEqual(
            self.banco.buscar_fatos_confirmados()[0].afirmacao,
            anterior.afirmacao,
        )
        self.assertEqual(len(self.banco.listar_evidencias_fato(anterior.id)), 2)

    def test_fato_revertido_nao_bloqueia_uma_nova_proposta(self):
        conteudo = ("Um fato que precisou ser corrigido.", "teste")
        primeira = self.propostas.propor_fato(
            conteudo[0],
            conteudo[1],
            motivo="Primeira confirmação.",
            origem="conversa: usuário",
        )
        self.propostas.aprovar(primeira.id)
        self.propostas.aplicar(primeira.id, permissao=self.permissao())
        self.propostas.reverter(primeira.id, permissao=self.permissao())

        segunda = self.propostas.propor_fato(
            conteudo[0],
            conteudo[1],
            motivo="Nova confirmação após revisão.",
            origem="conversa: usuário",
        )
        self.propostas.aprovar(segunda.id)
        self.propostas.aplicar(segunda.id, permissao=self.permissao())

        self.assertEqual(self.propostas.obter(segunda.id).estado, "aplicada")
        self.assertEqual(
            self.banco.buscar_fatos_confirmados("teste")[0].afirmacao,
            conteudo[0],
        )

    def test_conflito_apos_proposta_bloqueia_aplicacao_sem_sobrescrever(self):
        original = self.banco.salvar_fato(
            "A reunião é na terça-feira.",
            "agenda",
            permissao=self.permissao(),
        )
        proposta = self.propostas.propor_fato(
            "A reunião é na quarta-feira.",
            "agenda",
            fato_id=original.id,
            motivo="Correção recebida.",
            origem="conversa: usuário",
        )
        self.propostas.aprovar(proposta.id)
        self.banco.salvar_fato(
            "A reunião é na quinta-feira.",
            "agenda",
            fato_id=original.id,
            permissao=self.permissao(),
        )

        with self.assertRaisesRegex(ValueError, "mudou desde a proposta"):
            self.propostas.aplicar(proposta.id, permissao=self.permissao())

        self.assertEqual(
            self.banco.buscar_fatos_confirmados()[0].afirmacao,
            "A reunião é na quinta-feira.",
        )
        self.assertEqual(self.propostas.obter(proposta.id).estado, "aprovada")

    def test_rejeicao_registra_resultado_sem_aplicar_conteudo(self):
        proposta = self.propostas.propor_fato(
            "Um dado não confirmado.",
            "teste",
            motivo="Proposta de teste.",
            origem="conversa: usuário",
        )

        recusada = self.propostas.recusar(
            proposta.id,
            "A informação não foi confirmada.",
        )

        self.assertEqual(recusada.estado, "recusada")
        self.assertEqual(recusada.resultado, "A informação não foi confirmada.")
        self.assertEqual(self.banco.buscar_fatos(), [])

    def test_proposta_e_resultado_persistem_apos_reabrir_o_banco(self):
        proposta = self.propostas.propor_fato(
            "Uma afirmação para auditoria.",
            "teste",
            motivo="Motivo preservado.",
            origem="origem preservada",
        )
        self.propostas.recusar(proposta.id, "Resultado preservado.")
        self.banco.fechar()

        self.banco = ConhecimentoDB(self.caminho_db)
        self.propostas = PropostasAprendizagem(self.banco)
        persistida = self.propostas.obter(proposta.id)

        self.assertEqual(persistida.estado, "recusada")
        self.assertEqual(persistida.motivo, "Motivo preservado.")
        self.assertEqual(persistida.origem, "origem preservada")
        self.assertEqual(persistida.resultado, "Resultado preservado.")

    def test_reversao_nao_sobrescreve_alteracao_posterior(self):
        proposta = self.propostas.propor_termo(
            "termo",
            {"significado": "Definição proposta."},
            motivo="Teste de conflito na reversão.",
            origem="teste",
        )
        self.propostas.aprovar(proposta.id)
        self.propostas.aplicar(proposta.id, permissao=self.permissao())
        self.banco.salvar_termo(
            "termo",
            significado="Atualização posterior.",
            permissao=self.permissao(),
        )

        with self.assertRaisesRegex(ValueError, "mudou após a aplicação"):
            self.propostas.reverter(
                proposta.id,
                permissao=self.permissao(),
            )
        self.assertEqual(
            self.banco.buscar_termo_confirmado("termo")[0].significado,
            "Atualização posterior.",
        )
        self.assertEqual(self.propostas.obter(proposta.id).estado, "aplicada")

    def test_aplicacao_exige_permissao_de_escrita(self):
        proposta = self.propostas.propor_fato(
            "Fato pendente.",
            "teste",
            motivo="Teste de autorização.",
            origem="teste",
        )
        self.propostas.aprovar(proposta.id)

        with patch("protocolo.verificador._registrar_bloqueio"):
            with self.assertRaises(PermissionError):
                self.propostas.aplicar(proposta.id, permissao=None)

        self.assertEqual(self.banco.buscar_fatos(), [])
        self.assertEqual(self.propostas.obter(proposta.id).estado, "aprovada")

    def test_conversa_somente_leitura_nao_cria_propostas(self):
        resultado = processar_frase(
            "proposta-fato: A capital do Brasil é Brasília.",
            self.banco,
            modo_aprendizagem=False,
            propostas=self.propostas,
        )

        self.assertIn("somente leitura", resultado[0])
        self.assertEqual(self.propostas.listar(), [])
        self.assertEqual(self.banco.buscar_fatos(), [])

    def test_comandos_criam_aprovam_e_aplicam_somente_por_acao_explicita(self):
        respostas = iter(
            ["geografia", "Correção informada pelo usuário.", "usuário"]
        )
        criada = processar_frase(
            "proposta-fato: A capital do Brasil é Brasília.",
            self.banco,
            perguntar=lambda _mensagem: next(respostas),
            modo_aprendizagem=True,
            propostas=self.propostas,
        )
        self.assertIn("nada foi gravado", criada[0])
        proposta = self.propostas.listar()[0]
        self.assertEqual(proposta.estado, "proposta")
        self.assertEqual(self.banco.buscar_fatos(), [])

        aprovada = processar_frase(
            f"aprovar-proposta: {proposta.id}",
            self.banco,
            modo_aprendizagem=True,
            propostas=self.propostas,
        )
        self.assertIn("ainda não foi aplicada", aprovada[0])
        self.assertEqual(self.banco.buscar_fatos(), [])

        aplicada = processar_frase(
            f"aplicar-proposta: {proposta.id}",
            self.banco,
            modo_aprendizagem=True,
            permissao_memoria=self.permissao(),
            propostas=self.propostas,
        )
        self.assertIn("conhecimento confirmado", aplicada[0])
        self.assertEqual(len(self.banco.buscar_fatos_confirmados()), 1)

    def test_comando_explicito_cria_proposta_de_correcao_de_termo(self):
        original = self.banco.salvar_termo(
            "termômetro",
            significado="Um instrumento.",
            contexto_uso="ciência",
            permissao=self.permissao(),
        )
        respostas = iter(["Correção apoiada por exemplo de uso.", "usuário"])

        resultado = processar_frase(
            "proposta-termo: termômetro | significado | "
            "Instrumento que mede temperatura. | ciência",
            self.banco,
            perguntar=lambda _mensagem: next(respostas),
            modo_aprendizagem=True,
            propostas=self.propostas,
        )

        proposta = self.propostas.listar()[0]
        self.assertIn("nada foi gravado", resultado[0])
        self.assertEqual(proposta.entidade_id, original.id)
        self.assertEqual(proposta.acao, "correcao")
        self.assertEqual(
            self.banco.buscar_termo_confirmado("termômetro", "ciência")[0]
            .significado,
            "Um instrumento.",
        )

    def test_propostas_de_codigo_sao_rejeitadas_sem_alterar_arquivos(self):
        with self.assertRaisesRegex(PermissionError, "não são aceitas"):
            self.propostas.propor_codigo(
                "core/controlador.py",
                diff="+ código",
            )
        self.assertEqual(self.propostas.listar(), [])


if __name__ == "__main__":
    unittest.main()