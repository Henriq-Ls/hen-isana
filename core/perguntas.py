"""Seleção determinística de perguntas conforme lacunas de conhecimento."""


def gerar_pergunta_adaptativa(termo: str, campo: str) -> str:
    """Gera uma pergunta curta para a lacuna retornada pelo banco."""
    modelos = {
        "significado": f"O que '{termo}' significa? ",
        "exemplo_uso": f"Pode dar um exemplo de uso de '{termo}'? ",
        "contexto_uso": f"Em que contexto '{termo}' é usado? ",
    }
    try:
        return modelos[campo]
    except KeyError as erro:
        raise ValueError(
            f"não há pergunta adaptativa definida para a lacuna {campo!r}"
        ) from erro