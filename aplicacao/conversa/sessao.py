"""Ciclo interativo da conversa local."""

from __future__ import annotations

import sys
from typing import Optional

from _LOGS_ import log
from ..aprendizagem.cascata import CascataAprendizagem
from bancos.conhecimento import ConhecimentoDB
from bancos.propostas_aprendizagem import PropostasAprendizagem
from bancos.relacoes import RelacoesDB
from core.contexto_conversa import ContextoConversa
from protocolo.verificador import Permissao


def _input_alinhado(pergunta: str) -> str:
    """Emite o prompt antes de ler uma linha, sem descartar respostas válidas.

    Um `tcflush(TCIFLUSH)` descartaria linhas legítimas já enfileiradas por um
    PTY de teste. O alinhamento seguro é drenar a saída antes da leitura e
    deixar a validação do fluxo rejeitar linhas de controle ou eco.
    """
    sys.stdout.flush()
    return input(pergunta)


def executar_conversa_pessoal(
    banco: ConhecimentoDB,
    relacoes: RelacoesDB,
    *,
    modo_aprendizagem: bool,
    usar_internet: bool,
    permissao_memoria: Optional[Permissao] = None,
    permissao_relacao: Optional[Permissao] = None,
    propostas: Optional[PropostasAprendizagem] = None,
) -> None:
    """Executa conversa ou aprendizagem manual/online no terminal."""
    from ..fluxo import _eh_comando_proposta, processar_frase

    if modo_aprendizagem:
        if usar_internet:
            print(
                "\nModo aprendizagem pela internet ativo. A Isana buscará "
                "sugestões públicas e pedirá confirmação."
            )
        else:
            print(
                "\nModo aprendizagem manual ativo. A Isana perguntará os "
                "campos que faltarem."
            )
    else:
        print(
            "\nModo conversa ativo. Termos desconhecidos não serão salvos; "
            "a Isana informará o que ainda não entende."
        )
    print("Digite 'sair' para encerrar.")
    if modo_aprendizagem and propostas is not None:
        from ..aprendizagem.sessao import imprimir_comandos_propostas

        imprimir_comandos_propostas()
    contexto = None if modo_aprendizagem else ContextoConversa()
    cascata = (
        CascataAprendizagem(
            banco,
            relacoes,
            origem_resposta="usuario",
            permissao_memoria=permissao_memoria,
            permissao_relacao=permissao_relacao,
            componente_log="aprendizagem",
            usar_internet=usar_internet,
        )
        if modo_aprendizagem
        else None
    )

    while True:
        try:
            frase = input("\nhen-isana> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nEncerrando.")
            break

        log.entrada_usuario(frase)
        if frase.lower() in {"sair", "exit", "quit"}:
            print("Encerrando.")
            log.resposta_sistema("Encerrando.")
            break
        if not frase:
            continue

        try:
            if cascata is not None:
                cascata.registrar_entrada(frase)

                def ler_resposta_usuario(pergunta: str) -> str:
                    return _input_alinhado(pergunta)

                def responder_usuario(pergunta: str) -> str:
                    resposta = ler_resposta_usuario(pergunta)
                    if not _eh_comando_proposta(frase):
                        cascata.registrar_resposta(pergunta, resposta)
                    return resposta

                respostas = processar_frase(
                    frase,
                    banco,
                    perguntar=responder_usuario,
                    relacoes=relacoes,
                    usar_internet=usar_internet,
                    modo_aprendizagem=modo_aprendizagem,
                    permissao_memoria=permissao_memoria,
                    permissao_relacao=permissao_relacao,
                    contexto=contexto,
                    propostas=propostas,
                    ao_aceitar_sugestao=(
                        cascata.registrar_conteudo_confirmado
                    ),
                )
                cascata.processar_pendentes(ler_resposta_usuario)
            else:
                respostas = processar_frase(
                    frase,
                    banco,
                    relacoes=relacoes,
                    usar_internet=usar_internet,
                    modo_aprendizagem=modo_aprendizagem,
                    permissao_memoria=permissao_memoria,
                    permissao_relacao=permissao_relacao,
                    contexto=contexto,
                    propostas=propostas,
                )
        except Exception as erro:
            log.falha(
                "aplicacao",
                "executar_conversa_pessoal",
                str(erro),
                {"frase": frase},
            )
            print(f"Falha controlada: {erro}")
            continue
        finally:
            if cascata is not None:
                cascata.limpar_termos_em_cadeia()

        if respostas:
            for resposta in respostas:
                print(f"hen-isana: {resposta}")
                log.resposta_sistema(resposta)
        else:
            mensagem = "Ainda não tenho uma resposta completa para isso."
            print(mensagem)
            log.resposta_sistema(mensagem)