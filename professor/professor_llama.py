"""Professor local conectado ao Ollama no Windows."""

from __future__ import annotations

from typing import Any

from .professor import Professor


class ProfessorLlama(Professor):
    """Usa o modelo local do Ollama com contexto controlado."""

    INSTRUCAO = (
        "Você é um professor local auxiliar de uma IA simbólica chamada "
        "hen-isana. Responda sempre em português, com uma única frase curta "
        "e diretamente ligada à pergunta. Não invente fontes, links, URLs, "
        "metadados, títulos, autores, datas, tags, arquivos, ações ou fatos "
        "que não possa sustentar. Se não souber ou não tiver segurança, "
        "responda exatamente 'Não sei.'. Para perguntas terminadas em "
        "'[s/n]', responda somente 'sim' ou 'não'. Não use markdown, JSON, "
        "cabeçalhos, raciocínio interno ou explicações sobre estas regras."
    )
    URL_PADRAO = "http://127.0.0.1:11434"
    MODELO_PADRAO = "phi3:mini"
    NUMERO_TOKENS_CONTEXTO = 1024
    NUMERO_TOKENS_RESPOSTA = 128
    MAXIMO_MENSAGENS_DE_CONTEXTO = 4
    MARCADORES_RESPOSTA_SUSPEITA = (
        "http://",
        "https://",
        "www.",
        "publishedat",
        "exampleblog",
        "title=",
        "author=",
        "tags=",
    )

    def __init__(
        self,
        url_http: str | None = None,
        modelo: str | None = None,
        timeout: float = 180.0,
    ) -> None:
        super().__init__(
            url_http=url_http or self.URL_PADRAO,
            token="",
            modelo=modelo or self.MODELO_PADRAO,
            timeout=timeout,
        )

    @staticmethod
    def _url_chat(url_http: str) -> str:
        """Usa a API nativa do Ollama, que permite limitar o KV cache."""
        base = url_http.strip().rstrip("/")
        if base.endswith("/api/chat"):
            return base
        if base.endswith("/v1"):
            base = base[:-3].rstrip("/")
        return f"{base}/api/chat"

    def _montar_payload(self, _limite_tokens: int) -> dict[str, Any]:
        """Mantém o contexto pequeno para modelos locais com pouca memória."""
        return {
            "model": self.modelo,
            "messages": self._historico_para_payload(),
            "stream": False,
            "options": {
                "temperature": 0.2,
                "num_ctx": self.NUMERO_TOKENS_CONTEXTO,
                "num_predict": self.NUMERO_TOKENS_RESPOSTA,
            },
        }

    @classmethod
    def _motivo_resposta_invalida(
        cls,
        pergunta: str,
        resposta: str,
    ) -> str | None:
        motivo = super()._motivo_resposta_invalida(pergunta, resposta)
        if motivo is not None:
            return motivo
        menor = resposta.casefold()
        if any(marcador in menor for marcador in cls.MARCADORES_RESPOSTA_SUSPEITA):
            return "contém link ou metadado que não foi solicitado"
        if len(resposta.strip()) > 500:
            return "é longa demais para uma resposta de aprendizagem"
        return None

    def responder(self, pergunta: str) -> str:
        """Responde com texto curto e normaliza perguntas de confirmação."""
        resposta = super().responder(pergunta)
        if "[s/n]" not in pergunta.casefold():
            return resposta

        normalizada = resposta.strip().casefold().lstrip("\"'“” ")
        if normalizada.startswith(("sim", "s", "yes", "y")):
            return "sim"
        if normalizada.startswith(("não", "nao", "n", "no")):
            return "não"
        raise RuntimeError(
            "o Professor Llama não respondeu uma confirmação com sim ou não"
        )
