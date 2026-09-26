"""Testes comportamentais da API e do contrato da Fase 3.1."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import hashlib
import json
import sqlite3
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bancos.api_conhecimento import ConhecimentoAPI
from core.contratos import (
    CampoCadastro,
    ContratoCadastro,
    EvidenciaCadastro,
    ObjetoCadastro,
)


ROOT = Path(__file__).resolve().parents[1]
SCHEMA = ROOT / "aprendizado" / "bancos" / "linguagem_schema.sql"


def contrato_lexema(
    *,
    entrada: str = "manual",
    origem: str = "usuario",
    estado_campo: str = "fornecida",
    ambiguidades: tuple[str, ...] = (),
    pendencias: tuple[str, ...] = (),
) -> ContratoCadastro:
    evidencia = EvidenciaCadastro(
        evidencia_id="ev-1",
        fonte_tipo="manual" if origem == "usuario" else origem,
        fonte_identificador="usuario-1" if origem == "usuario" else f"{origem}-teste",
        origem="teste determinístico",
        trecho="correr",
    )
    objeto = ObjetoCadastro(
        objeto_id="obj-1",
        tipo="lexema",
        chave="correr",
        campos=(
            CampoCadastro(
                "lema",
                "correr",
                origem,
                estado_campo,
                evidencia_ids=("ev-1",),
            ),
            CampoCadastro(
                "categoria_lexical",
                "verbo",
                origem,
                estado_campo,
                evidencia_ids=("ev-1",),
            ),
        ),
    )
    return ContratoCadastro(
        proposta_id=f"prop-{entrada}-{origem}",
        entrada=entrada,
        objetos=(objeto,),
        evidencias=(evidencia,),
        pendencias=pendencias,
        ambiguidades=ambiguidades,
        idempotencia=f"correr:{entrada}:{origem}",
    )


class TestAPIConhecimentoFase31(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "linguagem.db"
        with sqlite3.connect(self.db) as conn:
            conn.executescript(SCHEMA.read_text(encoding="utf-8"))
            fonte = conn.execute(
                "INSERT INTO fontes (tipo, identificador, origem, estado) "
                "VALUES ('manual', 'teste-api', 'unittest', 'aprovado')"
            ).lastrowid
            conn.execute(
                "INSERT INTO lexemas (lema, categoria_lexical, estado) "
                "VALUES ('correr', 'verbo', 'aprovado')"
            )
            conn.commit()
        self.api = ConhecimentoAPI(self.db)

    def tearDown(self) -> None:
        self.api.fechar()
        self.tmp.cleanup()

    def test_consulta_usa_registro_logico_sem_cursor_ou_schema(self):
        registros = self.api.consultar("lexema", "correr")
        self.assertEqual(registros[0].tipo, "lexema")
        self.assertEqual(registros[0].chave, "correr")
        self.assertTrue(all(campo.nome != "tabela" for campo in registros[0].campos))
        self.assertFalse(hasattr(registros[0], "conn"))
        for tipo in (
            "forma_lexical",
            "analise_morfologica",
            "sentido",
            "conceito",
            "expressao",
            "proposicao",
            "argumento",
            "fato",
            "relacao_semantica",
            "fonte",
            "evidencia",
        ):
            self.api.consultar(tipo)

    def test_criacao_de_proposta_valida_e_fluxo_revisao_autorizacao(self):
        contrato = contrato_lexema()
        proposta = self.api.registrar_proposta(contrato)
        self.assertTrue(proposta.validacao.pode_autorizar)
        self.assertEqual(proposta.estado, "proposta")
        revisao = self.api.iniciar_revisao(contrato.proposta_id, "revisor-1")
        autorizada = self.api.autorizar(contrato.proposta_id, "revisor-1")
        self.assertEqual(revisao.estado, "em_revisao")
        self.assertEqual(autorizada.estado, "autorizada")
        self.assertNotEqual(autorizada.contrato.estado, "persistida")

    def test_proposta_incompleta_e_ambigua_sao_representaveis(self):
        incompleta = contrato_lexema(pendencias=("falta contexto",))
        ambigua = contrato_lexema(ambiguidades=("há dois sentidos possíveis",))
        resultado_incompleto = self.api.validar(incompleta)
        resultado_ambiguo = self.api.validar(ambigua)
        self.assertTrue(resultado_incompleto.incompleta)
        self.assertTrue(resultado_ambiguo.ambigua)
        self.assertFalse(resultado_ambiguo.pode_autorizar)

    def test_proveniencia_de_usuario_e_professor_e_preservada(self):
        usuario = contrato_lexema()
        professor = contrato_lexema(
            entrada="professor",
            origem="professor",
            estado_campo="proposta",
        )
        self.assertEqual(usuario.objetos[0].campos[0].origem, "usuario")
        self.assertEqual(professor.objetos[0].campos[0].origem, "professor")
        self.assertEqual(professor.evidencias[0].fonte_tipo, "professor")

    def test_evidencia_associada_e_proposta_nao_sao_fato(self):
        contrato = contrato_lexema()
        self.assertEqual(contrato.objetos[0].campos[0].evidencia_ids, ("ev-1",))
        self.assertNotEqual(contrato.estado, "persistida")
        self.assertNotEqual(contrato.objetos[0].tipo, "fato")

    def test_lexema_forma_sentido_e_conceito_sao_tipos_distintos(self):
        tipos = ("lexema", "forma_lexical", "sentido", "conceito")
        objetos = tuple(
            ObjetoCadastro(f"obj-{tipo}", tipo, tipo)
            for tipo in tipos
        )
        contrato = ContratoCadastro(
            proposta_id="prop-tipos",
            entrada="manual",
            objetos=objetos,
            pendencias=("campos ainda não preenchidos",),
            idempotencia="tipos:v1",
        )
        self.assertEqual(tuple(objeto.tipo for objeto in contrato.objetos), tipos)

    def test_rejeita_campo_fora_do_contrato_logico(self):
        contrato = contrato_lexema()
        objeto = deepcopy(contrato.objetos[0])
        objeto = ObjetoCadastro(
            objeto.objeto_id,
            objeto.tipo,
            objeto.chave,
            campos=objeto.campos
            + (CampoCadastro("tabela_sqlite", "lexemas", "usuario"),),
        )
        invalido = ContratoCadastro(
            proposta_id="prop-campo-invalido",
            entrada="manual",
            objetos=(objeto,),
            evidencias=contrato.evidencias,
            idempotencia="campo-invalido:v1",
        )
        with self.assertRaisesRegex(ValueError, "tabela_sqlite"):
            self.api.registrar_proposta(invalido)

    def test_validacao_de_proposta_valida_nao_grava_no_banco(self):
        before = self.db.read_bytes()
        resultado = self.api.validar(contrato_lexema())
        self.assertTrue(resultado.valido)
        self.assertEqual(before, self.db.read_bytes())

    def test_contrato_nao_depende_diretamente_do_sqlite(self):
        contrato = contrato_lexema()
        self.assertFalse(any("sqlite" in nome.lower() for nome in contrato.__dict__))
        self.assertFalse(any("sqlite" in nome.lower() for nome in contrato.objetos[0].__dict__))

    def test_mock_deterministico_de_professor_nao_exige_ollama(self):
        class FakeProfessorDeTeste:
            def propor(self) -> ContratoCadastro:
                return contrato_lexema(
                    entrada="professor",
                    origem="professor",
                    estado_campo="proposta",
                )

        proposta = self.api.registrar_proposta(FakeProfessorDeTeste().propor())
        self.assertEqual(proposta.contrato.entrada, "professor")
        self.assertEqual(proposta.estado, "proposta")

    def test_mock_nao_grava_diretamente_no_banco(self):
        before = self.db.read_bytes()
        proposta = self.api.registrar_proposta(
            contrato_lexema(
                entrada="professor",
                origem="professor",
                estado_campo="proposta",
            )
        )
        self.assertIsNotNone(proposta)
        self.assertEqual(before, self.db.read_bytes())

    def test_credencial_real_nao_e_necessaria(self):
        contrato = contrato_lexema(
            entrada="professor",
            origem="professor",
            estado_campo="proposta",
        )
        self.assertTrue(self.api.validar(contrato).valido)
        self.assertNotIn("token", json.dumps(contrato.to_dict()).lower())

    def test_json_e_entrada_de_dados_nao_e_executado(self):
        payload = contrato_lexema().to_dict()
        payload["objetos"][0]["campos"][0]["valor"] = "__import__('os').system('false')"
        contrato = ContratoCadastro.from_dict(payload)
        self.assertTrue(self.api.validar(contrato).valido)
        self.assertEqual(
            contrato.objetos[0].campos[0].valor,
            "__import__('os').system('false')",
        )

    def test_idempotencia_nao_duplica_proposta_em_memoria(self):
        contrato = contrato_lexema()
        primeira = self.api.registrar_proposta(contrato)
        segunda = self.api.registrar_proposta(contrato)
        self.assertIs(primeira, segunda)

    def test_fonte_nao_pode_autorizar_a_propria_proposta(self):
        contrato = contrato_lexema(
            entrada="professor",
            origem="professor",
            estado_campo="proposta",
        )
        self.api.registrar_proposta(contrato)
        self.api.iniciar_revisao(contrato.proposta_id, "professor-teste")
        with self.assertRaises(PermissionError):
            self.api.autorizar(contrato.proposta_id, "professor-teste")

    def test_persistencia_e_explicitamente_fora_da_fase(self):
        with self.assertRaises(NotImplementedError):
            self.api.persistir(contrato_lexema())

    def test_banco_permanece_integral_e_sem_escrita_da_api(self):
        before = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.api.consultar("fonte")
        self.api.registrar_proposta(contrato_lexema())
        after = hashlib.sha256(self.db.read_bytes()).hexdigest()
        self.assertEqual(before, after)
        with sqlite3.connect(self.db) as conn:
            self.assertEqual(conn.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(conn.execute("PRAGMA foreign_key_check").fetchall(), [])


if __name__ == "__main__":
    unittest.main()