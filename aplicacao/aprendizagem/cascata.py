"""Cascata compartilhada entre as fontes de aprendizagem."""

from __future__ import annotations

import re
from typing import Callable, Optional

from _LOGS_ import log
from bancos.conhecimento import ConhecimentoDB
from bancos.relacoes import RelacoesDB
from protocolo.verificador import Permissao


class CascataAprendizagem:
    """Encontra e aprende termos desconhecidos nas respostas da fonte."""

    LIMITE_CANDIDATOS_POR_RESPOSTA = 4
    LIMITE_TERMOS_POR_CADEIA = 64
    LIMITE_PROFUNDIDADE_CADEIA = 2
    LIMITE_CARACTERES_RESPOSTA_CASCATA = 240

    def __init__(
        self,
        banco: ConhecimentoDB,
        relacoes: Optional[RelacoesDB],
        *,
        origem_resposta: str,
        permissao_memoria: Optional[Permissao],
        permissao_relacao: Optional[Permissao],
        componente_log: str,
        usar_internet: bool = False,
    ) -> None:
        self.banco = banco
        self.relacoes = relacoes
        self.origem_resposta = origem_resposta
        self.permissao_memoria = permissao_memoria
        self.permissao_relacao = permissao_relacao
        self.componente_log = componente_log
        self.usar_internet = usar_internet
        self.termos_em_cadeia: set[str] = set()
        self.termos_pendentes: list[str] = []
        self.profundidade_por_termo: dict[str, int] = {}
        self._profundidade_atual = 0

    def registrar_entrada(self, frase: str) -> None:
        from ..fluxo import tokenizar

        self.termos_em_cadeia.update(
            tokenizar(frase, self.banco.listar_expressoes_compostas())
        )

    def limpar_termos_em_cadeia(self) -> None:
        self.termos_em_cadeia.clear()
        self.termos_pendentes.clear()
        self.profundidade_por_termo.clear()
        self._profundidade_atual = 0

    def registrar_resposta(self, pergunta: str, resposta: str) -> None:
        from core.interpretacao import interpretar_pergunta

        resposta_controle = re.sub(
            r"[.!?]+$",
            "",
            resposta.casefold().strip(),
        )
        if resposta_controle in {
            "cancelar",
            "cancele",
            "cancel",
            "desistir",
            "abortar",
            "sair",
            "exit",
            "quit",
        }:
            return
        if "[s/n]" in pergunta.casefold():
            return

        interpretacao = interpretar_pergunta(pergunta)
        campo = interpretacao[0] if interpretacao else None
        pergunta_normalizada = " ".join(pergunta.casefold().split())
        if re.match(
            r"^(?:pode\s+dar\s+um\s+exemplo|dê\s+um\s+exemplo|"
            r"de\s+um\s+exemplo)\b",
            pergunta_normalizada,
        ):
            campo = "exemplo_uso"

        if campo not in {"significado", "tipo"}:
            log.passo(
                self.componente_log,
                "registrar_resposta_cascata",
                "campo não alimenta a cascata",
                {"campo": campo},
            )
            return

        self.registrar_conteudo_confirmado(resposta)

    def registrar_conteudo_confirmado(self, texto: str) -> None:
        """Enfileira termos novos de conteúdo aceito por uma fonte."""
        from ..fluxo import termos_desconhecidos_no_texto

        texto_limpo = re.sub(
            r"^\s*(?:resposta|answer)\s*:\s*",
            "",
            texto.strip(),
            flags=re.IGNORECASE,
        )
        texto_limpo = re.split(r"[\r\n]+", texto_limpo, maxsplit=1)[0]
        if len(texto_limpo) > self.LIMITE_CARACTERES_RESPOSTA_CASCATA:
            log.passo(
                self.componente_log,
                "registrar_resposta_cascata",
                "resposta longa não alimenta a cascata",
                {
                    "limite_caracteres": self.LIMITE_CARACTERES_RESPOSTA_CASCATA,
                    "tamanho": len(texto_limpo),
                },
            )
            return

        candidatos = termos_desconhecidos_no_texto(
            texto_limpo,
            self.banco,
            ignorar=self.termos_em_cadeia,
        )[: self.LIMITE_CANDIDATOS_POR_RESPOSTA]
        self._enfileirar_candidatos(candidatos)

    def _enfileirar_candidatos(self, novos_termos: list[str]) -> None:
        profundidade = self._profundidade_atual + 1
        if profundidade > self.LIMITE_PROFUNDIDADE_CADEIA:
            log.passo(
                self.componente_log,
                "registrar_resposta_cascata",
                "profundidade máxima da cadeia atingida",
                {"limite": self.LIMITE_PROFUNDIDADE_CADEIA},
            )
            return

        for novo_termo in dict.fromkeys(novos_termos):
            if len(self.termos_em_cadeia) >= self.LIMITE_TERMOS_POR_CADEIA:
                log.falha(
                    self.componente_log,
                    "registrar_resposta_cascata",
                    "limite de termos da cadeia atingido",
                    {"limite": self.LIMITE_TERMOS_POR_CADEIA},
                )
                print(
                    "Limite de aprendizagem em cascata atingido nesta entrada."
                )
                break
            self.termos_em_cadeia.add(novo_termo)
            self.profundidade_por_termo[novo_termo] = profundidade
            print(
                "\nhen-isana encontrou um termo novo na resposta: "
                f"{novo_termo}"
            )
            self.termos_pendentes.append(novo_termo)

    def processar_pendentes(
        self,
        perguntar: Callable[[str], str],
        *,
        ao_falhar: Optional[Callable[[str, Exception], None]] = None,
    ) -> None:
        from ..fluxo import aprender_termo

        def perguntar_e_registrar(pergunta: str) -> str:
            resposta = perguntar(pergunta)
            self.registrar_resposta(pergunta, resposta)
            return resposta

        indice = 0
        while indice < len(self.termos_pendentes):
            novo_termo = self.termos_pendentes[indice]
            indice += 1
            print(f"\nAprendendo termo encontrado: {novo_termo}")
            profundidade_anterior = self._profundidade_atual
            self._profundidade_atual = self.profundidade_por_termo.get(
                novo_termo,
                1,
            )
            try:
                aprender_termo(
                    novo_termo,
                    self.banco,
                    perguntar=perguntar_e_registrar,
                    relacoes=self.relacoes,
                    origem_resposta=self.origem_resposta,
                    usar_internet=self.usar_internet,
                    permissao_memoria=self.permissao_memoria,
                    permissao_relacao=self.permissao_relacao,
                    ao_aceitar_sugestao=self.registrar_conteudo_confirmado,
                )
            except Exception as erro:
                log.falha(
                    self.componente_log,
                    "processar_termos_pendentes",
                    str(erro),
                    {"termo": novo_termo},
                )
                print(
                    f"Falha ao aprender o termo novo '{novo_termo}': {erro}"
                )
                if ao_falhar is not None:
                    ao_falhar(novo_termo, erro)
            finally:
                self._profundidade_atual = profundidade_anterior
        self.termos_pendentes.clear()