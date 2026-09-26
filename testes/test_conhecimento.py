import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bancos.conhecimento import ConhecimentoDB
from bancos.relacoes import RelacoesDB
from protocolo.regras import (
    ALVO_CONHECIMENTO,
    ALVO_RELACOES,
    TipoAcao,
)
from protocolo.verificador import emitir_permissao


class TestConhecimentoDB(unittest.TestCase):
    def setUp(self):
        self.pasta = tempfile.TemporaryDirectory()
        self.caminho_db = Path(self.pasta.name) / "conhecimento.db"
        self.banco = ConhecimentoDB(self.caminho_db)

    def tearDown(self):
        if self.banco is not None:
            self.banco.fechar()
        self.pasta.cleanup()

    @staticmethod
    def _permissao_conhecimento():
        return emitir_permissao(
            TipoAcao.SALVAR_CONHECIMENTO,
            ALVO_CONHECIMENTO,
        )

    @staticmethod
    def _permissao_relacao():
        return emitir_permissao(
            TipoAcao.SALVAR_RELACAO,
            ALVO_RELACOES,
        )

    def test_separa_o_mesmo_termo_por_contexto_e_sinaliza_ambiguidade(self):
        financeiro = self.banco.salvar_termo(
            "banco",
            significado="Instituição que oferece serviços financeiros.",
            contexto_uso="finanças",
            permissao=self._permissao_conhecimento(),
        )
        geografia = self.banco.salvar_termo(
            "banco",
            significado="Margem de um rio.",
            contexto_uso="geografia",
            permissao=self._permissao_conhecimento(),
        )

        encontrados = self.banco.buscar_termo("banco")

        self.assertEqual(len(encontrados), 2)
        self.assertNotEqual(financeiro.id, geografia.id)
        self.assertEqual(
            self.banco.buscar_termo("banco", "finanças")[0].significado,
            financeiro.significado,
        )
        self.assertEqual(
            self.banco.buscar_termo("banco", "geografia")[0].significado,
            geografia.significado,
        )
        self.assertEqual(
            self.banco.identificar_lacunas("banco"),
            ["contexto_uso"],
        )

    def test_rastreia_origem_e_estado_de_cada_evidencia(self):
        self.banco.salvar_termo(
            "fotossíntese",
            significado="Processo de conversão de energia luminosa.",
            exemplo_uso="A planta realiza fotossíntese.",
            proveniencias={
                "significado": ("professor", "proposta"),
                "exemplo_uso": ("usuario", "confirmada"),
            },
            permissao=self._permissao_conhecimento(),
        )

        evidencias = self.banco.listar_evidencias("fotossíntese")
        por_campo = {item.campo: item for item in evidencias}

        self.assertEqual(por_campo["significado"].origem, "professor")
        self.assertEqual(por_campo["significado"].estado, "proposta")
        self.assertEqual(por_campo["exemplo_uso"].origem, "usuario")
        self.assertEqual(por_campo["exemplo_uso"].estado, "confirmada")

    def test_identifica_lacunas_conforme_o_conhecimento_existente(self):
        self.assertEqual(
            self.banco.identificar_lacunas("termo novo"),
            ["significado", "exemplo_uso"],
        )

        self.banco.salvar_termo(
            "termo parcial",
            significado="Significado já conhecido.",
            permissao=self._permissao_conhecimento(),
        )
        self.assertEqual(
            self.banco.identificar_lacunas("termo parcial"),
            ["exemplo_uso"],
        )

        self.banco.salvar_termo(
            "termo contextualizado",
            significado="Significado já conhecido.",
            contexto_uso="Em uma conversa técnica.",
            permissao=self._permissao_conhecimento(),
        )
        self.assertEqual(
            self.banco.identificar_lacunas("termo contextualizado"),
            [],
        )

    def test_sugere_variacao_lexical_sem_criar_novo_conhecimento(self):
        self.banco.salvar_termo(
            "com licença",
            significado="Pedido educado de passagem ou atenção.",
            contexto_uso="Ao passar por alguém ou pedir atenção.",
            permissao=self._permissao_conhecimento(),
        )
        alteracoes_antes = self.banco.conn.total_changes

        sugestoes = self.banco.sugerir_termos("licença")

        self.assertEqual(sugestoes, ["com licença"])
        self.assertEqual(self.banco.conn.total_changes, alteracoes_antes)
        self.assertEqual(self.banco.buscar_termo("licença"), [])

    def test_gravacao_exige_permissao_valida_do_protocolo(self):
        permissao_de_relacao = self._permissao_relacao()
        with patch("protocolo.verificador._registrar_bloqueio"):
            with self.assertRaises(PermissionError):
                self.banco.salvar_termo("sem permissão")
            with self.assertRaises(PermissionError):
                self.banco.salvar_termo(
                    "permissão incompatível",
                    permissao=permissao_de_relacao,
                )

        self.assertEqual(self.banco.buscar_termo("sem permissão"), [])
        self.assertEqual(
            self.banco.buscar_termo("permissão incompatível"),
            [],
        )

        gravado = self.banco.salvar_termo(
            "autorizado",
            significado="Gravação autorizada.",
            permissao=self._permissao_conhecimento(),
        )
        self.assertEqual(gravado.termo, "autorizado")

    def test_atualizacao_nao_duplica_registro_e_persiste_apos_reabrir(self):
        self.banco.salvar_termo(
            "coração",
            significado="Definição inicial.",
            contexto_uso="anatomia",
            permissao=self._permissao_conhecimento(),
        )
        atualizado = self.banco.salvar_termo(
            "CORAÇÃO!",
            significado="Definição corrigida.",
            contexto_uso="anatomia",
            exemplo_uso="O coração bombeia sangue.",
            permissao=self._permissao_conhecimento(),
        )

        registros = self.banco.buscar_termo("coração", "anatomia")
        self.assertEqual(len(registros), 1)
        self.assertEqual(registros[0].id, atualizado.id)
        self.assertEqual(registros[0].significado, "Definição corrigida.")
        self.assertEqual(registros[0].exemplo_uso, "O coração bombeia sangue.")

        self.banco.fechar()
        self.banco = ConhecimentoDB(self.caminho_db)
        persistido = self.banco.buscar_termo("coração", "anatomia")
        self.assertEqual(len(persistido), 1)
        self.assertEqual(persistido[0].significado, "Definição corrigida.")

    def test_chave_ola_reutiliza_conhecimento_e_preserva_forma_canonica(self):
        original = self.banco.salvar_termo(
            "Olá",
            significado="Cumprimento.",
            contexto_uso="saudação",
            permissao=self._permissao_conhecimento(),
        )

        atualizado = self.banco.salvar_termo(
            "ola",
            significado="Saudação.",
            contexto_uso="saudação",
            permissao=self._permissao_conhecimento(),
        )

        encontrados = self.banco.buscar_termo("OLÁ!", "saudação")
        self.assertEqual(atualizado.id, original.id)
        self.assertEqual(atualizado.termo_original, "Olá")
        self.assertEqual(len(encontrados), 1)
        self.assertEqual(encontrados[0].termo, "Olá")
        self.assertEqual(
            self.banco.conn.execute(
                "SELECT COUNT(*) FROM conhecimento"
            ).fetchone()[0],
            1,
        )

    def test_pontuacao_na_chave_nao_altera_a_forma_exibida(self):
        original = self.banco.salvar_termo(
            "Até logo!",
            significado="Despedida.",
            permissao=self._permissao_conhecimento(),
        )

        encontrados = self.banco.buscar_termo("ate-logo?")

        self.assertEqual(len(encontrados), 1)
        self.assertEqual(encontrados[0].id, original.id)
        self.assertEqual(encontrados[0].termo_original, "Até logo!")

    def test_expressao_composta_reutiliza_termo_sem_diferenciar_caixa(self):
        original = self.banco.salvar_termo(
            "Bom dia",
            significado="Saudação.",
            permissao=self._permissao_conhecimento(),
        )

        encontrados = self.banco.buscar_termo("BOM DIA")

        self.assertEqual(len(encontrados), 1)
        self.assertEqual(encontrados[0].id, original.id)
        self.assertEqual(encontrados[0].termo_original, "Bom dia")

    def test_migracao_preserva_campos_anteriores_com_evidencia_legada(self):
        self.banco.fechar()
        self.banco = None
        conexao = sqlite3.connect(self.caminho_db)
        conexao.executescript(
            """
            DROP TABLE conhecimento;
            CREATE TABLE conhecimento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                termo TEXT NOT NULL,
                tipo TEXT,
                significado TEXT,
                contexto_uso TEXT,
                resposta_padrao TEXT,
                relacionados TEXT
            );
            INSERT INTO conhecimento (
                termo, tipo, significado, contexto_uso, resposta_padrao,
                relacionados
            ) VALUES (
                'registro antigo', 'conceito', 'sentido legado',
                'contexto legado', 'resposta legada', NULL
            );
            PRAGMA user_version = 0;
            """
        )
        conexao.close()

        self.banco = ConhecimentoDB(self.caminho_db)
        entrada = self.banco.buscar_termo("registro antigo")[0]
        evidencias = self.banco.listar_evidencias("registro antigo")

        self.assertEqual(entrada.significado, "sentido legado")
        self.assertEqual(
            {item.origem for item in evidencias},
            {"legado"},
        )
        self.assertEqual(
            {item.estado for item in evidencias},
            {"historico"},
        )
        linha = self.banco.conn.execute(
            """
            SELECT termo, termo_original, termo_chave, significado
            FROM conhecimento
            """
        ).fetchone()
        self.assertEqual(linha["termo"], "registro antigo")
        self.assertEqual(linha["termo_original"], "registro antigo")
        self.assertEqual(linha["termo_chave"], "registro antigo")
        self.assertEqual(linha["significado"], "sentido legado")
        self.assertEqual(
            self.banco.conn.execute("PRAGMA user_version").fetchone()[0],
            3,
        )

    def test_reabrir_banco_migrado_nao_altera_sqlite(self):
        self.banco.fechar()
        self.banco = None
        observador = sqlite3.connect(self.caminho_db)
        data_version_antes = observador.execute(
            "PRAGMA data_version"
        ).fetchone()[0]
        sequencia_antes = observador.execute(
            """
            SELECT name, seq
            FROM sqlite_sequence
            ORDER BY name
            """
        ).fetchall()

        self.banco = ConhecimentoDB(self.caminho_db)

        data_version_depois = observador.execute(
            "PRAGMA data_version"
        ).fetchone()[0]
        sequencia_depois = observador.execute(
            """
            SELECT name, seq
            FROM sqlite_sequence
            ORDER BY name
            """
        ).fetchall()
        observador.close()

        self.assertEqual(data_version_depois, data_version_antes)
        self.assertEqual(sequencia_depois, sequencia_antes)

    def test_migracao_interrompe_colisao_sem_unir_ou_alterar_registros(self):
        caminho = Path(self.pasta.name) / "colisao.db"
        conexao = sqlite3.connect(caminho)
        conexao.executescript(
            """
            CREATE TABLE conhecimento (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                termo TEXT NOT NULL,
                tipo TEXT,
                significado TEXT,
                contexto_uso TEXT,
                resposta_padrao TEXT,
                relacionados TEXT,
                exemplo_uso TEXT
            );
            INSERT INTO conhecimento (termo, significado, contexto_uso)
                VALUES ('cafe', 'sentido sem acento', 'mesmo contexto');
            INSERT INTO conhecimento (termo, significado, contexto_uso)
                VALUES ('café', 'sentido com acento', 'mesmo contexto');
            PRAGMA user_version = 2;
            """
        )
        conexao.close()

        with self.assertRaisesRegex(ValueError, "colisão"):
            ConhecimentoDB(caminho)

        conexao = sqlite3.connect(caminho)
        self.assertEqual(
            conexao.execute("SELECT COUNT(*) FROM conhecimento").fetchone()[0],
            2,
        )
        self.assertEqual(
            conexao.execute("PRAGMA user_version").fetchone()[0],
            2,
        )
        colunas = {
            linha[1]
            for linha in conexao.execute(
                "PRAGMA table_info(conhecimento)"
            ).fetchall()
        }
        self.assertNotIn("termo_original", colunas)
        self.assertNotIn("termo_chave", colunas)
        conexao.close()

    def test_relacao_consultavel_e_bidirecional(self):
        primeiro = self.banco.salvar_termo(
            "carro",
            significado="Veículo automotor.",
            permissao=self._permissao_conhecimento(),
        )
        segundo = self.banco.salvar_termo(
            "automóvel",
            significado="Veículo automotor.",
            permissao=self._permissao_conhecimento(),
        )
        caminho_relacoes = Path(self.pasta.name) / "relacoes.db"

        with RelacoesDB(caminho_relacoes) as relacoes:
            relacoes.adicionar(
                primeiro.id,
                segundo.id,
                tipo="sinônimo",
                permissao=self._permissao_relacao(),
            )
            relacoes.adicionar(
                primeiro.id,
                segundo.id,
                tipo="sinônimo",
                permissao=self._permissao_relacao(),
            )

            self.assertEqual(relacoes.listar_ids(primeiro.id), [segundo.id])
            self.assertEqual(relacoes.listar_ids(segundo.id), [primeiro.id])

    def test_fatos_sao_independentes_de_termos_e_separados_por_contexto(self):
        geografia = self.banco.salvar_fato(
            "A capital do Brasil é Brasília.",
            "geografia",
            permissao=self._permissao_conhecimento(),
        )
        política = self.banco.salvar_fato(
            "A capital do Brasil é Brasília.",
            "política",
            permissao=self._permissao_conhecimento(),
        )

        self.assertNotEqual(geografia.id, política.id)
        self.assertEqual(len(self.banco.buscar_fatos()), 2)
        self.assertEqual(
            self.banco.buscar_fato(
                "a CAPITAL do BRASIL é BRASÍLIA.",
                "GEOGRAFIA",
            ).id,
            geografia.id,
        )
        self.assertEqual(self.banco.buscar_termo("capital"), [])
        self.assertEqual(self.banco.buscar_fatos("geografia"), [geografia])

    def test_contexto_de_fato_compara_acentos_sem_diferenciar_caixa(self):
        fato = self.banco.salvar_fato(
            "Um registro contextual.",
            "Índice",
            permissao=self._permissao_conhecimento(),
        )

        self.assertEqual(self.banco.buscar_fatos("íNDICE"), [fato])

    def test_correcao_de_fato_preserva_evidencia_anterior(self):
        original = self.banco.salvar_fato(
            "O evento ocorre na terça-feira.",
            "agenda",
            permissao=self._permissao_conhecimento(),
        )

        atualizado = self.banco.salvar_fato(
            "O evento ocorre na quarta-feira.",
            "agenda",
            fato_id=original.id,
            permissao=self._permissao_conhecimento(),
        )

        evidencias = self.banco.listar_evidencias_fato(original.id)
        self.assertEqual(atualizado.id, original.id)
        self.assertEqual(
            atualizado.afirmacao,
            "O evento ocorre na quarta-feira.",
        )
        self.assertEqual(
            [evidencia.afirmacao for evidencia in evidencias],
            [
                "O evento ocorre na terça-feira.",
                "O evento ocorre na quarta-feira.",
            ],
        )


if __name__ == "__main__":
    unittest.main()