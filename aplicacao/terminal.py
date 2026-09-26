"""Entrada e coordenação do terminal do hen-isana."""

from __future__ import annotations

from _APPDATA_ import appdata
from _LOGS_ import log
from bancos.conhecimento import ConhecimentoDB
from bancos.indice_codigo import IndiceCodigoDB
from bancos.log_mudancas import LogMudancasDB
from bancos.propostas_aprendizagem import PropostasAprendizagem
from bancos.relacoes import RelacoesDB
from backup.diagnostico import DiagnosticoDB
from professor import ProfessorLlama
from protocolo.regras import (
    ALVO_CONHECIMENTO,
    ALVO_RELACOES,
    TipoAcao,
)
from protocolo.verificador import emitir_permissao

from .aprendizagem.sessao import executar_modo_professor
from .conversa.sessao import executar_conversa_pessoal


def _escolher_modo() -> str:
    """Escolhe entre testar a conversa e iniciar uma aprendizagem."""
    print("\nEscolha o modo de execução:")
    print("1 - Conversa")
    print("2 - Aprendizagem")
    while True:
        opcao = input("Modo [1/2]: ").strip().lower()
        if opcao in {"1", "c", "conversa", "conversar"}:
            return "conversa"
        if opcao in {"2", "a", "aprendizagem", "aprender"}:
            return "aprendizagem"
        print("Escolha 1 para conversa ou 2 para aprendizagem.")


def _escolher_fonte_aprendizagem() -> str:
    """Escolhe quem fornece a sugestão para um termo desconhecido."""
    print("\nEscolha a fonte da aprendizagem:")
    print("1 - Conversar e ensinar manualmente")
    print("2 - Consultar o professor")
    print("3 - Pesquisar na internet e confirmar")
    print("4 - Usar o Llama local do Ollama")
    while True:
        opcao = input("Fonte [1/2/3/4]: ").strip().lower()
        if opcao in {"1", "manual", "pessoal"}:
            return "manual"
        if opcao in {"2", "professor", "prof"}:
            return "professor"
        if opcao in {"3", "internet", "web"}:
            return "internet"
        if opcao in {"4", "llama", "ollama"}:
            return "llama"
        print(
            "Escolha 1 para manual, 2 para professor, 3 para internet "
            "ou 4 para Llama local."
        )


def executar_terminal() -> None:
    """Executa o ciclo interativo do sistema."""
    appdata.inicializar()
    log.passo(
        "aplicacao",
        "executar_terminal",
        "sessão do terminal iniciada",
        {"appdata": appdata.pasta_raiz, "log": log.caminho_geral},
    )
    print("hen-isana iniciado.")
    try:
        with (
            ConhecimentoDB() as banco,
            RelacoesDB() as relacoes,
            IndiceCodigoDB() as indice_codigo,
            LogMudancasDB() as log_mudancas,
            DiagnosticoDB() as diagnostico,
        ):
            del indice_codigo, log_mudancas, diagnostico
            modo = _escolher_modo()
            log.passo(
                "aplicacao",
                "executar_terminal",
                "modo selecionado",
                {"modo": modo},
            )
            if modo == "conversa":
                executar_conversa_pessoal(
                    banco,
                    relacoes,
                    modo_aprendizagem=False,
                    usar_internet=False,
                )
            else:
                propostas = PropostasAprendizagem(banco)
                fonte = _escolher_fonte_aprendizagem()
                log.passo(
                    "aplicacao",
                    "executar_terminal",
                    "fonte de aprendizagem selecionada",
                    {"fonte": fonte},
                )
                permissao_memoria = emitir_permissao(
                    TipoAcao.SALVAR_CONHECIMENTO,
                    ALVO_CONHECIMENTO,
                )
                permissao_relacao = emitir_permissao(
                    TipoAcao.SALVAR_RELACAO,
                    ALVO_RELACOES,
                )
                if fonte == "professor":
                    executar_modo_professor(
                        banco,
                        relacoes,
                        permissao_memoria=permissao_memoria,
                        permissao_relacao=permissao_relacao,
                        propostas=propostas,
                    )
                elif fonte == "llama":
                    executar_modo_professor(
                        banco,
                        relacoes,
                        permissao_memoria=permissao_memoria,
                        permissao_relacao=permissao_relacao,
                        propostas=propostas,
                        professor_cls=ProfessorLlama,
                        nome_professor="Professor Llama",
                    )
                else:
                    executar_conversa_pessoal(
                        banco,
                        relacoes,
                        modo_aprendizagem=True,
                        usar_internet=fonte == "internet",
                        permissao_memoria=permissao_memoria,
                        permissao_relacao=permissao_relacao,
                        propostas=propostas,
                    )
    finally:
        log.fim_sessao()
