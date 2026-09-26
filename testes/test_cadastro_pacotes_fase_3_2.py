"""Testes comportamentais do cadastro por pacote da Fase 3.2."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aplicacao.cadastro import (  # noqa: E402
    CadastroPacotes,
    contrato_de_dict,
    contrato_de_json,
)
from bancos.api_conhecimento import ConhecimentoAPI  # noqa: E402
from core.contratos import ContratoCadastro  # noqa: E402


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "aprendizado" / "bancos" / "linguagem_schema.sql"


def pacote_lexema(
    *,
    entrada: str = "manual",
    lema: str = "correr",
    categoria: str = "verbo",
    origem: str = "usuario",
    proposta_id: str = "prop-correr",
    idempotencia: str = "correr:v1",
) -> dict:
    fonte_tipo = "manual" if origem == "usuario" else origem
    fonte_identificador = "usuario-teste" if origem == "usuario" else f"{origem}-fake"
    return {
        "proposta_id": proposta_id,
        "entrada": entrada,
        "idempotencia": idempotencia,
        "evidencias": [
            {
                "evidencia_id": "ev-correr",
                "fonte_tipo": fonte_tipo,
                "fonte_identificador": fonte_identificador,
                "origem": "teste determinístico",
                "trecho": lema,
            }
        ],
        "objetos": [
            {
                "objeto_id": "obj-correr",
                "tipo": "lexema",
                "chave": lema,
                "campos": [
                    {
                        "nome": "lema",
                        "valor": lema,
                        "origem": origem,
                        "estado": "fornecida" if origem == "usuario" else "proposta",
                        "evidencia_ids": ["ev-correr"],
                    },
                    {
                        "nome": "categoria_lexical",
                        "valor": categoria,
                        "origem": origem,
                        "estado": "fornecida" if origem == "usuario" else "proposta",
                        "evidencia_ids": ["ev-correr"],
                    },
                ],
            }
        ],
    }


class TestCadastroPacotesFase32(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "linguagem.db"
        with sqlite3.connect(self.db) as conn:
            conn.executescript(SCHEMA.read_text(encoding="utf-8"))
            conn.execute(
                "INSERT INTO lexemas (lema, categoria_lexical, estado) "
                "VALUES ('andar', 'substantivo', 'aprovado')"
            )
            conn.commit()
        self.api = ConhecimentoAPI(self.db)
        self.cadastro = CadastroPacotes(self.api)

    def tearDown(self) -> None:
        self.api.fechar()
        self.tmp.cleanup()

    def test_pacote_python_valido_e_aceito(self):
        contrato = contrato_de_dict(pacote_lexema())
        resultado = self.cadastro.receber_contrato(contrato)

        self.assertIsInstance(resultado.contrato, ContratoCadastro)
        self.assertEqual(resultado.proposta.estado, "proposta")
        self.assertTrue(resultado.proposta.validacao.valido)

    def test_pacote_incompleto_e_representado_sem_confirmacao(self):
        pacote = pacote_lexema()
        del pacote["objetos"][0]["campos"][1]

        resultado = self.cadastro.receber_dict(pacote)

        self.assertTrue(resultado.proposta.validacao.incompleta)
        self.assertFalse(resultado.proposta.validacao.pode_autorizar)
        self.assertEqual(resultado.proposta.estado, "proposta")

    def test_pacote_invalido_e_rejeitado(self):
        pacote = pacote_lexema()
        pacote["objetos"][0]["campos"].append(
            {"nome": "estado_fisico", "valor": "confirmado", "origem": "usuario"}
        )

        with self.assertRaisesRegex(ValueError, "não é permitido"):
            self.cadastro.receber_dict(pacote)

    def test_json_e_dict_convergem_para_o_mesmo_contrato(self):
        pacote = pacote_lexema()

        contrato_dict = contrato_de_dict(pacote)
        contrato_json = contrato_de_json(json.dumps(pacote))
        resultado = self.cadastro.receber_json(json.dumps(pacote))

        self.assertEqual(contrato_dict, contrato_json)
        self.assertEqual(resultado.contrato, contrato_dict)

    def test_campos_desconhecidos_sao_rejeitados(self):
        pacote = pacote_lexema()
        pacote["campo_desconhecido"] = "não permitido"

        with self.assertRaisesRegex(ValueError, "campos desconhecidos"):
            self.cadastro.receber_dict(pacote)

    def test_sql_embutido_e_rejeitado(self):
        pacote = pacote_lexema()
        pacote["objetos"][0]["campos"][0]["valor"] = (
            "SELECT lema FROM lexemas; DROP TABLE conceitos;"
        )

        with self.assertRaisesRegex(ValueError, "contém SQL"):
            self.cadastro.receber_dict(pacote)

    def test_codigo_executavel_embutido_e_rejeitado(self):
        pacote = pacote_lexema()
        pacote["objetos"][0]["campos"][0]["valor"] = (
            "__import__('os').system('touch arquivo')"
        )

        with self.assertRaisesRegex(ValueError, "código executável"):
            self.cadastro.receber_json(json.dumps(pacote))

    def test_multiplos_sentidos_permanecem_separados(self):
        pacote = pacote_lexema()
        pacote["objetos"] = [
            {
                "objeto_id": "sentido-1",
                "tipo": "sentido",
                "chave": "correr:1",
                "campos": [
                    {
                        "nome": "definicao",
                        "valor": "deslocar-se rapidamente",
                        "origem": "usuario",
                        "evidencia_ids": ["ev-correr"],
                    }
                ],
            },
            {
                "objeto_id": "sentido-2",
                "tipo": "sentido",
                "chave": "correr:2",
                "campos": [
                    {
                        "nome": "definicao",
                        "valor": "disputar uma corrida",
                        "origem": "usuario",
                        "evidencia_ids": ["ev-correr"],
                    }
                ],
            },
        ]

        resultado = self.cadastro.receber_dict(pacote)

        self.assertEqual(
            [objeto.objeto_id for objeto in resultado.contrato.objetos],
            ["sentido-1", "sentido-2"],
        )
        self.assertNotEqual(
            resultado.contrato.objetos[0].campos[0].valor,
            resultado.contrato.objetos[1].campos[0].valor,
        )

    def test_estruturas_relacionadas_sao_preservadas(self):
        pacote = pacote_lexema()
        pacote["objetos"][0]["relacoes"] = [
            {
                "tipo": "tem_forma",
                "origem_objeto_id": "obj-correr",
                "destino_tipo": "forma_lexical",
                "destino_chave": "corro",
            }
        ]
        pacote["objetos"].append(
            {
                "objeto_id": "obj-corro",
                "tipo": "forma_lexical",
                "chave": "corro",
                "campos": [
                    {
                        "nome": "forma",
                        "valor": "corro",
                        "origem": "usuario",
                        "evidencia_ids": ["ev-correr"],
                    },
                    {
                        "nome": "normalizada",
                        "valor": "corro",
                        "origem": "usuario",
                        "evidencia_ids": ["ev-correr"],
                    },
                ],
            }
        )

        resultado = self.cadastro.receber_dict(pacote)

        self.assertEqual(len(resultado.contrato.objetos[0].relacoes), 1)
        self.assertEqual(
            resultado.contrato.objetos[0].relacoes[0].destino_chave,
            "corro",
        )

    def test_repeticao_do_mesmo_pacote_respeita_idempotencia(self):
        pacote = pacote_lexema()

        primeira = self.cadastro.receber_dict(pacote)
        segunda = self.cadastro.receber_dict(pacote)

        self.assertIs(primeira.proposta, segunda.proposta)

    def test_conflito_vai_para_revisao_sem_sobrescrever(self):
        pacote = pacote_lexema(
            lema="andar",
            categoria="verbo",
            proposta_id="prop-andar-conflito",
            idempotencia="andar:conflito:v1",
        )

        resultado = self.cadastro.receber_dict(pacote)

        self.assertTrue(resultado.proposta.validacao.conflitos)
        self.assertFalse(resultado.proposta.validacao.pode_autorizar)
        self.assertEqual(self.api.consultar("lexema", "andar")[0].campos[1].valor, "substantivo")

        self.cadastro.iniciar_revisao("prop-andar-conflito", "revisor")
        with self.assertRaisesRegex(ValueError, "conflitante"):
            self.cadastro.autorizar("prop-andar-conflito", "revisor")

    def test_proveniencia_e_preservada_ao_receber_professor(self):
        pacote = pacote_lexema(
            entrada="professor",
            origem="professor",
            proposta_id="prop-professor",
            idempotencia="professor:correr:v1",
        )

        resultado = self.cadastro.receber_professor(pacote)

        self.assertEqual(resultado.contrato.entrada, "professor")
        self.assertEqual(resultado.contrato.evidencias[0].fonte_tipo, "professor")
        self.assertEqual(
            resultado.contrato.objetos[0].campos[0].origem,
            "professor",
        )

    def test_proposta_nao_vira_fato_confirmado(self):
        resultado = self.cadastro.receber_dict(pacote_lexema())

        self.assertNotEqual(resultado.contrato.estado, "persistida")
        self.assertEqual(resultado.contrato.objetos[0].tipo, "lexema")
        self.assertNotEqual(resultado.proposta.estado, "autorizada")

    def test_revisao_e_autorizacao_continuam_separadas(self):
        resultado = self.cadastro.receber_dict(pacote_lexema())

        self.assertEqual(resultado.proposta.estado, "proposta")
        revisada = self.cadastro.iniciar_revisao("prop-correr", "revisor")
        self.assertEqual(revisada.estado, "em_revisao")
        autorizada = self.cadastro.autorizar("prop-correr", "revisor")
        self.assertEqual(autorizada.estado, "autorizada")

    def test_pacote_nao_pode_escolher_tabela_ou_coluna(self):
        pacote = pacote_lexema()
        pacote["tabela_sqlite"] = "lexemas"

        with self.assertRaisesRegex(ValueError, "referência física"):
            self.cadastro.receber_dict(pacote)

    def test_entrada_nao_grava_diretamente_no_sqlite(self):
        antes = hashlib.sha256(self.db.read_bytes()).hexdigest()

        self.cadastro.receber_dict(pacote_lexema())

        depois = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.assertEqual(antes, depois)

    def test_professor_falso_funciona_sem_professor_real(self):
        class ProfessorFalso:
            def propor(self) -> ContratoCadastro:
                return contrato_de_dict(
                    pacote_lexema(
                        entrada="professor",
                        origem="professor",
                        proposta_id="prop-professor-falso",
                        idempotencia="professor:falso:v1",
                    )
                )

        resultado = self.cadastro.receber_professor(ProfessorFalso().propor())

        self.assertEqual(resultado.contrato.entrada, "professor")

    def test_llama_usa_o_mesmo_contrato_sem_exigir_ollama(self):
        resultado = self.cadastro.receber_llama(
            pacote_lexema(
                entrada="llama",
                origem="llama",
                proposta_id="prop-llama",
                idempotencia="llama:correr:v1",
            )
        )

        self.assertEqual(resultado.contrato.entrada, "llama")
        self.assertEqual(resultado.proposta.estado, "proposta")

    def test_fonte_automatica_nao_autoriza_a_propria_proposta(self):
        self.cadastro.receber_professor(
            pacote_lexema(
                entrada="professor",
                origem="professor",
                proposta_id="prop-professor-autorizacao",
                idempotencia="professor:autorizacao:v1",
            )
        )
        self.cadastro.iniciar_revisao(
            "prop-professor-autorizacao",
            "revisor",
        )

        with self.assertRaises(PermissionError):
            self.cadastro.autorizar(
                "prop-professor-autorizacao",
                "professor-fake",
            )

    def test_credencial_nao_faz_parte_do_pacote(self):
        pacote = pacote_lexema()
        pacote["token"] = "segredo não permitido"

        with self.assertRaisesRegex(ValueError, "campos desconhecidos"):
            self.cadastro.receber_json(json.dumps(pacote))


if __name__ == "__main__":
    unittest.main()