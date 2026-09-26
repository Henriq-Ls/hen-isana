# _LOGS_/log.py
"""
Logger — Singleton de logging unificado do projeto.

Gera UM único arquivo: LOG_GERAL.log
  → recebe tudo em ordem cronológica: ok / info / aviso / erro / crash / fault
  → faulthandler (crash nativo C/Qt) também aponta para ele diretamente

conversa.log é uma view legível derivada dos eventos de conversa escritos no
LOG_GERAL.log. Ele nunca recebe eventos por uma chamada independente.

Pasta: PASTA_APPDATA/logs/  (constante definida em _CONFIGURA_)

Regras obrigatórias:
  - Singleton — uma única instância durante toda a vida do processo
  - Recria o arquivo a cada sessão — não acumula entre execuções
  - Todo open/write dentro de try/except silencioso — JAMAIS trava a UI
  - Pasta criada automaticamente se não existir
"""
import os
import datetime
import faulthandler
import json
import threading

from _CONFIGURA_ import PASTA_APPDATA, MODO_DEV


_TIPOS_CONVERSA = {
    "ENTRADA_USUARIO",
    "PERGUNTA_APRENDIZAGEM",
    "RESPOSTA_USUARIO",
    "RESPOSTA_SISTEMA",
}


def _pasta_logs() -> str:
    try:
        pasta = os.path.join(PASTA_APPDATA, "logs")
        os.makedirs(pasta, exist_ok=True)
        return pasta
    except Exception:
        # O logger nunca deve impedir o sistema de iniciar.
        return os.getcwd()


class Logger:
    """Singleton — única instância durante toda a vida do processo."""
    _inst: "Logger | None" = None

    @classmethod
    def instancia(cls) -> "Logger":
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst

    def __init__(self):
        self._pasta = _pasta_logs()
        self._session = datetime.datetime.now().strftime(
            "%Y-%m-%d %H:%M:%S"
        )
        self._lock = threading.RLock()

        # Único arquivo de log — recriado a cada sessão
        self.caminho_geral = os.path.join(self._pasta, "LOG_GERAL.log")
        self.caminho_conversa = os.path.join(self._pasta, "conversa.log")

        self._recriar_arquivo(self.caminho_geral)
        self._recriar_arquivo(self.caminho_conversa)

        # Cabeçalho de sessão
        modo = "DEV" if MODO_DEV else "PROD"
        self._escrever(f"{'═' * 60}")
        self._escrever(f"  SESSÃO INICIADA: {self._session}  [MODO: {modo}]")
        self._escrever(f"{'═' * 60}")

        # faulthandler aponta direto para o LOG_GERAL
        # (crash nativo C/Qt escreve inline, mantendo ordem cronológica)
        try:
            self._arq_fault = open(self.caminho_geral, "a", encoding="utf-8")
            self._arq_fault.write(
                f"\n{'═' * 60}\n  FAULTHANDLER ATIVO\n{'═' * 60}\n"
            )
            self._arq_fault.flush()
            faulthandler.enable(file=self._arq_fault)
        except Exception:
            pass

    # ── API pública ──────────────────────────────────────────────────────────

    def ok(self, modulo: str, funcao: str, msg: str):
        """Operação completou com sucesso. Só registra em MODO_DEV."""
        if MODO_DEV:
            self._log("OK   ", modulo, funcao, msg)

    def info(self, modulo: str, funcao: str, msg: str):
        """Fluxo normal do código. Só registra em MODO_DEV."""
        if MODO_DEV:
            self._log("INFO ", modulo, funcao, msg)

    def aviso(self, modulo: str, funcao: str, msg: str):
        """Algo inesperado mas o app continua. Sempre registra."""
        self._log("AVISO", modulo, funcao, msg)

    def erro(self, modulo: str, funcao: str, msg: str):
        """Exceção capturada em try/except. Sempre registra."""
        self._log("ERRO ", modulo, funcao, msg)

    def crash(self, modulo: str, funcao: str, texto: str):
        """Exceção não tratada — chegou ao sys.excepthook."""
        self._secao("CRASH")
        self._escrever(f"[CRASH] [{modulo}.{funcao}]")
        self._escrever(texto.strip())
        self._fim_secao()

    def fault(self, texto: str):
        """Dump manual de faulthandler (crash nativo C/Qt)."""
        self._secao("FAULTHANDLER")
        self._escrever(texto.strip())
        self._fim_secao()

    def evento(
        self,
        tipo: str,
        modulo: str,
        funcao: str,
        dados: dict | None = None,
        mensagem: str = "",
    ):
        """Registra um evento rastreável em formato JSON de uma linha.

        Eventos são sempre registrados, inclusive em modo de produção, porque
        representam o caminho real da IA: entrada, decisão, ação, resposta,
        aprendizagem e falha.
        """
        registro = {
            "timestamp": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "evento": tipo,
            "modulo": modulo,
            "funcao": funcao,
            "mensagem": mensagem,
            "dados": dados or {},
        }
        try:
            texto = json.dumps(
                registro,
                ensure_ascii=False,
                default=str,
                separators=(",", ":"),
            )
        except Exception as erro:
            texto = json.dumps(
                {
                    "evento": "ERRO_LOG_SERIALIZACAO",
                    "modulo": modulo,
                    "funcao": funcao,
                    "mensagem": str(erro),
                },
                ensure_ascii=False,
            )
        self._escrever_evento(texto, registro)

    def entrada_usuario(self, texto: str):
        """Registra exatamente o texto recebido do usuário."""
        self.evento(
            "ENTRADA_USUARIO",
            "main",
            "terminal",
            {"texto": texto},
        )

    def resposta_sistema(self, texto: str):
        """Registra uma resposta que o sistema exibiu."""
        self.evento(
            "RESPOSTA_SISTEMA",
            "main",
            "terminal",
            {"texto": texto},
        )

    def pergunta_aprendizagem(self, termo: str, campo: str, texto: str):
        """Registra uma pergunta feita para aprender um termo."""
        self.evento(
            "PERGUNTA_APRENDIZAGEM",
            "main",
            "aprender_termo",
            {
                "termo": termo,
                "campo": campo,
                "pergunta": texto,
            },
        )

    def resposta_usuario(
        self,
        termo: str,
        campo: str,
        texto: str,
    ):
        """Registra a resposta do usuário a uma pergunta de aprendizagem."""
        self.evento(
            "RESPOSTA_USUARIO",
            "main",
            "aprender_termo",
            {
                "termo": termo,
                "campo": campo,
                "resposta": texto,
            },
        )

    def passo(
        self,
        modulo: str,
        funcao: str,
        etapa: str,
        dados: dict | None = None,
    ):
        """Registra por qual etapa interna o fluxo está passando."""
        self.evento(
            "PASSO",
            modulo,
            funcao,
            dados,
            mensagem=etapa,
        )

    def acao(
        self,
        modulo: str,
        funcao: str,
        acao: str,
        dados: dict | None = None,
    ):
        """Registra uma ação disparada pelo sistema ou por uma ferramenta."""
        self.evento(
            "ACAO",
            modulo,
            funcao,
            dados,
            mensagem=acao,
        )

    def aprendizado(
        self,
        termo: str,
        dados: dict | None = None,
    ):
        """Registra o momento em que um termo foi salvo como aprendido."""
        self.evento(
            "APRENDIZADO",
            "bancos.conhecimento",
            "salvar_termo",
            {"termo": termo, **(dados or {})},
        )

    def falha(
        self,
        modulo: str,
        funcao: str,
        erro: str,
        dados: dict | None = None,
    ):
        """Registra falha capturada sem interromper o logger."""
        self.evento(
            "FALHA",
            modulo,
            funcao,
            dados,
            mensagem=erro,
        )

    def fim_sessao(self):
        """Marca o encerramento normal da sessão."""
        self.evento(
            "SESSAO_ENCERRADA",
            "logger",
            "fim_sessao",
            {"sessao": self._session},
        )

    @property
    def pasta(self) -> str:
        """Pasta onde fica o LOG_GERAL.log."""
        return self._pasta

    # ── Interno ──────────────────────────────────────────────────────────────

    def _log(self, nivel: str, modulo: str, funcao: str, msg: str):
        self._escrever(f"[{nivel}] [{modulo}.{funcao}] {msg}")

    def _secao(self, titulo: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        linha = f"\n[{ts}] {'═' * 20} {titulo} {'═' * 20}"
        try:
            with open(self.caminho_geral, "a", encoding="utf-8") as f:
                f.write(linha + "\n")
        except Exception:
            pass

    def _fim_secao(self):
        try:
            with open(self.caminho_geral, "a", encoding="utf-8") as f:
                f.write(f"{'─' * 60}\n")
        except Exception:
            pass

    def _escrever_evento(self, texto: str, registro: dict):
        """Escreve o evento geral e, depois, sua view de conversa.

        O evento geral é sempre tentado primeiro. A view só é gerada depois
        que a linha de LOG_GERAL.log foi escrita com sucesso, mantendo o log
        geral como fonte de verdade.
        """
        try:
            with self._lock:
                with open(self.caminho_geral, "a", encoding="utf-8") as arquivo:
                    arquivo.write(f"[EVENTO] {texto}\n")
                if registro.get("evento") in _TIPOS_CONVERSA:
                    self._escrever_linha_conversa(registro)
        except Exception:
            pass  # o logger jamais pode travar a UI

    def _escrever_linha_conversa(self, registro: dict):
        """Projeta um evento de conversa em uma linha de texto simples."""
        evento = registro.get("evento")
        campos = {
            "ENTRADA_USUARIO": ("Usuário", "texto"),
            "PERGUNTA_APRENDIZAGEM": ("hen-isana (pergunta)", "pergunta"),
            "RESPOSTA_USUARIO": ("Usuário", "resposta"),
            "RESPOSTA_SISTEMA": ("hen-isana", "texto"),
        }
        prefixo, campo = campos[evento]
        dados = registro.get("dados") or {}
        texto = str(dados.get(campo, "")).replace("\r", " ").replace("\n", " ")
        timestamp = str(registro.get("timestamp", ""))
        try:
            with open(self.caminho_conversa, "a", encoding="utf-8") as arquivo:
                arquivo.write(f"[{timestamp}] {prefixo}: {texto}\n")
        except Exception:
            pass

    @staticmethod
    def _recriar_arquivo(caminho: str):
        try:
            with open(caminho, "w", encoding="utf-8") as arquivo:
                arquivo.write("")
        except Exception:
            pass

    def _escrever(self, msg: str):
        ts = datetime.datetime.now().strftime("%H:%M:%S.%f")[:-3]
        try:
            with self._lock:
                with open(
                    self.caminho_geral,
                    "a",
                    encoding="utf-8",
                ) as f:
                    f.write(f"[{ts}] {msg}\n")
        except Exception:
            pass  # o logger jamais pode travar a UI


# Instância singleton exportada
log: Logger = Logger.instancia()
