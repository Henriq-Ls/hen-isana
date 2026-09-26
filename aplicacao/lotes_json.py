"""Preparação segura e determinística de lotes JSON da Fase 3.7.

Este módulo organiza propostas já estruturadas no contrato real. Ele não cria
conhecimento a partir de bancos, código, snapshots ou configuração, não aplica
propostas e não abre SQLite por conta própria. Quando a validação contra o
estado existente for necessária, ``IngestaoJSON`` é injetado e somente o
``dry_run`` é chamado.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import tempfile
from typing import Any, TYPE_CHECKING

from aplicacao.gerador_json import (
    GeradorJSONConhecimento,
    ResultadoGeracaoJSON,
)

if TYPE_CHECKING:
    from bancos.ingestao_json import IngestaoJSON


FORMATO_LOTE = "lote-json-conhecimento"
VERSAO_FORMATO_LOTE = "1"
_COMPONENTE = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_NOME_ARQUIVO = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]*$")


@dataclass(frozen=True)
class FonteProjeto:
    """Classificação declarativa de uma fonte local do projeto."""

    identificador: str
    caminho: str
    classificacao: str
    elegivel: bool
    motivo: str
    quantidade: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "identificador": self.identificador,
            "caminho": self.caminho,
            "classificacao": self.classificacao,
            "elegivel": self.elegivel,
            "motivo": self.motivo,
            "quantidade": self.quantidade,
        }


@dataclass(frozen=True)
class EntradaLote:
    """Metadados canônicos de uma proposta dentro do lote."""

    arquivo: str
    proposta_id: str
    idempotencia: str
    status: str
    json_texto: str
    motivos: tuple[str, ...] = ()
    sha256: str = ""
    objetos: int = 0
    relacoes: int = 0
    evidencias: int = 0
    pendencias: int = 0
    incertezas: int = 0
    ambiguidades: int = 0
    conflitos: int = 0
    duplicidades: tuple[str, ...] = ()

    @property
    def caminho_relativo(self) -> str:
        return f"propostas/{self.arquivo}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "arquivo": self.caminho_relativo,
            "proposta_id": self.proposta_id,
            "idempotencia": self.idempotencia,
            "status": self.status,
            "sha256": self.sha256,
            "objetos": self.objetos,
            "relacoes": self.relacoes,
            "evidencias": self.evidencias,
            "pendencias": self.pendencias,
            "incertezas": self.incertezas,
            "ambiguidades": self.ambiguidades,
            "conflitos": self.conflitos,
            "duplicidades": list(self.duplicidades),
            "motivos": list(self.motivos),
        }


@dataclass(frozen=True)
class LotePreparado:
    """Lote pronto para gravação, mas ainda não aplicado a nenhum banco."""

    fonte: str
    assunto: str
    lote_id: str
    versao: str
    entradas: tuple[EntradaLote, ...]

    @property
    def totais(self) -> dict[str, int]:
        return _totais(self.entradas)

    def manifesto_dict(self) -> dict[str, Any]:
        return {
            "formato": FORMATO_LOTE,
            "formato_versao": VERSAO_FORMATO_LOTE,
            "contrato": "ContratoCadastro",
            "lote": {
                "id": self.lote_id,
                "versao": self.versao,
                "fonte": self.fonte,
                "assunto": self.assunto,
            },
            "arquivos": [entrada.to_dict() for entrada in self.entradas],
            "totais": self.totais,
        }

    def manifesto_json(self) -> str:
        return _json_canonico(self.manifesto_dict())


@dataclass(frozen=True)
class RelatorioLote:
    """Resultado de uma validação estrutural ou por ``dry_run``."""

    fonte: str
    assunto: str
    lote_id: str
    versao: str
    caminho: Path | None
    entradas: tuple[EntradaLote, ...]
    manifesto_integro: bool
    motivos: tuple[str, ...] = ()

    @property
    def totais(self) -> dict[str, int]:
        return _totais(self.entradas)

    @property
    def valido(self) -> bool:
        return self.manifesto_integro and not any(
            entrada.status == "rejeitado" for entrada in self.entradas
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fonte": self.fonte,
            "assunto": self.assunto,
            "lote_id": self.lote_id,
            "versao": self.versao,
            "caminho": str(self.caminho) if self.caminho else None,
            "manifesto_integro": self.manifesto_integro,
            "valido": self.valido,
            "arquivos": [entrada.to_dict() for entrada in self.entradas],
            "totais": self.totais,
            "motivos": list(self.motivos),
        }


def _json_canonico(valor: Any) -> str:
    return json.dumps(
        valor,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _sha256(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _componente(valor: str, nome: str) -> str:
    if not isinstance(valor, str) or not valor or not _COMPONENTE.fullmatch(valor):
        raise ValueError(
            f"{nome} deve conter somente letras minúsculas, números, ponto, "
            "hífen ou sublinhado"
        )
    return valor


def _nome_arquivo(valor: Any) -> str:
    if not isinstance(valor, str) or not _NOME_ARQUIVO.fullmatch(valor):
        raise ValueError(f"nome de arquivo inseguro: {valor!r}")
    if Path(valor).name != valor or valor in {".", ".."}:
        raise ValueError(f"nome de arquivo inseguro: {valor!r}")
    return valor if valor.lower().endswith(".json") else f"{valor}.json"


def _texto_lista(valor: Any) -> int:
    return len(valor) if isinstance(valor, list) else 0


def _contagens(payload: Mapping[str, Any]) -> dict[str, int]:
    objetos = payload.get("objetos", [])
    if not isinstance(objetos, list):
        objetos = []
    relacoes = 0
    pendencias = _texto_lista(payload.get("pendencias", []))
    incertezas = _texto_lista(payload.get("incertezas", []))
    ambiguidades = _texto_lista(payload.get("ambiguidades", []))
    for objeto in objetos:
        if not isinstance(objeto, Mapping):
            continue
        relacoes += _texto_lista(objeto.get("relacoes", []))
        pendencias += _texto_lista(objeto.get("pendencias", []))
        incertezas += _texto_lista(objeto.get("incertezas", []))
        ambiguidades += _texto_lista(objeto.get("ambiguidades", []))
    return {
        "objetos": len(objetos),
        "relacoes": relacoes,
        "evidencias": _texto_lista(payload.get("evidencias", [])),
        "pendencias": pendencias,
        "incertezas": incertezas,
        "ambiguidades": ambiguidades,
    }


def _totais(entradas: tuple[EntradaLote, ...]) -> dict[str, int]:
    return {
        "arquivos": len(entradas),
        "aceitos": sum(item.status == "aceito" for item in entradas),
        "pendentes": sum(item.status == "pendente" for item in entradas),
        "conflitos": sum(item.status == "conflito" for item in entradas),
        "rejeitados": sum(item.status == "rejeitado" for item in entradas),
        "objetos": sum(item.objetos for item in entradas),
        "relacoes": sum(item.relacoes for item in entradas),
        "evidencias": sum(item.evidencias for item in entradas),
        "pendencias": sum(item.pendencias for item in entradas),
        "incertezas": sum(item.incertezas for item in entradas),
        "ambiguidades": sum(item.ambiguidades for item in entradas),
        "conflitos_detalhados": sum(item.conflitos for item in entradas),
    }


def _entrada_resultado(
    arquivo: str,
    resultado: ResultadoGeracaoJSON,
) -> EntradaLote:
    json_texto = resultado.json_texto
    payload: Mapping[str, Any] = {}
    if json_texto:
        carregado = json.loads(json_texto)
        if isinstance(carregado, Mapping):
            payload = carregado
    contagens = _contagens(payload)
    proposta_id = str(payload.get("proposta_id", ""))
    idempotencia = str(payload.get("idempotencia", ""))
    duplicidades = tuple(resultado.duplicidades)
    conflitos = len(duplicidades)
    if resultado.status == "conflito" and conflitos == 0:
        conflitos = 1
    conteudo = f"{json_texto}\n" if json_texto else ""
    return EntradaLote(
        arquivo=arquivo,
        proposta_id=proposta_id,
        idempotencia=idempotencia,
        status=resultado.status,
        json_texto=json_texto,
        motivos=tuple(resultado.motivos),
        sha256=_sha256(conteudo) if conteudo else "",
        conflitos=conflitos,
        duplicidades=duplicidades,
        **contagens,
    )


def _totais_manifesto(manifesto: Mapping[str, Any]) -> dict[str, int]:
    totais = manifesto.get("totais")
    if not isinstance(totais, Mapping):
        raise ValueError("manifesto não contém totais")
    resultado: dict[str, int] = {}
    for chave, valor in totais.items():
        if not isinstance(chave, str) or not isinstance(valor, int):
            raise ValueError("totais do manifesto precisam ser inteiros")
        resultado[chave] = valor
    return resultado


def _arquivos_manifesto(manifesto: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    arquivos = manifesto.get("arquivos")
    if not isinstance(arquivos, list):
        raise ValueError("manifesto não contém arquivos")
    resultado: list[Mapping[str, Any]] = []
    for item in arquivos:
        if not isinstance(item, Mapping):
            raise ValueError("entrada do manifesto precisa ser objeto")
        caminho = item.get("arquivo")
        if (
            not isinstance(caminho, str)
            or not caminho.startswith("propostas/")
            or Path(caminho).name != caminho.removeprefix("propostas/")
        ):
            raise ValueError("manifesto contém caminho de arquivo inseguro")
        resultado.append(item)
    return resultado


class LotesJSONConhecimento:
    """Prepara e grava lotes sem aplicar nenhum pacote."""

    def __init__(self, raiz: Path | str = "lotes_json") -> None:
        self.raiz = Path(raiz)
        self.gerador = GeradorJSONConhecimento()

    def preparar(
        self,
        descricoes: Mapping[str, Mapping[str, Any]],
        *,
        fonte: str,
        assunto: str,
        lote_id: str,
        versao: str = "v1",
        ingestao: "IngestaoJSON | None" = None,
    ) -> LotePreparado:
        """Normaliza um mapa de propostas sem escrever arquivos."""
        if not isinstance(descricoes, Mapping):
            raise TypeError("descricoes deve mapear nomes de arquivo para propostas")
        fonte = _componente(fonte, "fonte")
        assunto = _componente(assunto, "assunto")
        lote_id = _componente(lote_id, "lote_id")
        versao = _componente(versao, "versao")

        entradas: list[EntradaLote] = []
        nomes_vistos: set[str] = set()
        itens = sorted(descricoes.items(), key=lambda item: repr(item[0]))
        for nome_original, descricao in itens:
            try:
                arquivo = _nome_arquivo(nome_original)
                chave_colisao = arquivo.casefold()
                if chave_colisao in nomes_vistos:
                    raise ValueError(
                        f"nome de arquivo colide com outra proposta: {arquivo}"
                    )
                nomes_vistos.add(chave_colisao)
            except (TypeError, ValueError) as erro:
                resultado = ResultadoGeracaoJSON(
                    status="rejeitado",
                    motivos=(str(erro),),
                )
                entradas.append(
                    _entrada_resultado(str(nome_original), resultado)
                )
                continue

            resultado = (
                self.gerador.validar_no_fluxo_real(descricao, ingestao)
                if ingestao is not None
                else self.gerador.gerar(descricao)
            )
            entradas.append(_entrada_resultado(arquivo, resultado))

        return LotePreparado(
            fonte=fonte,
            assunto=assunto,
            lote_id=lote_id,
            versao=versao,
            entradas=tuple(sorted(entradas, key=lambda item: item.arquivo)),
        )

    def caminho_lote(self, lote: LotePreparado) -> Path:
        return (
            self.raiz
            / lote.fonte
            / lote.assunto
            / lote.lote_id
            / lote.versao
        )

    def gravar(self, lote: LotePreparado) -> Path:
        """Grava um lote inteiro, sem sobrescrever conteúdo diferente."""
        rejeitados = [
            entrada.arquivo
            for entrada in lote.entradas
            if entrada.status == "rejeitado"
        ]
        if rejeitados:
            raise ValueError(
                "lote contém propostas rejeitadas: " + ", ".join(rejeitados)
            )

        destino = self.caminho_lote(lote)
        esperado: dict[str, bytes] = {
            entrada.caminho_relativo: (
                entrada.json_texto + "\n"
            ).encode("utf-8")
            for entrada in lote.entradas
        }
        esperado["manifesto.json"] = (
            lote.manifesto_json() + "\n"
        ).encode("utf-8")

        if destino.exists():
            if not destino.is_dir():
                raise FileExistsError(f"caminho do lote não é diretório: {destino}")
            existentes = {
                caminho.relative_to(destino).as_posix(): caminho.read_bytes()
                for caminho in destino.rglob("*")
                if caminho.is_file()
            }
            if existentes == esperado:
                return destino
            raise FileExistsError(
                "lote existente possui conteúdo diferente; "
                "a versão deve ser incrementada"
            )

        destino.parent.mkdir(parents=True, exist_ok=True)
        temporario = Path(
            tempfile.mkdtemp(
                prefix=f".{lote.lote_id}-{lote.versao}-",
                dir=str(destino.parent),
            )
        )
        try:
            propostas = temporario / "propostas"
            propostas.mkdir()
            for entrada in lote.entradas:
                (propostas / entrada.arquivo).write_bytes(
                    esperado[entrada.caminho_relativo]
                )
            (temporario / "manifesto.json").write_bytes(
                esperado["manifesto.json"]
            )
            try:
                os.rename(temporario, destino)
            except FileExistsError as erro:
                raise FileExistsError(
                    "outro lote foi criado no mesmo caminho durante a geração"
                ) from erro
        finally:
            if temporario.exists():
                shutil.rmtree(temporario)
        return destino

    def gerar_e_gravar(
        self,
        descricoes: Mapping[str, Mapping[str, Any]],
        *,
        fonte: str,
        assunto: str,
        lote_id: str,
        versao: str = "v1",
        ingestao: "IngestaoJSON | None" = None,
    ) -> tuple[LotePreparado, Path]:
        lote = self.preparar(
            descricoes,
            fonte=fonte,
            assunto=assunto,
            lote_id=lote_id,
            versao=versao,
            ingestao=ingestao,
        )
        return lote, self.gravar(lote)

    def validar_lote(
        self,
        caminho: Path | str,
        ingestao: "IngestaoJSON",
    ) -> RelatorioLote:
        """Valida arquivos existentes com ``IngestaoJSON.dry_run``."""
        if ingestao is None:
            raise TypeError("ingestao é obrigatória para validar um lote")
        diretorio = Path(caminho)
        manifesto_path = diretorio / "manifesto.json"
        if not diretorio.is_dir() or not manifesto_path.is_file():
            raise ValueError("diretório de lote ou manifesto inexistente")
        try:
            manifesto = json.loads(manifesto_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as erro:
            raise ValueError("manifesto JSON inválido") from erro
        if not isinstance(manifesto, Mapping):
            raise ValueError("manifesto precisa ser um objeto")
        if manifesto.get("formato") != FORMATO_LOTE:
            raise ValueError("formato de lote desconhecido")
        if manifesto.get("formato_versao") != VERSAO_FORMATO_LOTE:
            raise ValueError("versão de formato de lote desconhecida")
        if manifesto.get("contrato") != "ContratoCadastro":
            raise ValueError("contrato de lote desconhecido")
        lote = manifesto.get("lote")
        if not isinstance(lote, Mapping):
            raise ValueError("manifesto não contém identificação do lote")
        fonte = _componente(lote.get("fonte"), "fonte")
        assunto = _componente(lote.get("assunto"), "assunto")
        lote_id = _componente(lote.get("id"), "lote_id")
        versao = _componente(lote.get("versao"), "versao")
        declarados = _arquivos_manifesto(manifesto)
        entradas: list[EntradaLote] = []
        motivos_manifesto: list[str] = []
        caminhos_declarados = [str(item["arquivo"]) for item in declarados]
        if len(set(caminhos_declarados)) != len(caminhos_declarados):
            motivos_manifesto.append("manifesto contém arquivo declarado mais de uma vez")
        arquivos_existentes = {
            caminho.relative_to(diretorio).as_posix()
            for caminho in diretorio.rglob("*")
            if caminho.is_file() and caminho != manifesto_path
        }
        arquivos_nao_declarados = sorted(
            arquivos_existentes - set(caminhos_declarados)
        )
        motivos_manifesto.extend(
            f"arquivo não declarado: {caminho}"
            for caminho in arquivos_nao_declarados
        )
        for declarado in declarados:
            relativo = declarado["arquivo"]
            arquivo = Path(relativo).name
            caminho_arquivo = diretorio / relativo
            if not caminho_arquivo.is_file():
                motivos_manifesto.append(f"arquivo ausente: {relativo}")
                continue
            texto = caminho_arquivo.read_text(encoding="utf-8")
            esperado_hash = declarado.get("sha256")
            if esperado_hash != _sha256(texto):
                motivos_manifesto.append(f"hash divergente: {relativo}")
            try:
                resultado_ingestao = ingestao.dry_run(texto)
                validacao = resultado_ingestao.validacao
                motivos = list(validacao.erros)
                motivos.extend(validacao.pendencias)
                motivos.extend(validacao.conflitos)
                if validacao.erros:
                    status = "rejeitado"
                elif validacao.conflitos or resultado_ingestao.duplicidades:
                    status = "conflito"
                    motivos.extend(
                        f"duplicidade existente: {item}"
                        for item in resultado_ingestao.duplicidades
                    )
                elif validacao.pendencias:
                    status = "pendente"
                else:
                    status = "aceito"
                resultado = ResultadoGeracaoJSON(
                    status=status,
                    json_texto=texto.rstrip("\n"),
                    motivos=tuple(dict.fromkeys(motivos)),
                    duplicidades=resultado_ingestao.duplicidades,
                )
            except (TypeError, ValueError, LookupError) as erro:
                resultado = ResultadoGeracaoJSON(
                    status="rejeitado",
                    json_texto=texto.rstrip("\n"),
                    motivos=(str(erro),),
                )
            entradas.append(_entrada_resultado(arquivo, resultado))

        totais_declarados = _totais_manifesto(manifesto)
        totais_calculados = _totais(tuple(sorted(entradas, key=lambda item: item.arquivo)))
        if totais_declarados != totais_calculados:
            motivos_manifesto.append("totais do manifesto não correspondem aos arquivos")
        manifesto_integro = not motivos_manifesto
        return RelatorioLote(
            fonte=fonte,
            assunto=assunto,
            lote_id=lote_id,
            versao=versao,
            caminho=diretorio,
            entradas=tuple(sorted(entradas, key=lambda item: item.arquivo)),
            manifesto_integro=manifesto_integro,
            motivos=tuple(dict.fromkeys(motivos_manifesto)),
        )


def carregar_descricoes_json(diretorio: Path | str) -> dict[str, dict[str, Any]]:
    """Carrega apenas JSONs diretos de um diretório, sem executar conteúdo."""
    caminho = Path(diretorio)
    if not caminho.is_dir():
        raise ValueError(f"diretório de fonte inexistente: {caminho}")
    resultado: dict[str, dict[str, Any]] = {}
    for arquivo in sorted(caminho.iterdir(), key=lambda item: item.name):
        if not arquivo.is_file() or arquivo.suffix.lower() != ".json":
            continue
        try:
            valor = json.loads(arquivo.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as erro:
            raise ValueError(f"JSON inválido na fonte: {arquivo.name}") from erro
        if not isinstance(valor, Mapping):
            raise ValueError(f"JSON da fonte precisa ser objeto: {arquivo.name}")
        resultado[arquivo.name] = dict(valor)
    return resultado


def inventariar_fontes(projeto: Path | str | None = None) -> tuple[FonteProjeto, ...]:
    """Declara quais fontes locais podem ou não alimentar lotes.

    A função inspeciona somente a existência e a quantidade de arquivos
    documentais; não lê bancos e não converte nenhuma fonte automaticamente.
    """
    raiz = (
        Path(projeto)
        if projeto is not None
        else Path(__file__).resolve().parents[1]
    )

    def quantidade(caminho: Path, extensao: str | None = None) -> int:
        if caminho.is_dir():
            itens = caminho.iterdir()
            return sum(
                item.is_file()
                and (extensao is None or item.suffix.lower() == extensao)
                for item in itens
            )
        return int(caminho.is_file())

    fontes = (
        (
            "documentacao-json-conhecimento",
            "docs/exemplos_json_conhecimento",
            "pacotes_json_documentais",
            True,
            "pacotes já estruturados no ContratoCadastro; elegíveis apenas "
            "para reempacotamento como propostas não aplicadas",
            ".json",
        ),
        (
            "documentacao-json-fase-1-3",
            "docs/exemplos_fase_1_3_json",
            "fixtures_de_validacao",
            False,
            "exemplos incluem casos deliberadamente inválidos; são somente "
            "fixtures de teste",
            ".json",
        ),
        (
            "configuracao-linguagem",
            "data/linguagem.json",
            "configuracao",
            False,
            "regras funcionais e abreviações do runtime, não propostas de "
            "conhecimento",
            None,
        ),
        (
            "conhecimento-legado",
            "aprendizado/bancos/conhecimento.db",
            "sqlite_legado",
            False,
            "memória legada; migração não autorizada nesta etapa",
            None,
        ),
        (
            "relacoes-legadas",
            "aprendizado/bancos/relacoes.db",
            "sqlite_legado",
            False,
            "relações legadas; migração não autorizada nesta etapa",
            None,
        ),
        (
            "linguagem-canonica",
            "aprendizado/bancos/linguagem.db",
            "sqlite_destino",
            False,
            "banco canônico de destino; não é fonte de geração",
            None,
        ),
        (
            "snapshots-de-codigo",
            "backup/snapshots",
            "codigo_historico",
            False,
            "snapshots são código histórico e não dados de conhecimento",
            ".snapshot",
        ),
    )
    return tuple(
        FonteProjeto(
            identificador=identificador,
            caminho=caminho,
            classificacao=classificacao,
            elegivel=elegivel,
            motivo=motivo,
            quantidade=quantidade(raiz / caminho, extensao),
        )
        for (
            identificador,
            caminho,
            classificacao,
            elegivel,
            motivo,
            extensao,
        ) in fontes
    )


__all__ = [
    "EntradaLote",
    "FonteProjeto",
    "LotePreparado",
    "LotesJSONConhecimento",
    "RelatorioLote",
    "carregar_descricoes_json",
    "inventariar_fontes",
]