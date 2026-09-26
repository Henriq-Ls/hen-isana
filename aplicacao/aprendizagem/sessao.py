"""Sessão de aprendizagem assistida pelo professor."""

from __future__ import annotations

from typing import Optional

from _LOGS_ import log
from bancos.conhecimento import ConhecimentoDB
from bancos.propostas_aprendizagem import PropostasAprendizagem
from bancos.relacoes import RelacoesDB
from professor import Professor, ProfessorRateLimitError
from protocolo.verificador import Permissao

from .cascata import CascataAprendizagem


def imprimir_comandos_propostas() -> None:
    """Mostra os comandos de auditoria disponíveis durante a aprendizagem."""
    print(
        "Propostas explícitas (não são aplicadas automaticamente):\n"
        "- proposta-termo: termo | campo | valor [| contexto-alvo]\n"
        "- proposta-fato: afirmação\n"
        "- proposta-correcao-fato: ID | nova afirmação\n"
        "- listar-propostas; aprovar-proposta: ID; aplicar-proposta: ID\n"
        "- recusar-proposta: ID | motivo; reverter-proposta: ID"
    )


def executar_modo_professor(
    banco: ConhecimentoDB,
    relacoes: RelacoesDB,
    *,
    permissao_memoria: Permissao,
    permissao_relacao: Permissao,
    propostas: Optional[PropostasAprendizagem] = None,
    professor_cls: type[Professor] | None = None,
    nome_professor: str = "professor",
) -> None:
    """Usa um professor para responder às perguntas de aprendizagem."""
    from ..fluxo import (
        _eh_comando_proposta,
        processar_frase,
    )
    from _APPDATA_ import appdata

    professor = (professor_cls or Professor)()
    if not professor.configurado:
        mensagem = (
            f"Modo {nome_professor} não configurado. Preencha url_http, "
            "token e modelo em "
            f"{appdata.arq_config_professor}."
        )
        print(mensagem)
        log.falha("professor", "iniciar", mensagem)
        return

    print(
        f"\nModo {nome_professor} ativo. Digite um tema ou frase para o hen-isana "
        "aprender; o professor responderá às perguntas automaticamente."
    )
    print("Digite 'sair' para voltar.")
    if propostas is not None:
        imprimir_comandos_propostas()

    cascata = CascataAprendizagem(
        banco,
        relacoes,
        origem_resposta="professor",
        permissao_memoria=permissao_memoria,
        permissao_relacao=permissao_relacao,
        componente_log="professor",
    )
    professor_indisponivel = False

    def consultar_professor(pergunta: str) -> str:
        nonlocal professor_indisponivel
        if professor_indisponivel:
            raise ProfessorRateLimitError(
                "o professor está indisponível nesta sessão por limite de uso"
            )
        print(f"\nhen-isana (pergunta ao {nome_professor}): {pergunta}")
        try:
            resposta = professor.responder(pergunta)
        except ProfessorRateLimitError:
            professor_indisponivel = True
            raise
        print(f"{nome_professor}: {resposta}")
        if "[s/n]" not in pergunta.lower():
            return resposta
        normalizada = resposta.strip().lower()
        if normalizada.startswith(("s", "yes")):
            resposta_controle = "sim"
        elif normalizada.startswith(("n", "no")):
            resposta_controle = "não"
        else:
            resposta_controle = resposta
        return resposta_controle

    def responder_professor(pergunta: str) -> str:
        resposta = consultar_professor(pergunta)
        cascata.registrar_resposta(pergunta, resposta)
        return resposta

    def tratar_falha_cascata(
        _termo: str,
        erro: Exception,
    ) -> None:
        if isinstance(erro, ProfessorRateLimitError):
            raise erro

    while True:
        try:
            frase = input("\nassunto> ").strip()
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

        cascata.registrar_entrada(frase)
        try:
            respostas = processar_frase(
                frase,
                banco,
                perguntar=(
                    input if _eh_comando_proposta(frase) else responder_professor
                ),
                relacoes=relacoes,
                origem_resposta="professor",
                usar_internet=False,
                modo_aprendizagem=True,
                permissao_memoria=permissao_memoria,
                permissao_relacao=permissao_relacao,
                propostas=propostas,
                ao_aceitar_sugestao=cascata.registrar_conteudo_confirmado,
            )
            cascata.processar_pendentes(
                consultar_professor,
                ao_falhar=tratar_falha_cascata,
            )
        except Exception as erro:
            log.falha(
                "professor",
                "executar_modo_professor",
                str(erro),
                {"frase": frase},
            )
            print(f"Falha controlada no professor: {erro}")
            continue
        finally:
            cascata.limpar_termos_em_cadeia()

        if respostas:
            for resposta in respostas:
                print(f"hen-isana: {resposta}")
                log.resposta_sistema(resposta)
        else:
            mensagem = "O professor concluiu o preenchimento deste aprendizado."
            print(mensagem)
            log.resposta_sistema(mensagem)