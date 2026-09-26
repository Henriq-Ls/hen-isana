"""Testes obrigatórios da resposta baseada em estrutura da Fase 3.6."""

from __future__ import annotations

from hashlib import sha256
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aplicacao.resposta_estruturada import (  # noqa: E402
    gerar_resposta_com_fallback,
)
from aplicacao.modo_sombra import (  # noqa: E402
    processar_frase_com_plano_estruturado,
)
from core.contratos import (  # noqa: E402
    AlvoSemantico,
    IntencaoIntermediaria,
    PredicadoSemantico,
    ProposicaoIntermediaria,
)
from core.inferencia_simbolica import (  # noqa: E402
    AfirmacaoSimbolica,
    LiteralSimbolico,
    MotorInferenciaSimbolica,
    RegraSimbolica,
)
from core.resposta_estruturada import (  # noqa: E402
    EvidenciaResposta,
    EtapaResposta,
    EstruturaRespostaIncompleta,
    PlanoResposta,
    RespostaEstruturada,
    ResultadoEstruturado,
    gerar_resposta_estruturada,
)


ROOT = Path(__file__).resolve().parents[1]


def intencao(objetivo: str = "consultar a estrutura") -> IntencaoIntermediaria:
    return IntencaoIntermediaria(
        tipo_ato="consulta",
        objetivo=objetivo,
    )


def resultado(
    texto: str = "A resposta veio da estrutura.",
    *,
    evidencias: tuple[str, ...] = ("ev-1",),
    estado: str = "confirmado",
) -> ResultadoEstruturado:
    return ResultadoEstruturado(
        resultado_id="res-1",
        texto=texto,
        origem="recuperacao",
        estado=estado,
        evidencia_ids=evidencias,
    )


def evidencia(
    trecho: str = "trecho factual fornecido",
    *,
    origem: str = "fonte-controlada",
) -> EvidenciaResposta:
    return EvidenciaResposta(
        evidencia_id="ev-1",
        origem=origem,
        trecho=trecho,
    )


def plano(
    etapas: tuple[EtapaResposta, ...] = (
        EtapaResposta("resultados", ("res-1",)),
    ),
    *,
    resultados: tuple[ResultadoEstruturado, ...] = (resultado(),),
    evidencias: tuple[EvidenciaResposta, ...] = (evidencia(),),
    **kwargs,
) -> PlanoResposta:
    return PlanoResposta(
        plano_id="plano-teste",
        intencao=intencao(),
        etapas=etapas,
        resultados=resultados,
        evidencias=evidencias,
        idempotencia="chave-teste",
        **kwargs,
    )


def proposicao() -> ProposicaoIntermediaria:
    return ProposicaoIntermediaria(
        proposicao_id="prop-1",
        predicado=PredicadoSemantico(
            tipo="estado",
            sentido=AlvoSemantico("sentido", "sentido:estado"),
        ),
    )


def afirmacao(
    chave: str,
    polaridade: str = "positiva",
    *,
    estado: str = "confirmada",
    origem: str = "usuario",
    evidencia_ids: tuple[str, ...] = ("ev-1",),
    referencia: str | None = None,
) -> AfirmacaoSimbolica:
    return AfirmacaoSimbolica(
        literal=LiteralSimbolico(chave, polaridade),
        estado=estado,
        origem=origem,
        evidencia_ids=evidencia_ids,
        referencia=referencia,
    )


class TestRespostaEstruturadaFase36(unittest.TestCase):
    def test_resposta_simples_baseada_em_estrutura(self):
        resposta = gerar_resposta_estruturada(plano())

        self.assertIsInstance(resposta, RespostaEstruturada)
        self.assertIn("A resposta veio da estrutura.", resposta.resultado.texto)
        self.assertNotIn("frase original", resposta.resultado.texto)

    def test_resposta_baseada_em_proposicao(self):
        resposta = gerar_resposta_estruturada(
            plano(
                etapas=(EtapaResposta("proposicoes", ("prop-1",)),),
                resultados=(),
                evidencias=(),
                proposicoes=(proposicao(),),
            )
        )

        self.assertIn("Proposição prop-1", resposta.resultado.texto)
        self.assertIn("modalidade assertiva", resposta.resultado.texto)

    def test_resposta_utiliza_evidencia(self):
        resposta = gerar_resposta_estruturada(
            plano(
                etapas=(EtapaResposta("evidencias", ("ev-1",)),),
            )
        )

        self.assertIn("Evidência ev-1", resposta.resultado.texto)
        self.assertIn("trecho factual fornecido", resposta.resultado.texto)
        self.assertEqual(resposta.evidencias[0].origem, "fonte-controlada")

    def test_resposta_contem_incerteza(self):
        resposta = gerar_resposta_estruturada(
            plano(
                etapas=(EtapaResposta("incertezas"),),
                resultados=(),
                evidencias=(),
                incertezas=("a fonte não foi confirmada",),
                estado_informacao="parcial",
            )
        )

        self.assertIn("Incerteza: a fonte não foi confirmada.", resposta.resultado.texto)
        self.assertIn("Estado da informação: parcial.", resposta.resultado.texto)
        self.assertEqual(resposta.resultado.incertezas, ("a fonte não foi confirmada",))

    def test_resposta_contem_conflito_sem_escolher_lado(self):
        conflito = (
            AfirmacaoSimbolica(
                LiteralSimbolico("porta-aberta", "positiva"),
                evidencia_ids=("ev-p",),
            ),
            AfirmacaoSimbolica(
                LiteralSimbolico("porta-aberta", "negativa"),
                evidencia_ids=("ev-n",),
            ),
        )
        from core.inferencia_simbolica import ConflitoSimbolico

        resposta = gerar_resposta_estruturada(
            plano(
                etapas=(EtapaResposta("conflitos", ("porta-aberta",)),),
                resultados=(),
                evidencias=(),
                conflitos=(ConflitoSimbolico("porta-aberta", conflito),),
            )
        )

        texto = resposta.resultado.texto
        self.assertIn("Conflito preservado em porta-aberta", texto)
        self.assertIn("positiva", texto)
        self.assertIn("negativa", texto)
        self.assertIn("nenhum lado foi escolhido", texto)

    def test_resposta_contem_conclusao_inferida(self):
        derivacao = MotorInferenciaSimbolica(
            (
                RegraSimbolica(
                    "regra-p-q",
                    LiteralSimbolico("p"),
                    LiteralSimbolico("q"),
                    evidencia_ids=("ev-regra",),
                ),
            )
        ).inferir((afirmacao("p"),)).inferencias[0]

        resposta = gerar_resposta_estruturada(
            plano(
                etapas=(EtapaResposta("inferencias", (derivacao.inferencia_id,)),),
                resultados=(),
                evidencias=(),
                inferencias=(derivacao,),
            )
        )

        texto = resposta.resultado.texto
        self.assertIn("Conclusão derivada: q", texto)
        self.assertIn("premissas: p", texto)
        self.assertIn("origem: inferencia", texto)
        self.assertNotIn("Conclusão confirmada", texto)

    def test_preserva_proveniencia(self):
        derivacao = MotorInferenciaSimbolica(
            (
                RegraSimbolica(
                    "regra-p-q",
                    LiteralSimbolico("p"),
                    LiteralSimbolico("q"),
                    origem="regra-cadastrada",
                ),
            )
        ).inferir((afirmacao("p"),)).inferencias[0]
        resposta = gerar_resposta_estruturada(
            plano(
                etapas=(
                    EtapaResposta("resultados", ("res-1",)),
                    EtapaResposta("inferencias", (derivacao.inferencia_id,)),
                ),
                inferencias=(derivacao,),
            )
        )

        self.assertEqual(resposta.proveniencias, ("recuperacao", "fonte-controlada", "regra-cadastrada"))
        self.assertIn("origem da regra: regra-cadastrada", resposta.resultado.texto)
        self.assertEqual(resposta.inferencias[0].conclusao.origem, "inferencia")

    def test_ausencia_de_informacao_nao_inventa(self):
        resposta = gerar_resposta_estruturada(
            plano(
                etapas=(EtapaResposta("ausencia"),),
                resultados=(),
                evidencias=(),
                estado_informacao="indisponivel",
                motivo_ausencia="nenhum registro compatível foi fornecido",
            )
        )

        self.assertIn(
            "Informação não disponível: nenhum registro compatível foi fornecido.",
            resposta.resultado.texto,
        )
        self.assertNotIn("valor inventado", resposta.resultado.texto)

    def test_estrutura_incompleta_e_rejeitada(self):
        resposta = plano(
            etapas=(EtapaResposta("resultados"),),
            resultados=(),
            evidencias=(),
        )

        with self.assertRaises(EstruturaRespostaIncompleta):
            gerar_resposta_estruturada(resposta)

    def test_fallback_para_legado_e_registrado(self):
        chamadas: list[str] = []
        resposta = gerar_resposta_com_fallback(
            plano(
                etapas=(EtapaResposta("resultados"),),
                resultados=(),
                evidencias=(),
            ),
            lambda: chamadas.append("legado") or "resposta legada",
        )

        self.assertEqual(resposta.resposta, "resposta legada")
        self.assertEqual(chamadas, ["legado"])
        self.assertTrue(resposta.registro.fallback)
        self.assertEqual(resposta.registro.status, "fallback_incompleta")
        self.assertIsNotNone(resposta.registro.motivo)

    def test_falha_do_novo_gerador_faz_fallback(self):
        chamadas: list[str] = []

        def gerador_falho(_plano):
            raise RuntimeError("falha controlada")

        resposta = gerar_resposta_com_fallback(
            plano(),
            lambda: chamadas.append("legado") or {"legado": True},
            gerador=gerador_falho,
        )

        self.assertEqual(resposta.resposta, {"legado": True})
        self.assertEqual(chamadas, ["legado"])
        self.assertEqual(resposta.registro.status, "fallback_falha")
        self.assertIn("falha controlada", resposta.registro.motivo or "")

    def test_idempotencia(self):
        primeira = gerar_resposta_estruturada(plano())
        segunda = gerar_resposta_estruturada(plano())

        self.assertEqual(primeira, segunda)
        self.assertEqual(primeira.idempotencia, "chave-teste")

    def test_ausencia_de_escrita_indevida(self):
        banco = ROOT / "aprendizado" / "bancos" / "linguagem.db"
        antes = sha256(banco.read_bytes()).digest() if banco.exists() else None

        gerar_resposta_estruturada(plano())

        depois = sha256(banco.read_bytes()).digest() if banco.exists() else None
        self.assertEqual(antes, depois)

    def test_conteudo_textual_e_tratado_apenas_como_dado(self):
        marcador = "__import__('os').system('nao-executar')"
        resposta = gerar_resposta_estruturada(
            plano(
                etapas=(EtapaResposta("evidencias", ("ev-1",)),),
                resultados=(),
                evidencias=(evidencia(marcador),),
            )
        )

        self.assertIn(marcador, resposta.resultado.texto)
        self.assertNotIn("nao-executar", resposta.proveniencias)

    def test_nao_reinterpreta_a_frase_original(self):
        resposta = gerar_resposta_estruturada(
            plano(
                etapas=(EtapaResposta("resultados", ("res-1",)),),
                resultados=(
                    resultado("Somente o conteúdo estruturado deve aparecer."),
                ),
            )
        )

        self.assertIn("Somente o conteúdo estruturado deve aparecer.", resposta.resultado.texto)
        self.assertNotIn(
            "A frase original dizia que o sistema deveria inventar um fato",
            resposta.resultado.texto,
        )

    def test_fallback_nao_chama_legado_quando_novo_e_valido(self):
        chamadas: list[str] = []
        resposta = gerar_resposta_com_fallback(
            plano(),
            lambda: chamadas.append("legado") or "não deveria ser usado",
        )

        self.assertIsInstance(resposta.resposta, RespostaEstruturada)
        self.assertEqual(chamadas, [])
        self.assertFalse(resposta.registro.fallback)
        self.assertEqual(resposta.registro.status, "estruturada")

    def test_adaptador_opt_in_preserva_legado_somente_como_fallback(self):
        with patch(
            "aplicacao.fluxo.processar_frase",
            return_value=["resposta legada"],
        ) as processar_legado:
            resposta_nova = processar_frase_com_plano_estruturado(
                "frase original que não entra no gerador",
                object(),
                plano(),
            )

        self.assertIsInstance(resposta_nova.resposta, RespostaEstruturada)
        processar_legado.assert_not_called()

        plano_incompleto = plano(
            etapas=(EtapaResposta("resultados"),),
            resultados=(),
            evidencias=(),
        )
        with patch(
            "aplicacao.fluxo.processar_frase",
            return_value=["resposta legada"],
        ) as processar_legado:
            resposta_legada = processar_frase_com_plano_estruturado(
                "frase original",
                object(),
                plano_incompleto,
            )

        self.assertEqual(resposta_legada.resposta, ["resposta legada"])
        processar_legado.assert_called_once()
        self.assertTrue(resposta_legada.registro.fallback)
