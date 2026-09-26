import sys
import unittest
from pathlib import Path
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from professor.professor_llama import ProfessorLlama
from professor.professor import Professor


class TestProfessorLlama(unittest.TestCase):
    def test_monta_payload_local_com_contexto_reduzido(self):
        professor = ProfessorLlama()
        professor._historico = [
            {"role": "system", "content": "instrução"},
            {"role": "user", "content": "pergunta"},
        ]

        payload = professor._montar_payload(512)

        self.assertEqual(payload["model"], "phi3:mini")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["options"]["num_ctx"], 1024)
        self.assertEqual(payload["options"]["num_predict"], 128)
        self.assertEqual(
            professor._url_chat(professor.url_http),
            "http://127.0.0.1:11434/api/chat",
        )

    def test_rejeita_link_ou_metadado_inventado(self):
        motivo = ProfessorLlama._motivo_resposta_invalida(
            "O que 'animal' significa?",
            "Animal é um ser vivo. https://example.com",
        )

        self.assertIsNotNone(motivo)

    def test_normaliza_confirmacao_do_modelo(self):
        professor = ProfessorLlama()
        professor._cache_respostas = {}
        professor._salvar_historico = lambda: None  # type: ignore[method-assign]

        with patch.object(
            Professor,
            "responder",
            return_value="Sim, a relação é válida.",
        ):
            resposta = professor.responder(
                "'animal' parece relacionado a 'ser vivo'. É a mesma coisa? [s/n]",
            )

        self.assertEqual(resposta, "sim")


if __name__ == "__main__":
    unittest.main()