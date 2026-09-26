"""Regras que toda ação solicitada pela IA deve respeitar."""

from .regras import TipoAcao
from .verificador import (
    Permissao,
    ResultadoVerificacao,
    emitir_permissao,
    validar_codigo_gerado,
    validar_permissao,
    verificar_acao,
)

__all__ = [
    "TipoAcao",
    "Permissao",
    "ResultadoVerificacao",
    "emitir_permissao",
    "validar_codigo_gerado",
    "validar_permissao",
    "verificar_acao",
]
