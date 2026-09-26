"""Consultas controladas ao relógio do sistema."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from _LOGS_ import log as runtime_log
from protocolo.regras import TipoAcao
from protocolo.verificador import verificar_acao


_DIAS = (
    "segunda-feira",
    "terça-feira",
    "quarta-feira",
    "quinta-feira",
    "sexta-feira",
    "sábado",
    "domingo",
)

_MESES = (
    "janeiro",
    "fevereiro",
    "março",
    "abril",
    "maio",
    "junho",
    "julho",
    "agosto",
    "setembro",
    "outubro",
    "novembro",
    "dezembro",
)


@dataclass(frozen=True)
class LeituraDataHora:
    """Leitura imutável do relógio em um fuso horário específico."""

    instante: datetime
    nome_fuso: str

    @property
    def data_extensa(self) -> str:
        return (
            f"{_DIAS[self.instante.weekday()]}, "
            f"{self.instante.day} de {_MESES[self.instante.month - 1]} "
            f"de {self.instante.year}"
        )

    @property
    def hora(self) -> str:
        return self.instante.strftime("%H:%M:%S")

    @property
    def texto_completo(self) -> str:
        return (
            f"Hoje é {self.data_extensa}. "
            f"Agora são {self.hora} (fuso {self.nome_fuso})."
        )


def consultar_data_hora(
    nome_fuso: Optional[str] = None,
) -> LeituraDataHora:
    """Consulta data e hora sem acessar arquivos nem serviços externos."""

    verificacao = verificar_acao(
        TipoAcao.CONSULTAR_SISTEMA,
        "sistema/data_hora",
    )
    if not verificacao.permitida:
        raise PermissionError(verificacao.mensagem)

    if nome_fuso:
        try:
            fuso = ZoneInfo(nome_fuso)
        except ZoneInfoNotFoundError as erro:
            raise ValueError(f"fuso horário desconhecido: {nome_fuso}") from erro
    else:
        fuso = datetime.now().astimezone().tzinfo
        if fuso is None:
            raise RuntimeError("o sistema não informou um fuso horário")

    instante = datetime.now(tz=fuso)
    nome_resolvido = getattr(fuso, "key", None) or instante.tzname() or "local"
    leitura = LeituraDataHora(instante, nome_resolvido)
    runtime_log.acao(
        "ferramentas.sistema",
        "consultar_data_hora",
        "data e hora consultadas",
        {"fuso": nome_resolvido},
    )
    return leitura