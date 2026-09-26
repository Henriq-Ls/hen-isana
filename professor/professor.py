"""Professor externo que responde às perguntas de aprendizagem do hen-isana.

Na primeira execução, o AppData cria ``professor/config.json``. Preencha esse
arquivo uma vez; a configuração não fica no código do projeto.
O módulo usa somente a biblioteca padrão e espera uma resposta compatível com
a API de chat da OpenAI. Também aceita a resposta simples do Ollama.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

from _APPDATA_ import appdata
from _LOGS_ import log


class ProfessorRateLimitError(RuntimeError):
    """Indica que o provedor recusou a chamada por limite de uso."""


class Professor:
    """Conexão isolada com a IA que ensina o hen-isana."""

    VERSAO_CACHE = "2"
    LIMITE_TOKENS = 512
    LIMITE_TOKENS_REPETICAO = 768
    MAXIMO_MENSAGENS_DE_CONTEXTO = 6

    INSTRUCAO = (
        "Você é o professor de uma IA simbólica chamada hen-isana. "
        "Responda em português. Você está respondendo uma pergunta de "
        "aprendizagem, então forneça somente a informação pedida, de forma "
        "clara, objetiva e sem markdown. Não invente arquivos, código ou "
        "ações executadas. Nunca escreva classificações de segurança, "
        "rótulos como 'User Safety' ou 'Response Safety', JSON, cabeçalhos "
        "técnicos ou explicações sobre suas regras internas."
    )

    def __init__(
        self,
        url_http: str | None = None,
        token: str | None = None,
        modelo: str | None = None,
        timeout: float = 180.0,
    ) -> None:
        configuracao = appdata.ler_config_professor()
        self.url_http = str(
            url_http if url_http is not None else configuracao.get("url_http", "")
        ).strip()
        self.token = str(
            token if token is not None else configuracao.get("token", "")
        ).strip()
        self.modelo = str(
            modelo if modelo is not None else configuracao.get("modelo", "")
        ).strip()
        self.timeout = timeout
        self._historico: list[dict[str, str]] = [
            {"role": "system", "content": self.INSTRUCAO}
        ]
        self._historico.extend(
            appdata.ler_historico_professor()[
                -self.MAXIMO_MENSAGENS_DE_CONTEXTO :
            ]
        )
        self._cache_respostas = appdata.ler_cache_professor()

    @property
    def configurado(self) -> bool:
        """Indica se há endereço e modelo suficientes para uma chamada."""
        return bool(self.url_http and self.modelo)

    def responder(self, pergunta: str) -> str:
        """Responde uma pergunta feita durante o aprendizado de um termo."""
        if not isinstance(pergunta, str) or not pergunta.strip():
            raise ValueError("a pergunta do professor precisa ser texto")

        log.evento(
            "PERGUNTA_PROFESSOR",
            "professor",
            "responder",
            {"texto": pergunta},
        )
        chave_cache = self._chave_cache(pergunta)
        resposta_cache = self._cache_respostas.get(chave_cache)
        if resposta_cache:
            self._registrar_troca_local(
                self._instruir_pergunta(pergunta),
                resposta_cache,
            )
            log.evento(
                "CACHE_PROFESSOR",
                "professor",
                "responder",
                {"modelo": self.modelo},
                mensagem="resposta local reutilizada sem chamada externa",
            )
            return resposta_cache

        resposta = self.conversar(self._instruir_pergunta(pergunta))
        motivo = self._motivo_resposta_invalida(pergunta, resposta)
        if motivo is None:
            resposta_limpa = self._limpar_resposta(pergunta, resposta)
            self._guardar_cache(chave_cache, resposta_limpa)
            return resposta_limpa

        # Alguns roteadores podem devolver metadados de moderação, raciocínio
        # ou uma explicação longa em vez da resposta final. Remova a troca
        # inválida e dê uma única oportunidade para o professor responder no
        # formato que o banco consegue armazenar.
        self._remover_ultima_troca()
        resposta = self.conversar(
            "A resposta anterior foi inválida porque "
            f"{motivo}. Responda agora somente ao pedido abaixo, "
            "em texto simples, sem rótulos, cabeçalhos, raciocínio ou "
            "classificações de segurança:\n"
            + pergunta
        )
        motivo = self._motivo_resposta_invalida(pergunta, resposta)
        if motivo is not None:
            self._remover_ultima_troca()
            raise RuntimeError(
                "o professor não retornou uma resposta válida: " + motivo
            )
        resposta_limpa = self._limpar_resposta(pergunta, resposta)
        self._guardar_cache(chave_cache, resposta_limpa)
        return resposta_limpa

    def conversar(self, texto: str) -> str:
        """Envia uma mensagem e devolve o texto da IA externa."""
        if not isinstance(texto, str) or not texto.strip():
            raise ValueError("a mensagem do professor precisa ser texto")
        if not self.configurado:
            raise RuntimeError(
                "modo professor não configurado: preencha "
                f"{appdata.arq_config_professor}"
            )

        self._historico.append({"role": "user", "content": texto})
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        resposta: dict[str, Any] | None = None
        try:
            resposta = self._post_json(
                self._url_chat(self.url_http),
                self._montar_payload(self.LIMITE_TOKENS),
                headers,
            )
            try:
                texto_resposta = self._extrair_texto(resposta)
            except RuntimeError:
                if not self._resposta_sem_texto_visivel(resposta):
                    raise
                log.evento(
                    "AVISO",
                    "professor",
                    "conversar",
                    dados=self._metadados_resposta(
                        resposta,
                        limite_tokens=self.LIMITE_TOKENS,
                    ),
                    mensagem=(
                        "resposta sem texto visível; repetindo com "
                        "orçamento maior"
                    ),
                )
                resposta = self._post_json(
                    self._url_chat(self.url_http),
                    self._montar_payload(self.LIMITE_TOKENS_REPETICAO),
                    headers,
                )
                texto_resposta = self._extrair_texto(resposta)
        except Exception as erro:
            self._historico.pop()
            log.falha(
                "professor",
                "conversar",
                str(erro),
                {
                    "modelo": self.modelo,
                    **self._metadados_resposta(resposta),
                },
            )
            raise

        self._historico.append({"role": "assistant", "content": texto_resposta})
        self._salvar_historico()
        log.evento(
            "RESPOSTA_PROFESSOR",
            "professor",
            "conversar",
            {"texto": texto_resposta, "modelo": self.modelo},
        )
        return texto_resposta

    def _montar_payload(self, limite_tokens: int) -> dict[str, Any]:
        """Monta um pedido curto sem ativar raciocínio excessivo no OpenRouter."""
        payload: dict[str, Any] = {
            "model": self.modelo,
            "messages": self._historico_para_payload(),
            "temperature": 0.2,
            "max_tokens": limite_tokens,
            "stream": False,
        }
        if self._eh_openrouter():
            payload["reasoning"] = {
                "effort": "minimal",
                "exclude": True,
            }
        return payload

    def _historico_para_payload(self) -> list[dict[str, str]]:
        """Mantém só o contexto recente para evitar raciocínio desnecessário."""
        sistema = self._historico[0]
        conversas = self._historico[1:]
        return [
            sistema,
            *conversas[-self.MAXIMO_MENSAGENS_DE_CONTEXTO :],
        ]

    def _salvar_historico(self) -> None:
        """Persiste apenas as últimas trocas concluídas da sessão."""
        self._historico = [
            self._historico[0],
            *self._historico[1:][-self.MAXIMO_MENSAGENS_DE_CONTEXTO :],
        ]
        appdata.salvar_historico_professor(self._historico[1:])

    def _registrar_troca_local(self, pergunta: str, resposta: str) -> None:
        self._historico.extend(
            [
                {"role": "user", "content": pergunta},
                {"role": "assistant", "content": resposta},
            ]
        )
        self._salvar_historico()

    def _guardar_cache(self, chave: str, resposta: str) -> None:
        self._cache_respostas[chave] = resposta
        appdata.salvar_cache_professor(self._cache_respostas)

    def _chave_cache(self, pergunta: str) -> str:
        normalizada = " ".join(pergunta.strip().casefold().split())
        return f"{self.VERSAO_CACHE}|{self.modelo.casefold()}|{normalizada}"

    def _eh_openrouter(self) -> bool:
        return "openrouter.ai" in self.url_http.lower()

    @staticmethod
    def _url_chat(url_http: str) -> str:
        base = url_http.strip().rstrip("/")
        if "://" not in base:
            base = f"https://{base}"
        partes = urlsplit(base)
        if partes.scheme not in {"http", "https"} or not partes.netloc:
            raise ValueError(f"URL HTTP inválida para o professor: {url_http!r}")
        if base.endswith("/chat/completions"):
            return base
        return f"{base}/chat/completions"

    @staticmethod
    def _instruir_pergunta(pergunta: str) -> str:
        """Adapta a pergunta ao formato curto esperado pelo banco."""
        menor = pergunta.lower()
        if "tipo ou categoria" in menor:
            regra = (
                "Retorne somente um nome curto de categoria, sem definição "
                "e sem pontuação extra."
            )
        elif "significa" in menor:
            regra = "Retorne somente uma definição curta em uma frase."
        elif "contexto" in menor:
            regra = "Retorne somente uma frase sobre o contexto de uso."
        elif "resposta devo dar" in menor:
            regra = (
                "Retorne somente a frase que o hen-isana deve dizer diretamente "
                "ao usuário quando esse termo aparecer. Isso é uma resposta "
                "real para o usuário, não uma definição do termo. Se for uma "
                "saudação, cumprimente o usuário; não explique o significado "
                "da saudação. Não use aspas."
            )
        else:
            regra = "Retorne somente a resposta direta para a pergunta."
        return f"{regra}\nPergunta: {pergunta}"

    @staticmethod
    def _limpar_resposta(pergunta: str, resposta: str) -> str:
        """Remove aspas externas da frase que será exibida ao usuário."""
        if "tipo ou categoria" in pergunta.lower():
            return Professor._categoria_curta_normalizada(resposta)
        if "resposta devo dar" not in pergunta.lower():
            return resposta
        limpa = resposta.strip()
        pares = (('"', '"'), ("“", "”"), ("'", "'"))
        for abertura, fechamento in pares:
            if (
                len(limpa) >= 2
                and limpa.startswith(abertura)
                and limpa.endswith(fechamento)
            ):
                return limpa[1:-1].strip()
        return limpa

    @staticmethod
    def _parece_metadado_de_seguranca(texto: str) -> bool:
        menor = texto.lower()
        return "user safety:" in menor or "response safety:" in menor

    @staticmethod
    def _categoria_curta_normalizada(texto: str) -> str:
        """Remove pontuação final sem alterar o rótulo retornado."""
        return " ".join(texto.strip().split()).rstrip(".!?").strip()

    @classmethod
    def _categoria_curta_valida(cls, texto: str) -> bool:
        """Aceita o rótulo curto esperado pelo campo ``tipo``."""
        normalizado = cls._categoria_curta_normalizada(texto)
        if not normalizado or len(normalizado) > 80:
            return False
        if len(normalizado.split()) > 5:
            return False
        if re.search(r"[:.!?{}\[\]\"“”'`]", normalizado):
            return False
        proibidos = (
            "i don't know",
            "i'm not sure",
            "we need to answer",
            "let me ",
            "the user ",
            "não sei",
            "não tenho certeza",
        )
        menor = normalizado.casefold()
        return not any(trecho in menor for trecho in proibidos)

    @staticmethod
    def _parece_raciocinio_exposto(texto: str) -> bool:
        """Detecta quando o provedor devolve análise interna em vez da resposta."""
        menor = " ".join(texto.casefold().split())
        marcadores = (
            "the user is asking",
            "the user's instruction",
            "let me recall",
            "wait, but",
            "possible answer",
            "the correct answer",
            "now, the user wants",
            "hmm, maybe",
            "we need to answer",
        )
        return any(marcador in menor for marcador in marcadores)

    @classmethod
    def _motivo_resposta_invalida(
        cls,
        pergunta: str,
        resposta: str,
    ) -> str | None:
        if cls._parece_metadado_de_seguranca(resposta):
            return "contém metadados de segurança"
        if cls._parece_raciocinio_exposto(resposta):
            return "contém raciocínio interno em vez da resposta final"
        if "tipo ou categoria" in pergunta.casefold():
            if not cls._categoria_curta_valida(resposta):
                return "não é um nome curto de categoria"
        return None

    def _remover_ultima_troca(self) -> None:
        """Remove a última pergunta e resposta inválidas do histórico."""
        if len(self._historico) >= 3:
            ultima = self._historico[-1]
            anterior = self._historico[-2]
            if (
                ultima.get("role") == "assistant"
                and anterior.get("role") == "user"
            ):
                del self._historico[-2:]
                self._salvar_historico()
                return
        if len(self._historico) > 1:
            self._historico.pop()
            self._salvar_historico()

    def _post_json(
        self,
        url: str,
        payload: dict[str, Any],
        headers: dict[str, str],
    ) -> dict[str, Any]:
        request = Request(
            url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json", **headers},
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                bruto = response.read().decode("utf-8", errors="replace")
        except HTTPError as erro:
            detalhe = erro.read().decode("utf-8", errors="replace")
            if erro.code == 429:
                raise ProfessorRateLimitError(
                    f"limite do professor atingido (HTTP 429): {detalhe[:500]}"
                ) from erro
            raise RuntimeError(
                f"professor respondeu HTTP {erro.code}: {detalhe[:500]}"
            ) from erro
        except URLError as erro:
            raise RuntimeError(
                f"não foi possível conectar ao professor: {erro.reason}"
            ) from erro
        except TimeoutError as erro:
            raise RuntimeError("o professor demorou demais para responder") from erro

        try:
            resultado = json.loads(bruto)
        except json.JSONDecodeError as erro:
            raise RuntimeError("o professor retornou JSON inválido") from erro
        if not isinstance(resultado, dict):
            raise RuntimeError("o professor retornou um formato inesperado")
        return resultado

    @staticmethod
    def _extrair_texto(resposta: dict[str, Any]) -> str:
        """Aceita ``choices`` da API compatível e ``message`` do Ollama."""
        erro = resposta.get("error")
        if isinstance(erro, dict):
            mensagem = str(erro.get("message", "")).strip()
            codigo = str(erro.get("code", "")).strip()
            detalhe = f"{codigo}: {mensagem}" if codigo else mensagem
            raise RuntimeError(
                "o professor retornou erro na API"
                + (f": {detalhe}" if detalhe else "")
            )

        escolhas = resposta.get("choices")
        if isinstance(escolhas, list) and escolhas:
            primeira = escolhas[0]
            if isinstance(primeira, dict):
                mensagem = primeira.get("message", {})
                if isinstance(mensagem, dict):
                    conteudo = mensagem.get("content", "")
                    texto = Professor._normalizar_conteudo(conteudo)
                    if texto:
                        return texto
                    motivo = primeira.get("finish_reason")
                    if motivo == "length":
                        raise RuntimeError(
                            "o professor esgotou o limite de tokens antes "
                            "de produzir texto visível"
                        )
                    if mensagem.get("reasoning") or mensagem.get(
                        "reasoning_details"
                    ):
                        raise RuntimeError(
                            "o professor retornou apenas raciocínio, sem "
                            "texto visível"
                        )
                    raise RuntimeError(
                        "o professor retornou uma escolha sem texto visível"
                    )
        if isinstance(escolhas, list) and not escolhas:
            raise RuntimeError("o professor retornou choices vazio")

        mensagem = resposta.get("message", {})
        if isinstance(mensagem, dict):
            texto = Professor._normalizar_conteudo(mensagem.get("content", ""))
            if texto:
                return texto

        raise RuntimeError("o professor não retornou texto")

    @staticmethod
    def _resposta_sem_texto_visivel(resposta: dict[str, Any]) -> bool:
        escolhas = resposta.get("choices")
        if not isinstance(escolhas, list) or not escolhas:
            return False
        primeira = escolhas[0]
        if not isinstance(primeira, dict):
            return False
        mensagem = primeira.get("message", {})
        if not isinstance(mensagem, dict):
            return False
        return not Professor._normalizar_conteudo(mensagem.get("content", ""))

    @staticmethod
    def _metadados_resposta(
        resposta: dict[str, Any] | None,
        *,
        limite_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Retorna diagnóstico seguro, sem registrar token ou conteúdo."""
        if not isinstance(resposta, dict):
            return {}

        dados: dict[str, Any] = {
            "chaves_resposta": sorted(str(chave) for chave in resposta),
        }
        escolhas = resposta.get("choices")
        if isinstance(escolhas, list):
            dados["quantidade_choices"] = len(escolhas)
            if escolhas and isinstance(escolhas[0], dict):
                primeira = escolhas[0]
                dados["finish_reason"] = primeira.get("finish_reason")
                mensagem = primeira.get("message")
                if isinstance(mensagem, dict):
                    dados["conteudo_vazio"] = not bool(
                        Professor._normalizar_conteudo(
                            mensagem.get("content", "")
                        )
                    )
                    dados["possui_reasoning"] = bool(
                        mensagem.get("reasoning")
                        or mensagem.get("reasoning_details")
                    )
        uso = resposta.get("usage")
        if isinstance(uso, dict):
            dados["completion_tokens"] = uso.get("completion_tokens")
            detalhes = uso.get("completion_tokens_details")
            if isinstance(detalhes, dict):
                dados["reasoning_tokens"] = detalhes.get("reasoning_tokens")
        if limite_tokens is not None:
            dados["limite_tokens"] = limite_tokens
        return dados

    @staticmethod
    def _normalizar_conteudo(conteudo: Any) -> str:
        if isinstance(conteudo, list):
            return "".join(
                str(parte.get("text", ""))
                for parte in conteudo
                if isinstance(parte, dict)
            ).strip()
        return str(conteudo or "").strip()