"""Consulta pública e limitada à internet.

Esta ferramenta lê apenas respostas textuais pequenas de hosts públicos.
Não permite localhost, redes privadas, portas customizadas, redirecionamentos
automáticos ou conteúdo binário.
"""

from dataclasses import dataclass
from html.parser import HTMLParser
import ipaddress
import json
import re
import socket
from typing import Any, Optional
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit, urlunsplit
from urllib.request import (
    HTTPRedirectHandler,
    Request,
    build_opener,
)

from _LOGS_ import log as runtime_log
from protocolo.regras import TipoAcao
from protocolo.verificador import verificar_acao


MAXIMO_BYTES = 64 * 1024
MAXIMO_CARACTERES_RESUMO = 2_000
TIMEOUT_SEGUNDOS = 8.0
MAXIMO_REDIRECIONAMENTOS = 2


class ConsultaInternetError(RuntimeError):
    """Falha controlada em uma consulta externa."""


@dataclass(frozen=True)
class ResultadoInternet:
    url: str
    status: int
    tipo_conteudo: str
    corpo: str


@dataclass(frozen=True)
class DefinicaoInternet:
    """Resumo externo usado apenas como sugestão de aprendizagem."""

    termo: str
    titulo: str
    resumo: str
    url: str


class _TextoHTML(HTMLParser):
    """Extrai texto visível sem dependências externas."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._ignorar = 0
        self._partes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._ignorar += 1

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self._ignorar = max(0, self._ignorar - 1)

    def handle_data(self, data: str) -> None:
        if not self._ignorar:
            texto = " ".join(data.split())
            if texto:
                self._partes.append(texto)

    def texto(self) -> str:
        return " ".join(self._partes)


class _SemRedirecionamento(HTTPRedirectHandler):
    """Faz cada redirecionamento passar pela validação da ferramenta."""

    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any):
        raise ConsultaInternetError(
            f"redirecionamento bloqueado para consulta direta: HTTP {code}"
        )


def _validar_url(url: str) -> tuple[str, str]:
    if not isinstance(url, str) or not url.strip():
        raise ConsultaInternetError("a URL precisa ser um texto não vazio")

    texto = url.strip()
    partes = urlsplit(texto)
    if partes.scheme.lower() not in {"http", "https"}:
        raise ConsultaInternetError("a consulta aceita somente http ou https")
    if not partes.hostname:
        raise ConsultaInternetError("a URL não informa um host")
    if partes.username or partes.password:
        raise ConsultaInternetError("URLs com usuário ou senha são bloqueadas")
    if partes.port not in {None, 80, 443}:
        raise ConsultaInternetError("portas customizadas são bloqueadas")
    if partes.fragment:
        texto = urlunsplit(
            (partes.scheme, partes.netloc, partes.path, partes.query, "")
        )
        partes = urlsplit(texto)

    host = partes.hostname.rstrip(".").casefold()
    if host in {"localhost", "localhost.localdomain"} or host.endswith(".local"):
        raise ConsultaInternetError("hosts locais são bloqueados")
    if not re.fullmatch(r"[a-z0-9.-]+", host):
        raise ConsultaInternetError("host com caracteres inválidos")

    try:
        enderecos = {
            info[4][0]
            for info in socket.getaddrinfo(
                host,
                partes.port or (443 if partes.scheme.lower() == "https" else 80),
                type=socket.SOCK_STREAM,
            )
        }
    except socket.gaierror as erro:
        raise ConsultaInternetError(f"não foi possível resolver o host: {host}") from erro

    if not enderecos:
        raise ConsultaInternetError("o host não resolveu para nenhum endereço")
    for endereco in enderecos:
        try:
            ip = ipaddress.ip_address(endereco)
        except ValueError as erro:
            raise ConsultaInternetError("o host resolveu para endereço inválido") from erro
        if not ip.is_global:
            raise ConsultaInternetError(
                "a consulta a redes locais ou reservadas foi bloqueada"
            )
    return texto, host


def _decodificar(resposta: Any, bruto: bytes) -> tuple[str, str]:
    tipo = resposta.headers.get_content_type().lower()
    permitido = (
        tipo.startswith("text/")
        or tipo in {"application/json", "application/xml", "application/xhtml+xml"}
    )
    if not permitido:
        raise ConsultaInternetError(
            f"tipo de conteúdo não permitido para leitura: {tipo}"
        )
    charset = resposta.headers.get_content_charset() or "utf-8"
    try:
        return tipo, bruto.decode(charset, errors="replace")
    except LookupError:
        return tipo, bruto.decode("utf-8", errors="replace")


def consultar_url(
    url: str,
    *,
    timeout: float = TIMEOUT_SEGUNDOS,
    maximo_bytes: int = MAXIMO_BYTES,
) -> ResultadoInternet:
    """Lê uma URL pública, textual e pequena após passar pelo protocolo."""

    verificacao = verificar_acao(
        TipoAcao.CONSULTAR_INTERNET,
        "internet/consulta",
    )
    if not verificacao.permitida:
        raise PermissionError(verificacao.mensagem)
    if maximo_bytes <= 0 or maximo_bytes > MAXIMO_BYTES:
        raise ValueError(f"maximo_bytes deve estar entre 1 e {MAXIMO_BYTES}")

    url_validada, host = _validar_url(url)
    request = Request(
        url_validada,
        headers={
            "Accept": "text/html, text/plain, application/json, application/xml",
            "User-Agent": "hen-isana/1.0 (consulta textual controlada)",
        },
        method="GET",
    )
    opener = build_opener(_SemRedirecionamento)
    try:
        with opener.open(request, timeout=timeout) as resposta:
            bruto = resposta.read(maximo_bytes + 1)
            if len(bruto) > maximo_bytes:
                raise ConsultaInternetError(
                    f"resposta maior que o limite de {maximo_bytes} bytes"
                )
            tipo, corpo = _decodificar(resposta, bruto)
            status = int(resposta.getcode() or 200)
    except ConsultaInternetError:
        raise
    except HTTPError as erro:
        raise ConsultaInternetError(
            f"servidor respondeu HTTP {erro.code} para {host}"
        ) from erro
    except (URLError, TimeoutError, OSError) as erro:
        raise ConsultaInternetError(
            f"não foi possível consultar {host}: {erro}"
        ) from erro

    runtime_log.acao(
        "ferramentas.internet",
        "consultar_url",
        "consulta pública concluída",
        {"host": host, "status": status, "bytes": len(bruto), "tipo": tipo},
    )
    return ResultadoInternet(url_validada, status, tipo, corpo)


def texto_visivel(resultado: ResultadoInternet) -> str:
    """Converte HTML/JSON em um trecho pequeno para a conversa."""

    if resultado.tipo_conteudo in {"application/json", "application/xml"}:
        if resultado.tipo_conteudo == "application/json":
            try:
                texto = json.dumps(
                    json.loads(resultado.corpo),
                    ensure_ascii=False,
                    indent=2,
                )
            except json.JSONDecodeError:
                texto = resultado.corpo
        else:
            texto = resultado.corpo
    elif "html" in resultado.tipo_conteudo:
        parser = _TextoHTML()
        parser.feed(resultado.corpo)
        texto = parser.texto()
    else:
        texto = resultado.corpo
    texto = " ".join(texto.split())
    return texto[:MAXIMO_CARACTERES_RESUMO].strip()


def _resumo_wikipedia(url: str, termo: str) -> Optional[DefinicaoInternet]:
    """Obtém um resumo curto de uma página da Wikipédia em português."""

    try:
        resultado = consultar_url(url)
    except ConsultaInternetError:
        return None
    dados = _json(resultado)
    titulo = str(dados.get("title") or "").strip()
    resumo = str(dados.get("extract") or "").strip()
    if not titulo or not resumo:
        return None
    urls = dados.get("content_urls")
    url_pagina = resultado.url
    if isinstance(urls, dict):
        desktop = urls.get("desktop")
        if isinstance(desktop, dict) and desktop.get("page"):
            url_pagina = str(desktop["page"])
    return DefinicaoInternet(
        termo=termo,
        titulo=titulo,
        resumo=" ".join(resumo.split())[:1_000],
        url=url_pagina,
    )


def consultar_definicao(termo: str) -> Optional[DefinicaoInternet]:
    """Procura uma definição pública sem executar ou persistir o conteúdo.

    A primeira tentativa usa o resumo direto da Wikipédia. Quando não existe
    uma página exata, a busca da própria Wikipédia encontra um título próximo
    e o resumo desse título é consultado em seguida.
    """

    nome = " ".join(str(termo).strip().split())
    if not re.fullmatch(
        r"[\wÀ-ÿ][\wÀ-ÿ .,'-]{1,79}",
        nome,
        flags=re.UNICODE,
    ):
        raise ValueError("o termo precisa ser um texto curto")

    resumo_url = (
        "https://pt.wikipedia.org/api/rest_v1/page/summary/"
        + quote(nome, safe="")
    )
    definicao = _resumo_wikipedia(resumo_url, nome)
    if definicao is not None:
        return definicao

    busca_url = (
        "https://pt.wikipedia.org/w/api.php?"
        + urlencode(
            {
                "action": "opensearch",
                "search": nome,
                "limit": 1,
                "namespace": 0,
                "format": "json",
            }
        )
    )
    try:
        busca = _json(consultar_url(busca_url))
    except ConsultaInternetError:
        return None
    titulos = busca.get("1")
    if not isinstance(titulos, list) or not titulos:
        return None
    titulo = str(titulos[0]).strip()
    if not titulo:
        return None
    pagina_url = (
        "https://pt.wikipedia.org/api/rest_v1/page/summary/"
        + quote(titulo, safe="")
    )
    return _resumo_wikipedia(pagina_url, nome)


_CODIGOS_TEMPO = {
    0: "céu limpo",
    1: "principalmente limpo",
    2: "parcialmente nublado",
    3: "nublado",
    45: "neblina",
    48: "neblina com geada",
    51: "garoa leve",
    53: "garoa moderada",
    55: "garoa intensa",
    61: "chuva leve",
    63: "chuva moderada",
    65: "chuva intensa",
    71: "neve leve",
    73: "neve moderada",
    75: "neve intensa",
    80: "pancadas de chuva leves",
    81: "pancadas de chuva moderadas",
    82: "pancadas de chuva intensas",
    95: "trovoada",
    96: "trovoada com granizo leve",
    99: "trovoada com granizo intenso",
}


def _json(resultado: ResultadoInternet) -> dict[str, Any]:
    try:
        dados = json.loads(resultado.corpo)
    except json.JSONDecodeError as erro:
        raise ConsultaInternetError("a fonte de internet retornou JSON inválido") from erro
    if not isinstance(dados, dict):
        raise ConsultaInternetError("a fonte de internet retornou formato inesperado")
    return dados


def consultar_clima(cidade: str) -> str:
    """Consulta condições atuais de uma cidade em uma fonte pública."""

    nome = " ".join(str(cidade).strip().split())
    if not re.fullmatch(r"[\wÀ-ÿ][\wÀ-ÿ .,'-]{1,79}", nome, flags=re.UNICODE):
        raise ValueError("informe uma cidade válida para consultar o tempo")

    geocode_url = (
        "https://geocoding-api.open-meteo.com/v1/search?"
        + urlencode(
            {
                "name": nome,
                "count": 1,
                "language": "pt",
                "format": "json",
            }
        )
    )
    localidades = _json(consultar_url(geocode_url))
    resultados = localidades.get("results")
    if not isinstance(resultados, list) or not resultados:
        return f"Não encontrei a cidade '{nome}' para consultar o tempo."
    localidade = resultados[0]
    if not isinstance(localidade, dict):
        raise ConsultaInternetError("a geocodificação retornou uma localidade inválida")

    latitude = localidade.get("latitude")
    longitude = localidade.get("longitude")
    if not isinstance(latitude, (int, float)) or not isinstance(longitude, (int, float)):
        raise ConsultaInternetError("a geocodificação não retornou coordenadas")

    previsao_url = (
        "https://api.open-meteo.com/v1/forecast?"
        + urlencode(
            {
                "latitude": latitude,
                "longitude": longitude,
                "current": (
                    "temperature_2m,apparent_temperature,relative_humidity_2m,"
                    "weather_code,wind_speed_10m"
                ),
                "timezone": "auto",
                "forecast_days": 1,
            }
        )
    )
    previsao = _json(consultar_url(previsao_url))
    atual = previsao.get("current")
    if not isinstance(atual, dict):
        raise ConsultaInternetError("a previsão não retornou as condições atuais")

    temperatura = atual.get("temperature_2m")
    sensacao = atual.get("apparent_temperature")
    umidade = atual.get("relative_humidity_2m")
    vento = atual.get("wind_speed_10m")
    codigo = atual.get("weather_code")
    condicao = _CODIGOS_TEMPO.get(int(codigo), "condição não informada")
    cidade_encontrada = str(localidade.get("name") or nome)
    pais = str(localidade.get("country") or "").strip()
    lugar = f"{cidade_encontrada}, {pais}" if pais else cidade_encontrada
    partes = [
        f"Em {lugar}, agora está {condicao}",
        f"com {temperatura} °C",
    ]
    if sensacao is not None:
        partes.append(f"sensação de {sensacao} °C")
    if umidade is not None:
        partes.append(f"umidade de {umidade}%")
    if vento is not None:
        partes.append(f"vento de {vento} km/h")
    return ", ".join(partes) + "."