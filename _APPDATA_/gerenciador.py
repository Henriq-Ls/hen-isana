# _APPDATA_/gerenciador.py
"""
GerenciadorAppData — Singleton Facade do AppData

Ponto ÚNICO de acesso a tudo que vive em PASTA_APPDATA (definida em _CONFIGURA_).
Nenhum módulo deve montar caminhos de AppData na mão — todos consultam esta classe.

Uso:
    from _APPDATA_ import appdata
    appdata.inicializar()
    print(appdata.pasta_raiz)
"""

import os
import json
import datetime


# Import tardio para evitar dependência circular na inicialização
def _log():
    from _LOGS_ import log as _l
    return _l


class GerenciadorAppData:
    """Singleton — instância única durante toda a vida do processo."""
    _inst: "GerenciadorAppData | None" = None

    @classmethod
    def instancia(cls) -> "GerenciadorAppData":
        if cls._inst is None:
            cls._inst = cls()
        return cls._inst

    def __init__(self):
        from _CONFIGURA_ import PASTA_APPDATA
        self._raiz = PASTA_APPDATA
        self._inicializado = False

    # ── Inicialização ────────────────────────────────────────────────────────

    def inicializar(self):
        """
        Garante toda a estrutura de pastas e arquivos padrão.
        Deve ser chamado UMA vez no startup, antes de qualquer acesso.
        """
        if self._inicializado:
            return

        os.makedirs(self._raiz,          exist_ok=True)
        os.makedirs(self.pasta_logs,     exist_ok=True)
        os.makedirs(self.pasta_config,   exist_ok=True)
        os.makedirs(self.pasta_cache,    exist_ok=True)
        os.makedirs(self.pasta_projetos, exist_ok=True)
        os.makedirs(self.pasta_professor, exist_ok=True)

        self._garantir_config_padrao()
        self._garantir_config_professor()
        self._inicializado = True
        _log().ok("AppData", "inicializar", f"pasta_raiz={self._raiz}")

    # ── Caminhos canônicos ────────────────────────────────────────────────────
    # Sempre use estas properties — nunca monte caminhos na mão fora daqui

    @property
    def pasta_raiz(self) -> str:
        return self._raiz

    @property
    def pasta_logs(self) -> str:
        return os.path.join(self._raiz, "logs")

    @property
    def pasta_config(self) -> str:
        return os.path.join(self._raiz, "config")

    @property
    def pasta_cache(self) -> str:
        return os.path.join(self._raiz, "cache")

    @property
    def pasta_projetos(self) -> str:
        return os.path.join(self._raiz, "projetos")

    @property
    def pasta_professor(self) -> str:
        """Pasta das configurações da IA externa que ensina o hen-isana."""
        return os.path.join(self._raiz, "professor")

    @property
    def arq_config(self) -> str:
        return os.path.join(self.pasta_config, "config.json")

    @property
    def arq_sessao(self) -> str:
        return os.path.join(self.pasta_config, "sessao.json")

    @property
    def arq_config_professor(self) -> str:
        return os.path.join(self.pasta_professor, "config.json")

    @property
    def arq_historico_professor(self) -> str:
        return os.path.join(self.pasta_professor, "historico.json")

    @property
    def arq_cache_professor(self) -> str:
        return os.path.join(self.pasta_professor, "cache_respostas.json")

    # ── Config ────────────────────────────────────────────────────────────────

    def ler_config(self) -> dict:
        """Lê config.json. Retorna {} em caso de falha."""
        try:
            with open(self.arq_config, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            _log().aviso("AppData", "ler_config", f"falha ao ler config.json: {e}")
            return {}

    def salvar_config(self, dados: dict):
        """Salva dict no config.json."""
        try:
            with open(self.arq_config, "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=2, ensure_ascii=False)
        except Exception as e:
            _log().erro("AppData", "salvar_config", f"falha ao salvar config.json: {e}")

    def restaurar_padrao(self):
        """Apaga config.json e recria com valores padrão de fábrica."""
        if os.path.exists(self.arq_config):
            os.remove(self.arq_config)
        self._garantir_config_padrao()
        _log().ok("AppData", "restaurar_padrao", "config restaurado ao padrão")

    # ── IA externa professor ──────────────────────────────────────────────────

    def ler_config_professor(self) -> dict:
        """Lê a configuração da IA externa sem expor seus campos no log."""
        self.inicializar()
        try:
            with open(self.arq_config_professor, "r", encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
        except (OSError, json.JSONDecodeError) as erro:
            _log().erro(
                "AppData",
                "ler_config_professor",
                f"falha ao ler configuração do professor: {erro}",
            )
            return {}
        return dados if isinstance(dados, dict) else {}

    def salvar_config_professor(self, dados: dict) -> None:
        """Salva a configuração da IA externa em arquivo próprio."""
        os.makedirs(self.pasta_professor, exist_ok=True)
        temporario = f"{self.arq_config_professor}.tmp"
        try:
            with open(temporario, "w", encoding="utf-8") as arquivo:
                json.dump(dados, arquivo, indent=2, ensure_ascii=False)
                arquivo.write("\n")
            os.replace(temporario, self.arq_config_professor)
            try:
                os.chmod(self.arq_config_professor, 0o600)
            except OSError:
                pass
        except OSError as erro:
            try:
                os.remove(temporario)
            except OSError:
                pass
            _log().erro(
                "AppData",
                "salvar_config_professor",
                f"falha ao salvar configuração do professor: {erro}",
            )
            raise

    def ler_historico_professor(self) -> list[dict[str, str]]:
        """Lê o histórico curto persistido, sem expor seu conteúdo no log."""
        dados = self._ler_json_professor(self.arq_historico_professor)
        mensagens = dados.get("mensagens") if isinstance(dados, dict) else None
        if not isinstance(mensagens, list):
            return []
        resultado = []
        for mensagem in mensagens:
            if not isinstance(mensagem, dict):
                continue
            papel = mensagem.get("role")
            conteudo = mensagem.get("content")
            if papel in {"user", "assistant"} and isinstance(conteudo, str):
                texto = conteudo.strip()
                if texto:
                    resultado.append({"role": papel, "content": texto})
        return resultado

    def salvar_historico_professor(
        self,
        mensagens: list[dict[str, str]],
    ) -> None:
        """Salva somente trocas já concluídas do professor."""
        limpas = [
            {
                "role": mensagem["role"],
                "content": mensagem["content"],
            }
            for mensagem in mensagens
            if isinstance(mensagem, dict)
            and mensagem.get("role") in {"user", "assistant"}
            and isinstance(mensagem.get("content"), str)
            and mensagem["content"].strip()
        ]
        self._salvar_json_professor(
            self.arq_historico_professor,
            {"versao": 1, "mensagens": limpas},
        )

    def ler_cache_professor(self) -> dict[str, str]:
        """Lê respostas aceitas indexadas pela pergunta normalizada."""
        dados = self._ler_json_professor(self.arq_cache_professor)
        respostas = dados.get("respostas") if isinstance(dados, dict) else None
        if not isinstance(respostas, dict):
            return {}
        return {
            str(chave): str(valor)
            for chave, valor in respostas.items()
            if isinstance(valor, str) and valor.strip()
        }

    def salvar_cache_professor(self, respostas: dict[str, str]) -> None:
        """Salva o cache local de respostas sem incluir configuração secreta."""
        limite = 512
        itens = list(respostas.items())[-limite:]
        self._salvar_json_professor(
            self.arq_cache_professor,
            {"versao": 1, "respostas": dict(itens)},
        )

    def _ler_json_professor(self, caminho: str) -> dict:
        self.inicializar()
        try:
            with open(caminho, "r", encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
        except (OSError, json.JSONDecodeError):
            return {}
        return dados if isinstance(dados, dict) else {}

    def _salvar_json_professor(self, caminho: str, dados: dict) -> None:
        os.makedirs(self.pasta_professor, exist_ok=True)
        temporario = f"{caminho}.tmp"
        try:
            with open(temporario, "w", encoding="utf-8") as arquivo:
                json.dump(dados, arquivo, indent=2, ensure_ascii=False)
                arquivo.write("\n")
            os.replace(temporario, caminho)
            try:
                os.chmod(caminho, 0o600)
            except OSError:
                pass
        except OSError as erro:
            try:
                os.remove(temporario)
            except OSError:
                pass
            _log().erro(
                "AppData",
                "_salvar_json_professor",
                f"falha ao salvar arquivo do professor: {erro}",
            )
            raise

    # ── Sessão (geometria, estado da janela) ──────────────────────────────────

    def ler_sessao(self) -> dict:
        """Lê sessao.json. Retorna {} em caso de falha."""
        try:
            with open(self.arq_sessao, "r", encoding="utf-8") as f:
                dados = json.load(f)
            _log().ok("AppData", "ler_sessao", f"sessão restaurada: {list(dados.keys())}")
            return dados
        except Exception:
            _log().info("AppData", "ler_sessao", "sessao.json ausente — usando padrão")
            return {}

    def salvar_sessao(self, dados: dict):
        """Persiste dados de sessão em sessao.json."""
        try:
            with open(self.arq_sessao, "w", encoding="utf-8") as f:
                json.dump(dados, f, indent=2, ensure_ascii=False)
            _log().ok("AppData", "salvar_sessao", f"sessão salva: {list(dados.keys())}")
        except Exception as e:
            _log().erro("AppData", "salvar_sessao", f"falha ao salvar sessao.json: {e}")

    # ── Internos ──────────────────────────────────────────────────────────────

    def _garantir_config_padrao(self):
        if not os.path.exists(self.arq_config):
            from _CONFIGURA_ import VERSAO_APP, TEMA_QT
            padrao = {
                "tema":    TEMA_QT,
                "versao":  VERSAO_APP,
                "criado":  datetime.datetime.now().isoformat(),
            }
            self.salvar_config(padrao)

    def _garantir_config_professor(self):
        if not os.path.exists(self.arq_config_professor):
            self.salvar_config_professor(
                {
                    "url_http": "",
                    "token": "",
                    "modelo": "",
                }
            )
