"""Gerador canônico de propostas JSON da Fase 3.7.

O gerador transforma uma descrição estruturada em JSON compatível com
``ContratoCadastro``. Ele não conhece SQLite, não abre banco, não aplica
propostas e não chama fontes externas. A validação estrutural real continua
sendo feita por ``contrato_de_dict``; a validação completa da ingestão pode ser
injetada por ``IngestaoJSON`` quando o chamador quiser consultar duplicidades e
conflitos existentes.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Literal, TYPE_CHECKING

from aplicacao.contrato_entrada import contrato_de_dict

if TYPE_CHECKING:
    from bancos.ingestao_json import IngestaoJSON, RelatorioIngestao


StatusGeracao = Literal["aceito", "pendente", "conflito", "rejeitado"]

_RAIZ = {
    "proposta_id",
    "entrada",
    "idempotencia",
    "objetos",
    "evidencias",
    "pendencias",
    "incertezas",
    "estado",
    "ambiguidades",
}
_OBJETO = {
    "objeto_id",
    "tipo",
    "chave",
    "campos",
    "relacoes",
    "pendencias",
    "incertezas",
    "ambiguidades",
}
_CAMPO = {
    "nome",
    "valor",
    "origem",
    "estado",
    "confianca",
    "evidencia_ids",
}
_EVIDENCIA = {
    "evidencia_id",
    "fonte_tipo",
    "fonte_identificador",
    "origem",
    "trecho",
    "referencia",
    "confianca",
    "estado",
    "revisao_necessaria",
}
_RELACAO = {
    "tipo",
    "origem_objeto_id",
    "destino_tipo",
    "destino_chave",
    "ordem",
    "estado",
    "confianca",
    "evidencia_ids",
}
_NOME_ARQUIVO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")
_NOME_FISICO = re.compile(
    r"(?:sql|python|exec|comando|tabela|coluna|cursor|conex[aã]o)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ResultadoGeracaoJSON:
    """Relatório da geração sem conexão, cursor ou efeito de aplicação."""

    status: StatusGeracao
    json_texto: str = ""
    motivos: tuple[str, ...] = ()
    caminho: Path | None = None
    duplicidades: tuple[str, ...] = ()

    @property
    def aceito(self) -> bool:
        return self.status == "aceito"


def _objeto(valor: Any, nome: str) -> Mapping[str, Any]:
    if not isinstance(valor, Mapping):
        raise TypeError(f"{nome} deve ser um objeto estruturado")
    if any(not isinstance(chave, str) for chave in valor):
        raise TypeError(f"{nome} contém chave que não é texto")
    return valor


def _chaves(valor: Mapping[str, Any], permitidas: set[str], nome: str) -> None:
    desconhecidas = set(valor) - permitidas
    if desconhecidas:
        nomes = ", ".join(sorted(desconhecidas))
        raise ValueError(f"{nome} contém campos não suportados: {nomes}")


def _lista(valor: Any, nome: str) -> list[Any]:
    if not isinstance(valor, Sequence) or isinstance(valor, (str, bytes)):
        raise TypeError(f"{nome} deve ser uma lista")
    return list(valor)


def _textos(valor: Any, nome: str) -> list[str]:
    itens = _lista(valor, nome)
    if any(not isinstance(item, str) or not item.strip() for item in itens):
        raise TypeError(f"{nome} deve conter somente textos não vazios")
    return sorted(itens)


def _ids(valor: Any, nome: str) -> list[str]:
    return _textos(valor, nome)


def _campos(valor: Any, tipo: str) -> list[dict[str, Any]]:
    if isinstance(valor, Mapping):
        itens: list[Mapping[str, Any]] = []
        for nome, especificacao in valor.items():
            if not isinstance(nome, str):
                raise TypeError("nome de campo deve ser texto")
            item = dict(_objeto(especificacao, f"campo {nome}"))
            item["nome"] = nome
            itens.append(item)
    else:
        itens = [_objeto(item, "campo") for item in _lista(valor, "campos")]

    resultado: list[dict[str, Any]] = []
    nomes: set[str] = set()
    for item in itens:
        item = dict(item)
        _chaves(item, _CAMPO, f"campo de {tipo}")
        nome = item.get("nome")
        if not isinstance(nome, str) or not nome.strip():
            raise ValueError(f"campo de {tipo} precisa de nome")
        if _NOME_FISICO.search(nome):
            raise ValueError(f"campo {nome} contém referência física")
        if nome in nomes:
            raise ValueError(f"campo repetido para {tipo}: {nome}")
        if "valor" not in item or "origem" not in item:
            raise ValueError(f"campo {nome} precisa de valor e origem")
        if "evidencia_ids" in item:
            item["evidencia_ids"] = _ids(
                item["evidencia_ids"],
                f"campo {nome}.evidencia_ids",
            )
        nomes.add(nome)
        resultado.append(item)
    return sorted(resultado, key=lambda item: item["nome"])


def _relacoes(valor: Any) -> list[dict[str, Any]]:
    resultado: list[dict[str, Any]] = []
    for valor_relacao in _lista(valor, "relacoes"):
        item = dict(_objeto(valor_relacao, "relacao"))
        _chaves(item, _RELACAO, "relacao")
        if "evidencia_ids" in item:
            item["evidencia_ids"] = _ids(
                item["evidencia_ids"],
                "relacao.evidencia_ids",
            )
        resultado.append(item)
    return sorted(
        resultado,
        key=lambda item: (
            str(item.get("tipo", "")),
            str(item.get("origem_objeto_id", "")),
            str(item.get("destino_tipo", "")),
            str(item.get("destino_chave", "")),
            json.dumps(item, ensure_ascii=False, sort_keys=True),
        ),
    )


def _objetos(valor: Any) -> list[dict[str, Any]]:
    resultado: list[dict[str, Any]] = []
    for valor_objeto in _lista(valor, "objetos"):
        item = dict(_objeto(valor_objeto, "objeto"))
        _chaves(item, _OBJETO, "objeto")
        for obrigatorio in ("objeto_id", "tipo", "chave"):
            if obrigatorio not in item:
                raise ValueError(f"objeto não contém {obrigatorio}")
        if "campos" in item:
            item["campos"] = _campos(item["campos"], str(item["tipo"]))
        if "relacoes" in item:
            item["relacoes"] = _relacoes(item["relacoes"])
        for nome in ("pendencias", "incertezas", "ambiguidades"):
            if nome in item:
                item[nome] = _textos(item[nome], f"objeto.{nome}")
        resultado.append(item)
    return sorted(
        resultado,
        key=lambda item: (
            str(item["objeto_id"]),
            str(item["tipo"]),
            str(item["chave"]),
        ),
    )


def _evidencias(valor: Any) -> list[dict[str, Any]]:
    resultado: list[dict[str, Any]] = []
    ids: set[str] = set()
    for valor_evidencia in _lista(valor, "evidencias"):
        item = dict(_objeto(valor_evidencia, "evidencia"))
        _chaves(item, _EVIDENCIA, "evidencia")
        evidencia_id = item.get("evidencia_id")
        if not isinstance(evidencia_id, str) or not evidencia_id.strip():
            raise ValueError("evidencia precisa de evidencia_id")
        if evidencia_id in ids:
            raise ValueError(f"evidencia repetida: {evidencia_id}")
        ids.add(evidencia_id)
        for obrigatorio in (
            "fonte_tipo",
            "fonte_identificador",
            "origem",
            "trecho",
        ):
            if obrigatorio not in item:
                raise ValueError(f"evidencia não contém {obrigatorio}")
        resultado.append(item)
    return sorted(resultado, key=lambda item: str(item["evidencia_id"]))


def _normalizar(descricao: Mapping[str, Any]) -> dict[str, Any]:
    descricao = _objeto(descricao, "descricao")
    _chaves(descricao, _RAIZ, "descricao")
    for obrigatorio in ("proposta_id", "entrada", "idempotencia"):
        if obrigatorio not in descricao:
            raise ValueError(f"descricao não contém {obrigatorio}")

    resultado: dict[str, Any] = {
        nome: descricao[nome]
        for nome in ("proposta_id", "entrada", "idempotencia")
    }
    if "objetos" in descricao:
        resultado["objetos"] = _objetos(descricao["objetos"])
    if "evidencias" in descricao:
        resultado["evidencias"] = _evidencias(descricao["evidencias"])
    for nome in ("pendencias", "incertezas", "ambiguidades"):
        if nome in descricao:
            resultado[nome] = _textos(descricao[nome], nome)
    if "estado" in descricao:
        resultado["estado"] = descricao["estado"]

    # Esta é a fronteira real do contrato. Ela rejeita JSON malformado para o
    # ContratoCadastro, conteúdo executável, SQL e referências físicas.
    contrato_de_dict(resultado)
    return resultado


def _status_estrutural(contrato: Any) -> tuple[StatusGeracao, tuple[str, ...]]:
    motivos = list(contrato.pendencias)
    motivos.extend(contrato.ambiguidades)
    for objeto in contrato.objetos:
        motivos.extend(objeto.pendencias)
        motivos.extend(objeto.ambiguidades)
    if contrato.ambiguidades or any(
        objeto.ambiguidades for objeto in contrato.objetos
    ):
        return "pendente", tuple(dict.fromkeys(motivos))
    if motivos:
        return "pendente", tuple(dict.fromkeys(motivos))
    if contrato.incertezas or any(
        objeto.incertezas for objeto in contrato.objetos
    ):
        return "aceito", ("incertezas preservadas para revisão",)
    return "aceito", ()


class GeradorJSONConhecimento:
    """Gera JSON canônico sem aplicar propostas."""

    def gerar(self, descricao: Mapping[str, Any]) -> ResultadoGeracaoJSON:
        try:
            payload = _normalizar(descricao)
            contrato = contrato_de_dict(payload)
            texto = json.dumps(
                payload,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        except (TypeError, ValueError, OverflowError, json.JSONDecodeError) as erro:
            return ResultadoGeracaoJSON(
                status="rejeitado",
                motivos=(str(erro),),
            )
        status, motivos = _status_estrutural(contrato)
        return ResultadoGeracaoJSON(
            status=status,
            json_texto=texto,
            motivos=motivos,
        )

    def gerar_json(self, descricao: Mapping[str, Any]) -> str:
        """Gera texto canônico ou rejeita a descrição sem escrever nada."""
        resultado = self.gerar(descricao)
        if resultado.status == "rejeitado":
            motivo = "; ".join(resultado.motivos) or "descrição rejeitada"
            raise ValueError(motivo)
        return resultado.json_texto

    def gerar_arquivo(
        self,
        descricao: Mapping[str, Any],
        caminho: Path | str,
    ) -> ResultadoGeracaoJSON:
        """Escreve somente o arquivo JSON indicado, sem aplicar seu conteúdo."""
        resultado = self.gerar(descricao)
        if resultado.status == "rejeitado":
            return resultado
        destino = Path(caminho)
        if destino.suffix.lower() != ".json":
            return ResultadoGeracaoJSON(
                status="rejeitado",
                motivos=("o arquivo de saída precisa ter extensão .json",),
            )
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_text(resultado.json_texto + "\n", encoding="utf-8")
        return ResultadoGeracaoJSON(
            status=resultado.status,
            json_texto=resultado.json_texto,
            motivos=resultado.motivos,
            caminho=destino,
        )

    def gerar_lote(
        self,
        descricoes: Mapping[str, Mapping[str, Any]],
        diretorio: Path | str,
    ) -> tuple[ResultadoGeracaoJSON, ...]:
        """Gera arquivos por lote; nunca chama ingestão ou aplicação."""
        if not isinstance(descricoes, Mapping):
            raise TypeError("descricoes deve mapear nomes de arquivo para descrições")
        destino = Path(diretorio)
        resultados: list[ResultadoGeracaoJSON] = []
        for nome in sorted(descricoes):
            if (
                not isinstance(nome, str)
                or not _NOME_ARQUIVO.fullmatch(nome)
                or Path(nome).name != nome
                or nome in {".", ".."}
            ):
                resultados.append(
                    ResultadoGeracaoJSON(
                        status="rejeitado",
                        motivos=(f"nome de arquivo inseguro: {nome!r}",),
                    )
                )
                continue
            arquivo = nome if nome.lower().endswith(".json") else f"{nome}.json"
            resultados.append(
                self.gerar_arquivo(descricoes[nome], destino / arquivo)
            )
        return tuple(resultados)

    def validar_no_fluxo_real(
        self,
        descricao: Mapping[str, Any],
        ingestao: "IngestaoJSON",
    ) -> ResultadoGeracaoJSON:
        """Classifica o JSON usando ``IngestaoJSON.dry_run`` injetado."""
        resultado = self.gerar(descricao)
        if resultado.status == "rejeitado":
            return resultado
        try:
            relatorio: RelatorioIngestao = ingestao.dry_run(resultado.json_texto)
        except (TypeError, ValueError, LookupError) as erro:
            return ResultadoGeracaoJSON(
                status="rejeitado",
                json_texto=resultado.json_texto,
                motivos=(str(erro),),
            )

        validacao = relatorio.validacao
        motivos = list(resultado.motivos)
        motivos.extend(validacao.erros)
        motivos.extend(validacao.pendencias)
        motivos.extend(validacao.conflitos)
        if validacao.erros:
            status: StatusGeracao = "rejeitado"
        elif validacao.conflitos or relatorio.duplicidades:
            status = "conflito"
            motivos.extend(
                f"duplicidade existente: {item}"
                for item in relatorio.duplicidades
            )
        elif validacao.pendencias:
            status = "pendente"
        else:
            status = "aceito"
        return ResultadoGeracaoJSON(
            status=status,
            json_texto=resultado.json_texto,
            motivos=tuple(dict.fromkeys(motivos)),
            duplicidades=relatorio.duplicidades,
        )


def gerar_json_conhecimento(descricao: Mapping[str, Any]) -> str:
    """Atalho funcional para gerar um único JSON canônico."""
    return GeradorJSONConhecimento().gerar_json(descricao)


__all__ = [
    "GeradorJSONConhecimento",
    "ResultadoGeracaoJSON",
    "gerar_json_conhecimento",
]