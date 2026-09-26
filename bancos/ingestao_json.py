"""Ingestão controlada de pacotes JSON da Fase 3.3.

O módulo não aceita SQL, código ou nomes físicos no pacote. A aplicação
transacional só é chamada para uma proposta que passou por revisão e
autorização explícitas.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
import json
from typing import Any

from aplicacao.cadastro import contrato_de_dict, contrato_de_json
from bancos.api_conhecimento import (
    ConhecimentoAPI,
    PropostaConhecimento,
    ResultadoValidacao,
)
from bancos.persistencia_conhecimento import ResultadoAplicacao
from core.contratos import ContratoCadastro


@dataclass(frozen=True)
class RelatorioIngestao:
    """Resultado de validação ou aplicação, sem cursor ou conexão exposta."""

    contrato: ContratoCadastro
    validacao: ResultadoValidacao
    duplicidades: tuple[str, ...] = ()
    dry_run: bool = True
    aplicado: bool = False
    auditoria: ResultadoAplicacao | None = None


class IngestaoJSON:
    """Coordena leitura, validação, revisão e aplicação de um pacote."""

    def __init__(self, api: ConhecimentoAPI):
        if not isinstance(api, ConhecimentoAPI):
            raise TypeError("api deve ser uma ConhecimentoAPI")
        self.api = api

    def ler(
        self,
        entrada: ContratoCadastro | Mapping[str, Any] | str,
    ) -> ContratoCadastro:
        if isinstance(entrada, ContratoCadastro):
            return entrada
        if isinstance(entrada, Mapping):
            return contrato_de_dict(entrada)
        if isinstance(entrada, str):
            return contrato_de_json(entrada)
        raise TypeError("a entrada precisa ser contrato, dicionário ou JSON")

    def validar(
        self,
        entrada: ContratoCadastro | Mapping[str, Any] | str,
    ) -> RelatorioIngestao:
        contrato = self.ler(entrada)
        validacao = self.api.validar(contrato)
        validacao = self._validar_referencias(contrato, validacao)
        return RelatorioIngestao(
            contrato=contrato,
            validacao=validacao,
            duplicidades=self._duplicidades(contrato),
        )

    def dry_run(
        self,
        entrada: ContratoCadastro | Mapping[str, Any] | str,
    ) -> RelatorioIngestao:
        return self.validar(entrada)

    def registrar(
        self,
        entrada: ContratoCadastro | Mapping[str, Any] | str,
    ) -> PropostaConhecimento:
        relatorio = self.validar(entrada)
        if not relatorio.validacao.valido:
            detalhes = "; ".join(relatorio.validacao.erros)
            raise ValueError(f"pacote inválido: {detalhes}")
        return self.api.registrar_proposta(relatorio.contrato)

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

    def aplicar(self, proposta_id: str) -> RelatorioIngestao:
        proposta = self.api.obter_proposta(proposta_id)
        relatorio = self.validar(proposta.contrato)
        if proposta.estado != "autorizada":
            raise PermissionError(
                "a ingestão física exige uma proposta autorizada"
            )
        if not relatorio.validacao.pode_autorizar:
            raise ValueError(
                "a proposta autorizada deixou de cumprir a validação aplicável"
            )
        auditoria = self.api.aplicar_autorizada(proposta_id)
        return replace(
            relatorio,
            dry_run=False,
            aplicado=True,
            auditoria=auditoria,
        )

    @staticmethod
    def _validar_referencias(
        contrato: ContratoCadastro,
        resultado: ResultadoValidacao,
    ) -> ResultadoValidacao:
        pendencias = list(resultado.pendencias)
        erros = list(resultado.erros)
        objeto_ids = {objeto.objeto_id for objeto in contrato.objetos}

        for objeto in contrato.objetos:
            campos = {campo.nome: campo for campo in objeto.campos}
            if objeto.tipo in {"forma_lexical", "sentido"} and "lexema" not in campos:
                pendencias.append(
                    f"objeto {objeto.objeto_id} precisa referenciar um lexema"
                )
            if objeto.tipo == "analise_morfologica" and "forma_lexical" not in campos:
                pendencias.append(
                    f"objeto {objeto.objeto_id} precisa referenciar uma forma lexical"
                )
            if objeto.tipo in {"argumento", "fato"}:
                if objeto.tipo == "argumento" and "proposicao" not in campos:
                    pendencias.append(
                        f"objeto {objeto.objeto_id} precisa referenciar uma proposição"
                    )
                if objeto.tipo == "fato" and "proposicao" not in campos:
                    pendencias.append(
                        f"objeto {objeto.objeto_id} precisa referenciar uma proposição"
                    )
            for relacao in objeto.relacoes:
                if relacao.origem_objeto_id not in objeto_ids:
                    erros.append("relação embutida referencia origem inexistente")

        pendencias_unicas = tuple(dict.fromkeys(pendencias))
        erros_unicos = tuple(dict.fromkeys(erros))
        return replace(
            resultado,
            valido=not erros_unicos,
            pendencias=pendencias_unicas,
            erros=erros_unicos,
        )

    def _duplicidades(self, contrato: ContratoCadastro) -> tuple[str, ...]:
        tipos = {"lexema", "forma_lexical", "conceito", "expressao"}
        duplicidades: list[str] = []
        for objeto in contrato.objetos:
            if objeto.tipo in tipos and self.api.consultar(
                objeto.tipo, objeto.chave
            ):
                duplicidades.append(f"{objeto.tipo}:{objeto.chave}")
        return tuple(duplicidades)


def pacote_json(texto: str) -> ContratoCadastro:
    """Função de conveniência para leitura segura sem API ou banco."""
    if not isinstance(texto, str):
        raise TypeError("texto deve ser uma string JSON")
    try:
        json.loads(texto)
    except json.JSONDecodeError as erro:
        raise ValueError("JSON inválido") from erro
    return contrato_de_json(texto)