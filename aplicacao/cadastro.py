"""Entradas estruturadas da Fase 3.2.

As funções deste módulo são adaptadores de fronteira. Elas convertem contrato
Python, dicionário ou JSON para o mesmo ``ContratoCadastro`` e encaminham tudo
para ``ConhecimentoAPI``. Não abrem SQLite, não executam conteúdo recebido e
não aceitam instruções de persistência física.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import json
from typing import Any

from aplicacao.contrato_entrada import (
    _rejeitar_conteudo_ativo,
    contrato_de_dict,
    contrato_de_json,
)
from bancos.api_conhecimento import (
    ConhecimentoAPI,
    PropostaConhecimento,
)
from core.contratos import ContratoCadastro


@dataclass(frozen=True)
class ResultadoCadastro:
    """Resultado comum para qualquer origem de pacote."""

    contrato: ContratoCadastro
    proposta: PropostaConhecimento


class CadastroPacotes:
    """Recebe pacotes e os encaminha ao único fluxo de conhecimento."""

    def __init__(self, api: ConhecimentoAPI):
        if not isinstance(api, ConhecimentoAPI):
            raise TypeError("api deve ser uma ConhecimentoAPI")
        self.api = api

    def receber_contrato(
        self,
        contrato: ContratoCadastro,
    ) -> ResultadoCadastro:
        """Recebe um objeto já construído sem criar um caminho paralelo."""
        proposta = self.api.registrar_proposta(contrato)
        return ResultadoCadastro(contrato=contrato, proposta=proposta)

    def receber_dict(
        self,
        pacote: Mapping[str, Any],
    ) -> ResultadoCadastro:
        """Converte um pacote estruturado para o contrato comum."""
        _rejeitar_conteudo_ativo(pacote)
        contrato = ContratoCadastro.from_dict(pacote)
        return self.receber_contrato(contrato)

    def receber_json(self, texto: str) -> ResultadoCadastro:
        """Lê JSON como dados; nunca avalia ou executa o conteúdo."""
        if not isinstance(texto, str) or not texto.strip():
            raise ValueError("o pacote JSON precisa ser texto não vazio")
        try:
            pacote = json.loads(texto)
        except json.JSONDecodeError as erro:
            raise ValueError("pacote JSON inválido") from erro
        if not isinstance(pacote, Mapping):
            raise TypeError("o pacote JSON precisa ser um objeto")
        return self.receber_dict(pacote)

    def receber_professor(
        self,
        pacote: ContratoCadastro | Mapping[str, Any],
    ) -> ResultadoCadastro:
        """Recebe candidato estruturado do professor sem chamar o professor real."""
        contrato = (
            pacote
            if isinstance(pacote, ContratoCadastro)
            else contrato_de_dict(pacote)
        )
        if contrato.entrada != "professor":
            raise ValueError("pacote do Professor precisa ter entrada 'professor'")
        return self.receber_contrato(contrato)

    def receber_llama(
        self,
        pacote: ContratoCadastro | Mapping[str, Any],
    ) -> ResultadoCadastro:
        """Recebe candidato do adaptador Llama sem exigir Ollama."""
        contrato = (
            pacote
            if isinstance(pacote, ContratoCadastro)
            else contrato_de_dict(pacote)
        )
        if contrato.entrada != "llama":
            raise ValueError("pacote do Llama precisa ter entrada 'llama'")
        return self.receber_contrato(contrato)

    def iniciar_revisao(
        self,
        proposta_id: str,
        revisor: str,
    ) -> PropostaConhecimento:
        return self.api.iniciar_revisao(proposta_id, revisor)

    def autorizar(
        self,
        proposta_id: str,
        autorizador: str,
    ) -> PropostaConhecimento:
        return self.api.autorizar(proposta_id, autorizador)

