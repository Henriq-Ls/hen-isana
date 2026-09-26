"""Testes do contrato comum de cadastro da Parte 3.1."""

from pathlib import Path
import sys
import unittest
from dataclasses import FrozenInstanceError


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.contratos import (  # noqa: E402
    CampoCadastro,
    ContratoCadastro,
    EvidenciaCadastro,
    ObjetoCadastro,
    RelacaoCadastro,
)


def contrato_exemplo(entrada="manual"):
    evidencia = EvidenciaCadastro(
        evidencia_id="ev-1",
        fonte_tipo="manual",
        fonte_identificador="usuario-1",
        origem="entrada manual",
        trecho="correr",
        confianca=1.0,
    )
    campo = CampoCadastro(
        nome="lema",
        valor="correr",
        origem="usuario",
        estado="fornecida",
        confianca=1.0,
        evidencia_ids=("ev-1",),
    )
    objeto = ObjetoCadastro(
        objeto_id="obj-1",
        tipo="lexema",
        chave="correr",
        campos=(campo,),
        pendencias=("categoria lexical ainda não confirmada",),
    )
    return ContratoCadastro(
        proposta_id="prop-1",
        entrada=entrada,
        objetos=(objeto,),
        evidencias=(evidencia,),
        pendencias=("categoria lexical ainda não confirmada",),
        incertezas=("a entrada pode ter mais de um sentido",),
        idempotencia="entrada:correr:v1",
    )


class TestContratoCadastroParte3(unittest.TestCase):
    def test_aceita_proposta_incompleta_com_proveniencia_e_pendencia(self):
        contrato = contrato_exemplo()

        self.assertEqual(contrato.objetos[0].tipo, "lexema")
        self.assertEqual(contrato.objetos[0].campos[0].evidencia_ids, ("ev-1",))
        self.assertEqual(contrato.evidencias[0].fonte_tipo, "manual")
        self.assertEqual(len(contrato.pendencias), 1)

    def test_manual_json_e_professor_usam_a_mesma_estrutura(self):
        payload = contrato_exemplo("json").to_dict()
        payload["objetos"][0]["campos"][0]["origem"] = "professor"
        payload["evidencias"][0]["fonte_tipo"] = "professor"
        payload["evidencias"][0]["fonte_identificador"] = "professor-remoto"

        contrato = ContratoCadastro.from_dict(payload)

        self.assertEqual(contrato.entrada, "json")
        self.assertEqual(contrato.objetos[0].campos[0].origem, "professor")
        self.assertEqual(
            contrato.evidencias[0].fonte_identificador,
            "professor-remoto",
        )
        self.assertEqual(contrato.to_dict(), payload)

    def test_aceita_estrutura_ainda_sem_objeto_quando_ha_pendencia(self):
        contrato = ContratoCadastro(
            proposta_id="prop-pendente",
            entrada="manual",
            pendencias=("identificar o tipo do objeto",),
            idempotencia="entrada:desconhecida:v1",
        )

        self.assertEqual(contrato.objetos, ())
        self.assertTrue(contrato.pendencias)

    def test_relacao_logica_nao_expoe_id_fisico(self):
        relacao = RelacaoCadastro(
            tipo="forma_de",
            origem_objeto_id="obj-forma",
            destino_tipo="lexema",
            destino_chave="correr",
        )
        objeto = ObjetoCadastro(
            objeto_id="obj-forma",
            tipo="forma_lexical",
            chave="corro",
            relacoes=(relacao,),
        )
        contrato = ContratoCadastro(
            proposta_id="prop-relacao",
            entrada="manual",
            objetos=(objeto,),
            idempotencia="entrada:corro:v1",
        )

        self.assertEqual(contrato.objetos[0].relacoes[0].destino_chave, "correr")
        self.assertFalse(hasattr(contrato.objetos[0].relacoes[0], "tabela"))

    def test_rejeita_campos_desconhecidos_no_json(self):
        payload = contrato_exemplo("json").to_dict()
        payload["tabela_sqlite"] = "lexemas"

        with self.assertRaisesRegex(ValueError, "campos desconhecidos"):
            ContratoCadastro.from_dict(payload)

    def test_rejeita_valor_estruturado_fora_de_campo_logico(self):
        with self.assertRaises(TypeError):
            CampoCadastro(
                nome="sentidos",
                valor={"id": 1},
                origem="professor",
            )

    def test_rejeita_confirmacao_sem_evidencia(self):
        with self.assertRaisesRegex(ValueError, "ao menos uma evidência"):
            CampoCadastro(
                nome="definicao",
                valor="Uma ação.",
                origem="usuario",
                estado="confirmada",
            )

    def test_rejeita_relacao_com_origem_inexistente(self):
        relacao = RelacaoCadastro(
            tipo="relaciona",
            origem_objeto_id="ausente",
            destino_tipo="conceito",
            destino_chave="acao",
        )
        objeto = ObjetoCadastro(
            objeto_id="obj-1",
            tipo="lexema",
            chave="agir",
            relacoes=(relacao,),
        )

        with self.assertRaisesRegex(ValueError, "origem inexistente"):
            ContratoCadastro(
                proposta_id="prop-invalida",
                entrada="manual",
                objetos=(objeto,),
                idempotencia="entrada:agir:v1",
            )

    def test_contrato_e_componentes_sao_immutaveis(self):
        contrato = contrato_exemplo()

        with self.assertRaises(FrozenInstanceError):
            contrato.estado = "autorizada"


if __name__ == "__main__":
    unittest.main()