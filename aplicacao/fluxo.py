"""Ponto de entrada terminal do hen-isana."""

from dataclasses import dataclass
import re
from pathlib import Path
from typing import Callable, Iterable, Optional

from _APPDATA_ import appdata
from _LOGS_ import log
from bancos.conhecimento import (
    ConhecimentoDB,
    EntradaConhecimento,
    FatoConhecimento,
)
from bancos.indice_codigo import IndiceCodigoDB
from bancos.log_mudancas import LogMudancasDB
from bancos.propostas_aprendizagem import PropostasAprendizagem
from bancos.relacoes import RelacoesDB
from backup.diagnostico import DiagnosticoDB
from core.composicao_resposta import (
    compor_resposta_conversacional as _compor_resposta_conversacional,
    compor_resposta_explicativa as _compor_resposta_explicativa,
    compor_resposta_dinamica as _compor_resposta_dinamica,
    entrada_eh_conversacional as _entrada_eh_conversacional,
)
from core.contexto_conversa import (
    CorrecaoDigitacaoPendente,
    ContextoConversa,
    DesambiguacaoPendente,
    Mencao,
)
from core.interpretacao import interpretar_pergunta, parece_pergunta
from core.linguagem import (
    EXPRESSOES_CONVERSACIONAIS,
    PALAVRAS_FUNCIONAIS,
    PALAVRAS_IGNORADAS_AO_APRENDER_RESPOSTA,
)
from core.normalizador import (
    eh_vocativo,
    normalizar_frase,
    normalizar_termo_estrito,
)
from core.perguntas import gerar_pergunta_adaptativa as _gerar_pergunta_adaptativa
from core.roteador import Intencao, rotear
from ferramentas.busca import (
    buscar_conhecimento,
    buscar_conhecimento_confirmado,
    buscar_conhecimento_por_id_confirmado,
    buscar_fatos_confirmados,
    identificar_lacunas,
    listar_conhecimento_confirmado,
)
from ferramentas.internet import (
    ConsultaInternetError,
    consultar_clima,
    consultar_definicao,
    consultar_url,
    texto_visivel,
)
from ferramentas.sistema import consultar_data_hora
from professor import Professor, ProfessorRateLimitError
from protocolo.regras import (
    ALVO_CONHECIMENTO,
    ALVO_RELACOES,
    TipoAcao,
)
from protocolo.verificador import Permissao, emitir_permissao


BASE_DIR = Path(__file__).resolve().parents[1]
RespostaUsuario = Callable[[str], str]
LIMIAR_SUGESTAO_DIGITACAO = 0.78
_PREFIXOS_CONTROLE_RESPOSTA = (
    "termo:",
    "comando:",
    "fato:",
    "proposta-termo:",
    "proposta-fato:",
    "proposta-correcao-fato:",
    "aprovar-proposta:",
    "recusar-proposta:",
    "aplicar-proposta:",
    "reverter-proposta:",
    "listar-propostas",
)


class AprendizagemCancelada(Exception):
    """Interrompe uma aprendizagem sem persistir respostas parciais."""


@dataclass(frozen=True)
class CampoProposto:
    nome: str
    valor_anterior: Optional[str]
    valor_proposto: str


@dataclass(frozen=True)
class PropostaConhecimento:
    entidade: str
    identificador: str
    contexto: Optional[str]
    campos: tuple[CampoProposto, ...]
    significado: Optional[str] = None
    motivo_confirmacao: Optional[str] = None

    @property
    def requer_confirmacao(self) -> bool:
        return bool(self.campos) and self.motivo_confirmacao is not None


def _eh_comando_proposta(frase: str) -> bool:
    return bool(
        re.match(
            r"^\s*(?:proposta-fato|proposta-correcao-fato|"
            r"proposta-termo|"
            r"aprovar-proposta|recusar-proposta|aplicar-proposta|"
            r"reverter-proposta|listar-propostas)\b",
            frase,
            flags=re.IGNORECASE,
        )
    )


def _resposta_obrigatoria_proposta(
    perguntar: RespostaUsuario,
    mensagem: str,
) -> str:
    resposta = perguntar(mensagem)
    if not isinstance(resposta, str):
        raise TypeError("a resposta à proposta deve ser texto")
    if resposta.strip().casefold() == "cancelar":
        raise AprendizagemCancelada
    resposta_limpa = " ".join(resposta.strip().split())
    if not resposta_limpa:
        raise ValueError("o campo informado não pode ficar vazio")
    return resposta_limpa


def _processar_comando_proposta(
    frase: str,
    banco: ConhecimentoDB,
    perguntar: RespostaUsuario,
    *,
    propostas: Optional[PropostasAprendizagem],
    modo_aprendizagem: bool,
    permissao_memoria: Optional[Permissao],
) -> Optional[list[str]]:
    """Executa apenas comandos de proposta digitados no modo aprendizagem."""
    if not _eh_comando_proposta(frase):
        return None
    if not modo_aprendizagem:
        return [
            "Propostas de aprendizagem só podem ser gerenciadas no modo "
            "aprendizagem; a conversa permaneceu somente leitura."
        ]
    if propostas is None:
        return [
            "O fluxo de propostas não foi inicializado nesta sessão de "
            "aprendizagem."
        ]

    comando = frase.strip()
    correspondencia = re.fullmatch(
        r"proposta-termo\s*:\s*([^|]+)\s*\|\s*([^|]+)\s*\|\s*"
        r"([^|]+?)(?:\s*\|\s*([^|]+))?",
        comando,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if correspondencia:
        termo = correspondencia.group(1).strip()
        campo = correspondencia.group(2).strip()
        valor = correspondencia.group(3).strip()
        contexto_alvo = (
            correspondencia.group(4).strip()
            if correspondencia.group(4)
            else None
        )
        motivo = _resposta_obrigatoria_proposta(
            perguntar,
            "Por que esta correção/experiência deve ser considerada? ",
        )
        origem = _resposta_obrigatoria_proposta(
            perguntar,
            "Qual é a origem da informação? ",
        )
        proposta = propostas.propor_termo(
            termo,
            {campo: valor},
            motivo=motivo,
            origem=origem,
            contexto_alvo=contexto_alvo,
        )
        return [
            f"Proposta #{proposta.id} registrada para revisão; nada foi "
            "gravado no conhecimento. Use aprovar-proposta e, depois, "
            "aplicar-proposta para efetivar."
        ]

    correspondencia = re.fullmatch(
        r"proposta-fato\s*:\s*(.+)",
        comando,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if correspondencia:
        afirmacao = correspondencia.group(1).strip()
        contexto = _resposta_obrigatoria_proposta(
            perguntar,
            "Em que contexto este fato se aplica? (ou 'cancelar') ",
        )
        motivo = _resposta_obrigatoria_proposta(
            perguntar,
            "Por que esta experiência/correção deve ser considerada? ",
        )
        origem = _resposta_obrigatoria_proposta(
            perguntar,
            "Qual é a origem da informação? ",
        )
        proposta = propostas.propor_fato(
            afirmacao,
            contexto,
            motivo=motivo,
            origem=origem,
        )
        return [
            f"Proposta #{proposta.id} registrada para revisão; nada foi "
            "gravado no conhecimento. Use aprovar-proposta e, depois, "
            "aplicar-proposta para efetivar."
        ]

    correspondencia = re.fullmatch(
        r"proposta-correcao-fato\s*:\s*(\d+)\s*\|\s*(.+)",
        comando,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if correspondencia:
        fato_id = int(correspondencia.group(1))
        afirmacao = correspondencia.group(2).strip()
        fato = next(
            (item for item in banco.buscar_fatos() if item.id == fato_id),
            None,
        )
        if fato is None:
            raise LookupError(f"fato {fato_id} não encontrado")
        motivo = _resposta_obrigatoria_proposta(
            perguntar,
            "Por que esta correção deve ser considerada? ",
        )
        origem = _resposta_obrigatoria_proposta(
            perguntar,
            "Qual é a origem da correção? ",
        )
        proposta = propostas.propor_fato(
            afirmacao,
            fato.contexto,
            motivo=motivo,
            origem=origem,
            fato_id=fato_id,
        )
        return [
            f"Proposta #{proposta.id} registrada para revisão; o fato "
            "original não foi alterado."
        ]

    correspondencia = re.fullmatch(
        r"(aprovar-proposta|aplicar-proposta|reverter-proposta)"
        r"\s*:\s*(\d+)",
        comando,
        flags=re.IGNORECASE,
    )
    if correspondencia:
        acao = correspondencia.group(1).casefold()
        proposta_id = int(correspondencia.group(2))
        if acao == "aprovar-proposta":
            proposta = propostas.aprovar(proposta_id)
            return [
                f"Proposta #{proposta.id} aprovada; ainda não foi aplicada "
                "ao conhecimento."
            ]
        if permissao_memoria is None:
            return [
                "A aplicação/reversão exige uma permissão explícita de "
                "gravação do conhecimento."
            ]
        if acao == "aplicar-proposta":
            proposta = propostas.aplicar(
                proposta_id,
                permissao=permissao_memoria,
            )
            return [
                f"Proposta #{proposta.id} aplicada ao conhecimento confirmado."
            ]
        proposta = propostas.reverter(
            proposta_id,
            permissao=permissao_memoria,
        )
        return [f"Proposta #{proposta.id} revertida; auditoria preservada."]

    correspondencia = re.fullmatch(
        r"recusar-proposta\s*:\s*(\d+)\s*\|\s*(.+)",
        comando,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if correspondencia:
        proposta = propostas.recusar(
            int(correspondencia.group(1)),
            correspondencia.group(2).strip(),
        )
        return [f"Proposta #{proposta.id} recusada; conteúdo não aplicado."]

    if re.fullmatch(r"listar-propostas", comando, flags=re.IGNORECASE):
        itens = propostas.listar()
        if not itens:
            return ["Não há propostas de aprendizagem registradas."]
        return [
            "Propostas de aprendizagem:\n"
            + "\n".join(
                f"#{item.id} [{item.estado}] {item.entidade}/"
                f"{item.acao} — origem: {item.origem}; "
                f"motivo: {item.motivo}; conteúdo: {item.conteudo}; "
                f"antes: {item.antes or 'sem registro anterior'}; "
                f"resultado: {item.resultado or 'pendente'}"
                for item in itens
            )
        ]

    return [
        "Comando de proposta inválido. Use proposta-termo:, proposta-fato:, "
        "proposta-correcao-fato:, aprovar-proposta:, recusar-proposta:, "
        "aplicar-proposta:, reverter-proposta: ou listar-propostas."
    ]


def _normalizar_unidade_textual(texto: str) -> str:
    """Converte uma entrada em texto comparável ao tokenizador."""
    return " ".join(re.findall(r"\w+", texto.casefold(), flags=re.UNICODE))


def _expressoes_conversacionais() -> tuple[str, ...]:
    """Retorna expressões ordenadas para priorizar as mais longas."""
    return tuple(
        sorted(
            EXPRESSOES_CONVERSACIONAIS,
            key=lambda item: len(item.split()),
            reverse=True,
        )
    )


_INICIOS_CONVERSACIONAIS_SEM_ASSUNTO = (
    "até ",
    "ate ",
    "valeu",
    "obrigado",
    "obrigada",
    "desculpa",
    "desculpe",
    "foi mal",
    "espera",
    "tô ",
    "to ",
    "estou ",
    "meu deus",
    "fala ",
    "oi ",
    "ola ",
    "olá ",
)

_PADROES_PERGUNTA_EMBUTIDA = (
    r"\b(?:o que|qual|quais|como|quando|onde|quem)\s+"
    r"(?:é|e|significa|são|sao|foi|será|sera)\b",
    r"\bpor\s+que\b.*\?",
)

_REAÇÕES_SEM_ASSUNTO = frozenset(
    {
        "que porcaria",
        "que droga",
        "que merda",
        "meu deus",
        "meu deus do ceu",
        "mano do ceu",
        "mano do céu",
    }
)


def _entrada_de_aprendizagem_sem_assunto(
    frase: str,
    tokens: list[str],
) -> bool:
    """Evita ensinar fala social, reação ou frase sem assunto delimitado.

    Uma expressão curta ainda pode ser um termo legítimo: ``uma vez`` é um
    exemplo. Frases longas devem usar ``termo: ...`` quando a intenção for
    ensinar a expressão completa; isso evita que uma frase conversacional seja
    confundida com um conceito só porque contém várias palavras.
    """
    texto = normalizar_frase(frase)
    comparavel = _normalizar_unidade_textual(texto)
    if not comparavel:
        return True

    expressoes = {
        _normalizar_unidade_textual(expressao)
        for expressao in _expressoes_conversacionais()
    }
    if comparavel in expressoes or comparavel in _REAÇÕES_SEM_ASSUNTO:
        return True

    rota = rotear(texto)
    if rota.intencao is not None:
        return True

    if any(
        re.search(padrao, texto, flags=re.IGNORECASE)
        for padrao in _PADROES_PERGUNTA_EMBUTIDA
    ):
        return True

    if (
        len(tokens) > 1
        and parece_pergunta(texto)
        and not interpretar_pergunta(texto)
    ):
        return True

    if any(
        comparavel == inicio.strip()
        or comparavel.startswith(inicio.strip() + " ")
        for inicio in _INICIOS_CONVERSACIONAIS_SEM_ASSUNTO
    ):
        return True

    # Uma frase com mais de três unidades é tratada como fala, não como um
    # termo composto implícito. O comando ``termo:`` continua disponível para
    # cadastrar expressões longas de propósito.
    return len(tokens) > 3


def _mensagem_sem_assunto_de_aprendizagem() -> str:
    """Orienta uma nova entrada sem iniciar perguntas ou chamadas externas."""
    return (
        "Não identifiquei um termo claro para aprender nessa frase. "
        "Digite um termo ou use 'termo: expressão' para ensinar uma frase "
        "completa."
    )


def termos_desconhecidos_no_texto(
    texto: str,
    banco: ConhecimentoDB,
    ignorar: Iterable[str] = (),
) -> list[str]:
    """Seleciona palavras relevantes ainda ausentes do banco."""
    ignorados = {
        _normalizar_unidade_textual(str(item))
        for item in ignorar
    }
    encontrados: list[str] = []
    vistos: set[str] = set()
    for token in tokenizar(texto, banco.listar_expressoes_compostas()):
        normalizado = _normalizar_unidade_textual(token)
        if (
            len(normalizado) < 3
            or normalizado in vistos
            or normalizado in ignorados
            or normalizado in PALAVRAS_IGNORADAS_AO_APRENDER_RESPOSTA
        ):
            continue
        vistos.add(normalizado)
        if not banco.buscar_termo(normalizado):
            encontrados.append(normalizado)
    return encontrados


def tokenizar(
    frase: str,
    expressoes_conhecidas: Iterable[str] = (),
) -> list[str]:
    """Quebra uma frase preservando expressões compostas de conversa e do banco."""

    if not isinstance(frase, str):
        raise TypeError("frase deve ser uma string")

    palavras = re.findall(r"\w+", frase.lower(), flags=re.UNICODE)
    expressao_tokens = []
    expressoes = (*_expressoes_conversacionais(), *expressoes_conhecidas)
    for expressao in expressoes:
        partes = tuple(re.findall(r"\w+", expressao.lower(), flags=re.UNICODE))
        if len(partes) > 1:
            expressao_tokens.append(partes)
    expressao_tokens.sort(key=len, reverse=True)

    resultado: list[str] = []
    indice = 0
    while indice < len(palavras):
        encontrada: Optional[tuple[str, ...]] = None
        for partes in expressao_tokens:
            fim = indice + len(partes)
            if tuple(palavras[indice:fim]) == partes:
                encontrada = partes
                break
        if encontrada:
            resultado.append(" ".join(encontrada))
            indice += len(encontrada)
        else:
            resultado.append(palavras[indice])
            indice += 1
    return resultado


def _extrair_mencoes_contexto(
    frase: str,
    banco: ConhecimentoDB,
) -> list[Mencao]:
    """Extrai termos conhecidos para o contexto, sem gravar nada."""
    mencoes: list[Mencao] = []
    vistos: set[str] = set()
    primeiro_indice_entidade: Optional[int] = None
    tokens = tokenizar(frase, banco.listar_expressoes_compostas())
    for indice, token in enumerate(tokens):
        normalizado = _normalizar_unidade_textual(token)
        if (
            not normalizado
            or normalizado in vistos
            or normalizado in PALAVRAS_FUNCIONAIS
            or eh_vocativo(normalizado)
        ):
            continue
        entradas = buscar_conhecimento_confirmado(banco, token)
        entradas = [entrada for entrada in entradas if entrada.completa]
        if len(entradas) != 1:
            continue
        if primeiro_indice_entidade is None:
            primeiro_indice_entidade = indice
        vistos.add(normalizado)
        entrada = entradas[0]
        tipo = entrada.tipo.casefold() if entrada.tipo else None
        mencoes.append(
            Mencao(
                texto_original=token,
                forma_normalizada=normalizado,
                tipo_lexical_conhecido=tipo,
                numero_e_genero=_inferir_numero_e_genero(
                    normalizado,
                    tipo,
                ),
                posicao_na_frase=indice,
                eh_sujeito=indice == primeiro_indice_entidade,
            )
        )
    return mencoes


def _inferir_numero_e_genero(
    termo: str,
    tipo: Optional[str],
) -> Optional[str]:
    """Usa somente marcações explícitas; não inventa gênero gramatical."""
    partes = []
    informacao = f"{termo} {tipo or ''}".casefold()
    for marcador in ("singular", "plural", "masculino", "feminino", "neutro"):
        if marcador in informacao:
            partes.append(marcador)
    return " ".join(partes) or None


def _resposta_obrigatoria(
    perguntar: RespostaUsuario,
    mensagem: str,
    termo: str,
    campo: str,
    origem_resposta: str = "usuario",
) -> str:
    while True:
        resposta = _perguntar_com_cancelamento(
            perguntar,
            mensagem,
            termo,
            campo,
            origem_resposta,
        )
        motivo_rejeicao = _validar_resposta_campo(resposta, termo, campo)
        if motivo_rejeicao is None:
            return resposta
        if origem_resposta == "usuario":
            print(
                "Resposta rejeitada: "
                f"{motivo_rejeicao} Informe novamente."
            )
        log.aviso(
            "main",
            "_resposta_obrigatoria",
            "resposta de campo rejeitada: "
            f"termo={termo!r}, campo={campo!r}, motivo={motivo_rejeicao}",
        )


def _validar_resposta_campo(
    resposta: str,
    termo: str,
    campo: str,
) -> Optional[str]:
    """Rejeita comandos, ecos e respostas sem conteúdo semântico útil."""
    if not isinstance(resposta, str):
        return "a resposta precisa ser texto"

    limpa = " ".join(resposta.strip().split())
    if not limpa:
        return "a resposta não pode ficar vazia"

    comparavel = limpa.casefold()
    termo_comparavel = " ".join(termo.strip().split()).casefold()
    campo_comparavel = " ".join(campo.strip().split()).casefold()
    if comparavel == termo_comparavel:
        return "a resposta é igual ao termo que está sendo cadastrado"
    if comparavel == campo_comparavel:
        return "a resposta é apenas o nome do campo solicitado"

    if any(
        comparavel.startswith(prefixo)
        for prefixo in _PREFIXOS_CONTROLE_RESPOSTA
    ):
        return "a resposta parece ser um comando ou uma entrada de controle"

    return None


def _perguntar_com_cancelamento(
    perguntar: RespostaUsuario,
    mensagem: str,
    termo: str,
    campo: str,
    origem_resposta: str = "usuario",
) -> str:
    log.pergunta_aprendizagem(termo, campo, mensagem)
    try:
        resposta = perguntar(mensagem).strip()
    except (EOFError, KeyboardInterrupt) as erro:
        raise AprendizagemCancelada(
            "a entrada foi encerrada pelo usuário"
        ) from erro
    if origem_resposta == "usuario":
        log.resposta_usuario(termo, campo, resposta)
    comando = re.sub(r"[.!?]+$", "", resposta.casefold().strip())
    if comando in {
        "cancelar",
        "cancele",
        "cancel",
        "desistir",
        "abortar",
        "sair",
    }:
        raise AprendizagemCancelada("aprendizagem cancelada pelo usuário")
    return resposta


def _texto_incerto(texto: Optional[str]) -> bool:
    if not texto:
        return False
    normalizado = " ".join(texto.casefold().split())
    marcadores = (
        r"\btalvez\b",
        r"\bacho\b",
        r"\bprovavelmente\b",
        r"\baparentemente\b",
        r"\bincerto\b",
        r"\bduvidoso\b",
        r"\bpode ser\b",
        r"\bnão sei\b",
        r"\bnao sei\b",
        r"\bnão tenho certeza\b",
        r"\bnao tenho certeza\b",
    )
    return any(re.search(marcador, normalizado) for marcador in marcadores)


def _montar_proposta_termo(
    termo: str,
    atual: Optional[EntradaConhecimento],
    valores: dict[str, Optional[str]],
    *,
    motivo_extra: Optional[str] = None,
) -> PropostaConhecimento:
    alteracoes = []
    tem_correcao = False
    tem_incerteza = False
    for campo in ConhecimentoDB.CAMPOS_CONHECIMENTO:
        novo_valor = valores.get(campo)
        if not novo_valor:
            continue
        anterior = getattr(atual, campo) if atual is not None else None
        if anterior == novo_valor:
            continue
        alteracoes.append(
            CampoProposto(
                nome=campo,
                valor_anterior=anterior,
                valor_proposto=novo_valor,
            )
        )
        tem_correcao = tem_correcao or anterior is not None
        tem_incerteza = tem_incerteza or _texto_incerto(novo_valor)

    motivos = []
    if tem_correcao:
        motivos.append("a proposta altera um dado já armazenado")
    if tem_incerteza:
        motivos.append("a resposta contém um marcador de incerteza")
    if motivo_extra:
        motivos.append(motivo_extra)
    return PropostaConhecimento(
        entidade="termo",
        identificador=termo,
        contexto=valores.get("contexto_uso"),
        campos=tuple(alteracoes),
        significado=valores.get("significado"),
        motivo_confirmacao="; ".join(motivos) or None,
    )


def _montar_proposta_fato(
    afirmacao: str,
    contexto: str,
    atual: Optional[FatoConhecimento] = None,
) -> PropostaConhecimento:
    incerto = _texto_incerto(afirmacao) or _texto_incerto(contexto)
    alteracoes = []
    if atual is None or atual.afirmacao != afirmacao:
        alteracoes.append(
            CampoProposto(
                "afirmacao",
                atual.afirmacao if atual else None,
                afirmacao,
            )
        )
    if atual is None or atual.contexto != contexto:
        alteracoes.append(
            CampoProposto(
                "contexto",
                atual.contexto if atual else None,
                contexto,
            )
        )
    motivos = []
    if atual is not None and alteracoes:
        motivos.append("a proposta corrige um fato já armazenado")
    elif atual is None:
        motivos.append("a proposta registra um fato independente novo")
    if incerto:
        motivos.append(
            "a afirmação ou o contexto contém um marcador de incerteza"
        )
    return PropostaConhecimento(
        entidade="fato",
        identificador=afirmacao,
        contexto=contexto,
        campos=tuple(alteracoes),
        motivo_confirmacao="; ".join(motivos) or None,
    )


def _mensagem_proposta(proposta: PropostaConhecimento) -> str:
    rotulos = {
        "tipo": "tipo",
        "significado": "significado",
        "contexto_uso": "contexto de uso",
        "resposta_padrao": "resposta padrão",
        "relacionados": "termos relacionados",
        "exemplo_uso": "exemplo de uso",
        "afirmacao": "afirmação",
        "contexto": "contexto",
    }
    entidade = "fato" if proposta.entidade == "fato" else "termo"
    linhas = [f"Proposta estruturada de conhecimento ({entidade}):"]
    linhas.append(f"- identificador: '{proposta.identificador}'")
    for campo in proposta.campos:
        rotulo = rotulos.get(campo.nome, campo.nome)
        if campo.valor_anterior is None:
            linhas.append(f"- {rotulo}: '{campo.valor_proposto}' (novo)")
        else:
            linhas.append(
                f"- {rotulo}: '{campo.valor_anterior}' → "
                f"'{campo.valor_proposto}'"
            )
    if proposta.contexto and not any(
        campo.nome in {"contexto", "contexto_uso"}
        for campo in proposta.campos
    ):
        linhas.append(f"- contexto: '{proposta.contexto}'")
    if proposta.motivo_confirmacao:
        linhas.append(f"Motivo da confirmação: {proposta.motivo_confirmacao}.")
    return "\n".join(linhas) + "\nConfirma? [s/n] "


def _nao(resposta: str) -> bool:
    return resposta.strip().casefold() in {
        "n",
        "não",
        "nao",
        "no",
        "nope",
    }


def _confirmar_proposta(
    proposta: PropostaConhecimento,
    perguntar: RespostaUsuario,
    origem_resposta: str = "usuario",
) -> bool:
    if not proposta.requer_confirmacao:
        return True
    if origem_resposta != "usuario":
        log.aviso(
            "main",
            "_confirmar_proposta",
            "proposta requer confirmação do usuário; fonte automática "
            f"'{origem_resposta}' não pode confirmá-la",
        )
        return False
    try:
        while True:
            resposta = _perguntar_com_cancelamento(
                perguntar,
                _mensagem_proposta(proposta),
                proposta.identificador,
                "confirmacao_proposta",
                origem_resposta,
            )
            if _sim(resposta):
                return True
            if _nao(resposta):
                log.aviso(
                    "main",
                    "_confirmar_proposta",
                    "proposta recusada; nenhum dado foi gravado "
                    f"(entidade: {proposta.entidade})",
                )
                return False
            if origem_resposta == "usuario":
                print("Responda sim ou não, ou digite 'cancelar'.")
    except AprendizagemCancelada:
        log.aviso(
            "main",
            "_confirmar_proposta",
            "confirmação cancelada; nenhum dado foi gravado "
            f"(entidade: {proposta.entidade})",
        )
        return False


def _selecionar_sentido_existente(
    termo: str,
    entradas: list[EntradaConhecimento],
    perguntar: RespostaUsuario,
    origem_resposta: str,
) -> EntradaConhecimento:
    """Exige uma escolha explícita quando o termo tem mais de um sentido."""
    opcoes = []
    for indice, entrada in enumerate(entradas, start=1):
        contexto = entrada.contexto_uso or "contexto não informado"
        significado = entrada.significado or "significado ainda não informado"
        opcoes.append(
            f"{indice}. {contexto} — {significado}"
        )
    mensagem = (
        f"Encontrei mais de um sentido para '{termo}': "
        + "; ".join(opcoes)
        + ". Qual número devo usar? "
    )

    while True:
        resposta = _resposta_obrigatoria(
            perguntar,
            mensagem,
            termo,
            "desambiguacao",
            origem_resposta,
        )
        try:
            indice = int(resposta)
        except ValueError:
            indice = 0
        if 1 <= indice <= len(entradas):
            return entradas[indice - 1]
        if origem_resposta == "usuario":
            print(f"Escolha um número entre 1 e {len(entradas)}.")


def _sim(resposta: str) -> bool:
    return resposta.strip().lower() in {
        "s",
        "sim",
        "ss",
        "yes",
        "y",
    }


def _resposta_padrao_parece_definicao(entrada: EntradaConhecimento) -> bool:
    """Detecta uma saudação salva como definição em vez de resposta."""
    tipo = (entrada.tipo or "").casefold()
    resposta = (entrada.resposta_padrao or "").casefold()
    categoria_de_saudacao = any(
        palavra in tipo
        for palavra in ("sauda", "cumpr", "greeting")
    )
    parece_explicacao = any(
        trecho in resposta
        for trecho in (
            "é um cumprimento",
            "é uma saudação",
            "significa",
            "usado como cumprimento",
            "usada como saudação",
        )
    )
    return categoria_de_saudacao and parece_explicacao


def _responder_ferramenta(frase: str) -> Optional[list[str]]:
    """Executa somente consultas explícitas e pequenas do sistema ou da web."""

    texto = " ".join(frase.strip().split())
    sem_pontuacao = texto.rstrip("?.! ").casefold()
    leitura = None

    rota = rotear(frase)
    intencao = rota.intencao
    consulta_data = intencao == Intencao.CONSULTAR_DATA
    consulta_hora = intencao == Intencao.CONSULTAR_HORA
    consulta_data_hora = intencao == Intencao.CONSULTAR_DATA_HORA
    if intencao is not None:
        log.passo(
            "main",
            "_responder_ferramenta",
            "intenção operacional reconhecida",
            {
                "intencao": intencao.value,
                "confianca": rota.confianca,
                "frase_normalizada": sem_pontuacao,
            },
        )
    if consulta_data or consulta_hora or consulta_data_hora:
        leitura = consultar_data_hora()
        if consulta_data_hora:
            resposta = leitura.texto_completo
        elif consulta_data:
            resposta = f"Hoje é {leitura.data_extensa}."
        else:
            resposta = f"Agora são {leitura.hora} (fuso {leitura.nome_fuso})."
        log.acao(
            "main",
            "_responder_ferramenta",
            "consulta de relógio respondida",
            {"tipo": "data_hora"},
        )
        return [resposta]

    clima = re.fullmatch(
        r"(?:como\s+(?:está|esta|vai)\s+o\s+tempo|"
        r"qual\s+a\s+previsão\s+do\s+tempo|"
        r"qual\s+a\s+previsao\s+do\s+tempo|"
        r"previsão\s+do\s+tempo|previsao\s+do\s+tempo|"
        r"vai\s+chover)"
        r"(?:\s+(?:em|no|na|para)\s+(.+))?",
        sem_pontuacao,
        flags=re.IGNORECASE,
    )
    if clima:
        cidade = (clima.group(1) or "").strip()
        if not cidade:
            return [
                "Para consultar o tempo, diga a cidade. "
                "Exemplo: como está o tempo em São Paulo?"
            ]
        try:
            resposta = consultar_clima(cidade)
        except (ConsultaInternetError, ValueError) as erro:
            resposta = f"Não consegui consultar o tempo agora: {erro}"
        log.acao(
            "main",
            "_responder_ferramenta",
            "consulta de clima respondida",
            {"cidade": cidade},
        )
        return [resposta]

    url = re.fullmatch(
        r"(?:consulte|consultar|acesse|abra|busque)\s+"
        r"(https?://[^\s]+)",
        texto,
        flags=re.IGNORECASE,
    )
    if url:
        endereco = url.group(1).rstrip(".,;:!?")
        try:
            resultado = consultar_url(endereco)
            conteudo = texto_visivel(resultado)
            resposta = (
                f"Consulta concluída em {resultado.url} "
                f"(HTTP {resultado.status})."
            )
            if conteudo:
                resposta += f" Conteúdo: {conteudo}"
        except (ConsultaInternetError, ValueError) as erro:
            resposta = f"Não consegui consultar a internet agora: {erro}"
        log.acao(
            "main",
            "_responder_ferramenta",
            "consulta de URL respondida",
            {"url": endereco},
        )
        return [resposta]

    return None


def aprender_termo(
    termo: str,
    banco: ConhecimentoDB,
    perguntar: RespostaUsuario = input,
    *,
    contexto: Optional[str] = None,
    relacoes: Optional[RelacoesDB] = None,
    origem_resposta: str = "usuario",
    usar_internet: bool = False,
    permissao_memoria: Optional[Permissao] = None,
    permissao_relacao: Optional[Permissao] = None,
    ao_aceitar_sugestao: Optional[Callable[[str], None]] = None,
) -> Optional[EntradaConhecimento]:
    """Aprende apenas os campos que ainda faltam para um termo."""

    log.passo(
        "main",
        "aprender_termo",
        "iniciando consulta e aprendizagem",
        {"termo": termo, "contexto": contexto},
    )
    existentes = banco.buscar_termo(termo, contexto)
    if contexto is None and len(existentes) > 1:
        entrada_selecionada = _selecionar_sentido_existente(
            termo,
            existentes,
            perguntar,
            origem_resposta,
        )
        contexto = entrada_selecionada.contexto_uso
        existentes = [entrada_selecionada]

    completos = [entrada for entrada in existentes if entrada.completa]
    if completos:
        entrada = completos[0]
        if (
            origem_resposta == "professor"
            and _resposta_padrao_parece_definicao(entrada)
        ):
            pergunta_reparo = (
                f"Qual resposta devo dar quando '{termo}' aparecer? "
                "Dê uma resposta direta ao usuário, não uma definição."
            )
            resposta_nova = _resposta_obrigatoria(
                perguntar,
                pergunta_reparo,
                termo,
                "resposta_padrao",
                origem_resposta,
            )
            valores_propostos = {
                campo: getattr(entrada, campo)
                for campo in ConhecimentoDB.CAMPOS_CONHECIMENTO
            }
            valores_propostos["resposta_padrao"] = resposta_nova
            proposta = _montar_proposta_termo(
                termo,
                entrada,
                valores_propostos,
            )
            if not _confirmar_proposta(
                proposta,
                perguntar,
                origem_resposta,
            ):
                return None
            entrada = banco.salvar_termo(
                termo=termo,
                tipo=entrada.tipo,
                significado=entrada.significado,
                contexto_uso=entrada.contexto_uso,
                resposta_padrao=resposta_nova,
                relacionados=entrada.relacionados,
                permissao=permissao_memoria,
            )
            log.aprendizado(
                termo,
                {
                    "entrada_id": entrada.id,
                    "campos_preenchidos": ["resposta_padrao"],
                    "modo": "reparo_resposta_padrao",
                },
            )
        log.passo(
            "main",
            "aprender_termo",
            "termo já conhecido; perguntas não repetidas",
            {"termo": termo, "entrada_id": entrada.id},
        )
        return entrada

    termo_relacionado: Optional[EntradaConhecimento] = None
    sugestoes = banco.sugerir_termos(termo)
    if sugestoes:
        sugestao = sugestoes[0]
        pergunta_relacao = (
            f"'{termo}' parece relacionado a '{sugestao}'. "
            "É a mesma coisa ou um sinônimo? [s/n] "
        )
        confirmar = _perguntar_com_cancelamento(
            perguntar,
            pergunta_relacao,
            termo,
            "relacionamento",
            origem_resposta,
        )
        if _sim(confirmar):
            candidatos = banco.buscar_termo(sugestao)
            if candidatos:
                termo_relacionado = candidatos[0]

    if termo_relacionado is not None:
        valores_propostos = {
            "tipo": termo_relacionado.tipo,
            "significado": termo_relacionado.significado,
            "contexto_uso": termo_relacionado.contexto_uso,
            "resposta_padrao": termo_relacionado.resposta_padrao,
            "relacionados": termo_relacionado.termo,
            "exemplo_uso": termo_relacionado.exemplo_uso,
        }
        proposta = _montar_proposta_termo(
            termo,
            None,
            valores_propostos,
            motivo_extra="o termo foi associado a um sinônimo existente",
        )
        if not _confirmar_proposta(proposta, perguntar, origem_resposta):
            return None
        entrada = banco.salvar_termo(
            termo=termo,
            tipo=termo_relacionado.tipo,
            significado=termo_relacionado.significado,
            contexto_uso=termo_relacionado.contexto_uso,
            resposta_padrao=termo_relacionado.resposta_padrao,
            relacionados=termo_relacionado.termo,
            permissao=permissao_memoria,
        )
        if relacoes is not None:
            relacoes.adicionar(
                entrada.id,
                termo_relacionado.id,
                permissao=permissao_relacao,
            )
        log.aprendizado(
            termo,
            {
                "entrada_id": entrada.id,
                "relacionado_a": termo_relacionado.termo,
                "modo": "sinonimo",
            },
        )
        return entrada

    significado_internet: Optional[str] = None
    resumo_internet: Optional[str] = None
    if usar_internet:
        falha_internet: Optional[str] = None
        try:
            definicao = consultar_definicao(termo)
        except (ConsultaInternetError, ValueError) as erro:
            definicao = None
            falha_internet = str(erro)
            log.aviso(
                "main",
                "aprender_termo",
                f"consulta online indisponível: {erro}",
                {"termo": termo},
            )
        if definicao is None:
            if falha_internet:
                print(
                    f"A pesquisa na internet falhou para '{termo}': "
                    f"{falha_internet}"
                )
            else:
                print(
                    f"A pesquisa na internet não encontrou uma definição "
                    f"para '{termo}'. Vou pedir os campos manualmente."
                )
        if definicao is not None:
            resumo = definicao.resumo[:700]
            pergunta_internet = (
                f"Encontrei uma definição pública para '{termo}' "
                f"na fonte {definicao.titulo}: {resumo}\n"
                "Posso usar esse significado como ponto de partida? [s/n] "
            )
            confirmar = _perguntar_com_cancelamento(
                perguntar,
                pergunta_internet,
                termo,
                "significado_internet",
                origem_resposta,
            )
            if _sim(confirmar):
                significado_internet = definicao.resumo
                resumo_internet = resumo
                log.acao(
                    "main",
                    "aprender_termo",
                    "sugestão pública aceita como significado provisório",
                    {"termo": termo, "fonte": definicao.url},
                )

    lacunas = identificar_lacunas(banco, termo, contexto)
    log.passo(
        "main",
        "aprender_termo",
        "lacunas identificadas",
        {"termo": termo, "lacunas": lacunas},
    )
    atual = existentes[0] if existentes else None
    respostas: dict[str, str] = {}
    if significado_internet is not None:
        lacunas = [campo for campo in lacunas if campo != "significado"]

    for campo in lacunas:
        respostas[campo] = _resposta_obrigatoria(
            perguntar,
            _gerar_pergunta_adaptativa(termo, campo),
            termo,
            campo,
            origem_resposta,
        )

    valores_propostos = {
        "tipo": respostas.get("tipo", atual.tipo if atual else None),
        "significado": respostas.get(
            "significado",
            atual.significado if atual else significado_internet,
        ),
        "contexto_uso": respostas.get(
            "contexto_uso",
            atual.contexto_uso if atual else contexto,
        ),
        "resposta_padrao": respostas.get(
            "resposta_padrao",
            atual.resposta_padrao if atual else None,
        ),
        "relacionados": atual.relacionados if atual else None,
        "exemplo_uso": respostas.get(
            "exemplo_uso",
            atual.exemplo_uso if atual else None,
        ),
    }
    proposta = _montar_proposta_termo(
        termo,
        atual,
        valores_propostos,
    )
    if not _confirmar_proposta(proposta, perguntar, origem_resposta):
        return None

    entrada = banco.salvar_termo(
        termo=termo,
        tipo=valores_propostos["tipo"],
        significado=valores_propostos["significado"],
        contexto_uso=valores_propostos["contexto_uso"],
        resposta_padrao=valores_propostos["resposta_padrao"],
        relacionados=valores_propostos["relacionados"],
        exemplo_uso=valores_propostos["exemplo_uso"],
        permissao=permissao_memoria,
    )
    log.aprendizado(
        termo,
        {
            "entrada_id": entrada.id,
            "campos_preenchidos": list(respostas),
            "tipo": entrada.tipo,
            "contexto": entrada.contexto_uso,
        },
    )
    if resumo_internet is not None and ao_aceitar_sugestao is not None:
        ao_aceitar_sugestao(resumo_internet)
    return entrada


def aprender_fato(
    afirmacao: str,
    banco: ConhecimentoDB,
    perguntar: RespostaUsuario = input,
    *,
    contexto: Optional[str] = None,
    corrigir_fato_id: Optional[int] = None,
    origem_resposta: str = "usuario",
    permissao_memoria: Optional[Permissao] = None,
) -> Optional[FatoConhecimento]:
    """Propõe um fato independente e só o grava após confirmação explícita."""
    afirmacao_limpa = " ".join(afirmacao.strip().split())
    if not afirmacao_limpa:
        raise ValueError("a afirmação do fato não pode ficar vazia")

    if contexto is None or not contexto.strip():
        contexto = _resposta_obrigatoria(
            perguntar,
            "Em que contexto este fato se aplica? ",
            afirmacao_limpa,
            "contexto_fato",
            origem_resposta,
        )
    contexto_limpo = " ".join(contexto.strip().split())
    if not contexto_limpo:
        raise ValueError("o contexto do fato não pode ficar vazio")

    fatos_contextuais = banco.buscar_fatos(contexto_limpo)
    atual: Optional[FatoConhecimento] = None
    if corrigir_fato_id is not None:
        atual = next(
            (
                fato
                for fato in fatos_contextuais
                if fato.id == corrigir_fato_id
            ),
            None,
        )
        if atual is None:
            raise LookupError(
                f"fato {corrigir_fato_id} não encontrado no contexto informado"
            )
    else:
        duplicado = banco.buscar_fato(afirmacao_limpa, contexto_limpo)
        if duplicado is not None:
            log.passo(
                "main",
                "aprender_fato",
                "fato já registrado; nenhuma gravação necessária",
                {"fato_id": duplicado.id, "contexto": contexto_limpo},
            )
            return duplicado

        if fatos_contextuais:
            opcoes = ["0. Registrar como um fato independente novo."]
            opcoes.extend(
                f"{indice}. Corrigir: {fato.afirmacao}"
                for indice, fato in enumerate(fatos_contextuais, start=1)
            )
            mensagem = (
                f"Já existem fatos no contexto '{contexto_limpo}': "
                + " | ".join(opcoes)
                + ". Escolha 0 para adicionar um fato ou o número do fato "
                "que deseja corrigir. "
            )
            while True:
                resposta = _resposta_obrigatoria(
                    perguntar,
                    mensagem,
                    afirmacao_limpa,
                    "selecao_fato",
                    origem_resposta,
                ).casefold()
                if resposta in {"0", "novo", "novo fato"}:
                    break
                try:
                    indice = int(resposta)
                except ValueError:
                    indice = -1
                if 1 <= indice <= len(fatos_contextuais):
                    atual = fatos_contextuais[indice - 1]
                    break
                if origem_resposta == "usuario":
                    print(
                        "Escolha 0 para um fato novo ou um dos números "
                        "listados."
                    )

    if atual is not None and any(
        fato.id != atual.id
        and fato.afirmacao.casefold() == afirmacao_limpa.casefold()
        for fato in fatos_contextuais
    ):
        log.aviso(
            "main",
            "aprender_fato",
            "correção não aplicada porque a afirmação já existe "
            "no mesmo contexto",
        )
        return None

    proposta = _montar_proposta_fato(
        afirmacao_limpa,
        contexto_limpo,
        atual,
    )
    if not _confirmar_proposta(
        proposta,
        perguntar,
        origem_resposta,
    ):
        return None

    fato = banco.salvar_fato(
        afirmacao_limpa,
        contexto_limpo,
        origem=origem_resposta,
        estado="confirmada",
        fato_id=atual.id if atual is not None else None,
        permissao=permissao_memoria,
    )
    log.aprendizado(
        afirmacao_limpa,
        {
            "fato_id": fato.id,
            "contexto": fato.contexto,
            "corrigido": atual is not None,
        },
    )
    return fato


def _responder_pergunta_direta(
    frase: str,
    banco: ConhecimentoDB,
    perguntar: RespostaUsuario,
    *,
    relacoes: Optional[RelacoesDB],
    projeto_dir: Path,
    origem_resposta: str,
    usar_internet: bool,
    modo_aprendizagem: bool,
    permissao_memoria: Optional[Permissao],
    permissao_relacao: Optional[Permissao],
    ao_aceitar_sugestao: Optional[Callable[[str], None]],
) -> Optional[list[str]]:
    """Responde ao campo solicitado, em vez de devolver a saudação do termo."""
    interpretacao = interpretar_pergunta(frase)
    if interpretacao is None:
        return None

    campo, termo = interpretacao
    log.passo(
        "main",
        "processar_frase",
        "pergunta direta identificada",
        {"campo": campo, "termo": termo},
    )
    entradas = buscar_conhecimento(banco, termo)
    if len(entradas) > 1 and not modo_aprendizagem:
        return [_mensagem_sentidos_ambiguos(termo, entradas)]

    entrada_completa = None
    aprendeu = False
    if len(entradas) > 1:
        entrada_completa = aprender_termo(
            termo,
            banco,
            perguntar,
            relacoes=relacoes,
            origem_resposta=origem_resposta,
            usar_internet=usar_internet,
            permissao_memoria=permissao_memoria,
            permissao_relacao=permissao_relacao,
            ao_aceitar_sugestao=ao_aceitar_sugestao,
        )
        aprendeu = False
    else:
        entrada_completa = next(
            (item for item in entradas if item.completa),
            None,
        )

    if entrada_completa is None:
        if not modo_aprendizagem:
            return [f"Ainda não sei o que significa '{termo}'."]
        entrada_completa = aprender_termo(
            termo,
            banco,
            perguntar,
            relacoes=relacoes,
            origem_resposta=origem_resposta,
            usar_internet=usar_internet,
            permissao_memoria=permissao_memoria,
            permissao_relacao=permissao_relacao,
            ao_aceitar_sugestao=ao_aceitar_sugestao,
        )
        aprendeu = True

    resposta = getattr(entrada_completa, campo)
    if resposta:
        return [resposta]
    return []


def _mensagem_termos_desconhecidos(
    frase: str,
    termos: list[str],
    banco: ConhecimentoDB,
) -> str:
    """Informa desconhecidos sem transformar conversa em entrevista."""

    partes = [
        f"Ainda não sei interpretar a frase '{frase}'.",
        "Não conheço: " + ", ".join(f"'{termo}'" for termo in termos) + ".",
    ]
    associacoes: list[str] = []
    for termo in termos:
        sugestoes = banco.sugerir_termos(termo, limite=2)
        if sugestoes:
            associacoes.append(
                f"{termo} parece próximo de "
                + ", ".join(f"'{sugestao}'" for sugestao in sugestoes)
            )
    if associacoes:
        partes.append(
            "Associações por proximidade de escrita: "
            + "; ".join(associacoes)
            + "."
        )
    return " ".join(partes)


def _mensagem_sentidos_ambiguos(
    termo: str,
    entradas: list[EntradaConhecimento],
) -> str:
    """Apresenta os sentidos encontrados sem escolher um silenciosamente."""
    opcoes = []
    for indice, entrada in enumerate(entradas, start=1):
        contexto = entrada.contexto_uso or "contexto não informado"
        significado = entrada.significado or "significado não informado"
        opcoes.append(f"{indice}. {contexto}: {significado}")
    return (
        f"Encontrei mais de um sentido para '{termo}': "
        + "; ".join(opcoes)
        + ". Qual contexto se aplica? Responda pelo número ou pelo contexto."
    )


def _buscar_sugestao_digitacao(
    frase: str,
    banco: ConhecimentoDB,
    entradas_confirmadas: list[EntradaConhecimento],
    grupos: list[tuple[str, list[EntradaConhecimento]]],
) -> Optional[tuple[str, tuple[str, ...]]]:
    """Busca uma aproximação conservadora sem escolher o candidato."""
    expressoes = [entrada.termo for entrada in entradas_confirmadas]
    tokens = tokenizar(frase, expressoes)

    if not grupos and tokens:
        candidatas_frase = banco.sugerir_termos(
            frase,
            limite=3,
            proporcao_minima=LIMIAR_SUGESTAO_DIGITACAO,
        )
        if candidatas_frase:
            return frase, tuple(candidatas_frase)

    desconhecidos: list[str] = []
    vistos: set[str] = set()
    for token in tokens:
        normalizado = _normalizar_unidade_textual(token)
        if (
            not normalizado
            or normalizado in PALAVRAS_FUNCIONAIS
            or eh_vocativo(normalizado)
            or normalizado in vistos
            or buscar_conhecimento_confirmado(banco, token)
        ):
            continue
        vistos.add(normalizado)
        desconhecidos.append(token)

    if len(desconhecidos) != 1:
        return None

    termo_digitado = desconhecidos[0]
    candidatas = banco.sugerir_termos(
        termo_digitado,
        limite=3,
        proporcao_minima=LIMIAR_SUGESTAO_DIGITACAO,
    )
    if not candidatas:
        return None
    return termo_digitado, tuple(candidatas)


def _mensagem_sugestao_digitacao(
    termo_digitado: str,
    candidatos: tuple[str, ...],
) -> str:
    if len(candidatos) == 1:
        return f"Você quis dizer '{candidatos[0]}'?"
    opcoes = "; ".join(
        f"{indice}. '{candidato}'"
        for indice, candidato in enumerate(candidatos, start=1)
    )
    return (
        f"Encontrei mais de um termo próximo de '{termo_digitado}': "
        f"{opcoes}. Qual deles você quis dizer? Responda pelo número "
        "ou pelo termo; use 0 se nenhum servir."
    )


def _interpretar_resposta_correcao(
    resposta: str,
    pendencia: CorrecaoDigitacaoPendente,
) -> tuple[str, Optional[str]]:
    """Retorna aceita, recusada, repetir ou nova para a pendência lexical."""
    texto = _normalizar_unidade_textual(resposta)
    if texto in {"nao", "nenhum", "nenhuma", "0", "cancelar"}:
        return "recusada", None

    if len(pendencia.candidatos) == 1:
        candidato = pendencia.candidatos[0]
        if texto in {"sim", "s", "isso", "correto"}:
            return "aceita", candidato
        if normalizar_termo_estrito(resposta) == normalizar_termo_estrito(
            candidato
        ):
            return "aceita", candidato
        return "nova", None

    indice = re.fullmatch(r"(?:opcao\s+)?(\d+)[.)]?", texto)
    if indice:
        numero = int(indice.group(1))
        if numero == 0:
            return "recusada", None
        if 1 <= numero <= len(pendencia.candidatos):
            return "aceita", pendencia.candidatos[numero - 1]
        return "repetir", None

    forma_estrita = normalizar_termo_estrito(resposta)
    for candidato in pendencia.candidatos:
        if forma_estrita == normalizar_termo_estrito(candidato):
            return "aceita", candidato
    return "repetir", None


def _substituir_trecho_digitado(
    frase: str,
    trecho_digitado: str,
    candidato: str,
) -> str:
    """Troca a aproximação confirmada e conserva a pontuação ao redor."""
    palavras = re.findall(r"\w+", trecho_digitado, flags=re.UNICODE)
    if not palavras:
        return frase
    padrao = r"(?<!\w)" + r"\W+".join(map(re.escape, palavras)) + r"(?!\w)"
    return re.sub(
        padrao,
        lambda _match: candidato,
        frase,
        count=1,
        flags=re.IGNORECASE | re.UNICODE,
    )


def _palavras_de_conteudo(texto: str) -> set[str]:
    palavras_meta = {
        "significa",
        "significado",
        "definicao",
        "definição",
        "explique",
        "explica",
        "conte",
        "sobre",
        "contexto",
        "sentido",
        "termo",
        "palavra",
        "informacao",
        "informação",
        "fato",
        "fatos",
    }
    return {
        palavra
        for palavra in _normalizar_unidade_textual(texto).split()
        if len(palavra) > 1
        and palavra not in PALAVRAS_FUNCIONAIS
        and palavra not in palavras_meta
        and not eh_vocativo(palavra)
    }


def _texto_contexto_recente(
    contexto: Optional[ContextoConversa],
) -> str:
    if contexto is None:
        return ""
    partes = [
        contexto.topico_atual or "",
        *contexto.turnos_recentes[-3:],
        *(
            mencao.forma_normalizada
            for mencao in contexto.entidades_ativas[-8:]
        ),
    ]
    return " ".join(parte for parte in partes if parte)


def _grupos_de_sentidos(
    frase: str,
    entradas_confirmadas: list[EntradaConhecimento],
) -> list[tuple[str, list[EntradaConhecimento]]]:
    por_termo: dict[str, list[EntradaConhecimento]] = {}
    for entrada in entradas_confirmadas:
        chave = _normalizar_unidade_textual(entrada.termo)
        por_termo.setdefault(chave, []).append(entrada)

    unidades = tokenizar(frase, [entrada.termo for entrada in entradas_confirmadas])
    grupos: list[tuple[str, list[EntradaConhecimento]]] = []
    vistos: set[str] = set()
    for unidade in unidades:
        chave = _normalizar_unidade_textual(unidade)
        if (
            not chave
            or chave in vistos
            or chave in PALAVRAS_FUNCIONAIS
            or eh_vocativo(chave)
        ):
            continue
        encontrados = por_termo.get(chave, [])
        if encontrados:
            grupos.append((encontrados[0].termo, encontrados))
            vistos.add(chave)
    return grupos


def _selecionar_sentido_com_contexto(
    termo: str,
    entradas: list[EntradaConhecimento],
    pistas_da_frase: set[str],
    pistas_recentes: set[str],
) -> tuple[Optional[EntradaConhecimento], bool]:
    if len(entradas) == 1:
        return entradas[0], False

    palavras_termo = _palavras_de_conteudo(termo)
    pistas_frase = pistas_da_frase - palavras_termo
    pistas_contexto = pistas_recentes - palavras_termo
    pontuacoes: list[tuple[int, EntradaConhecimento]] = []
    for entrada in entradas:
        palavras_contexto = _palavras_de_conteudo(
            entrada.contexto_uso or ""
        )
        pontos = (
            3 * len(palavras_contexto & pistas_frase)
            + len(palavras_contexto & pistas_contexto)
        )
        pontuacoes.append((pontos, entrada))

    maior = max(pontos for pontos, _entrada in pontuacoes)
    melhores = [
        entrada for pontos, entrada in pontuacoes if pontos == maior
    ]
    if maior > 0 and len(melhores) == 1:
        return melhores[0], False
    return None, True


def _frase_parece_seguimento(frase: str, palavras: set[str]) -> bool:
    normalizada = _normalizar_unidade_textual(frase)
    return (
        normalizada.startswith("e ")
        or normalizada.startswith(
            ("ele ", "ela ", "eles ", "elas ", "isso ", "isto ", "aquilo ")
        )
        or (
            len(palavras) <= 2
            and normalizada.startswith(("onde ", "qual ", "quando ", "por que "))
        )
    )


def _remover_vocativo_inicial(frase: str) -> str:
    palavras = _normalizar_unidade_textual(frase).split()
    while len(palavras) > 1 and eh_vocativo(palavras[0]):
        palavras.pop(0)
    return " ".join(palavras)


def _pontuar_fato(
    fato: FatoConhecimento,
    palavras_da_frase: set[str],
    palavras_recentes: set[str],
    *,
    seguimento: bool,
) -> int:
    palavras_afirmacao = _palavras_de_conteudo(fato.afirmacao)
    palavras_contexto = _palavras_de_conteudo(fato.contexto)
    diretas = palavras_da_frase & palavras_afirmacao
    contexto_explicito = palavras_da_frase & palavras_contexto
    recentes_na_afirmacao = palavras_recentes & palavras_afirmacao
    recentes_no_contexto = palavras_recentes & palavras_contexto

    if diretas:
        return (
            4 * len(diretas)
            + 2 * len(contexto_explicito)
            + (len(recentes_na_afirmacao) if seguimento else 0)
        )
    if contexto_explicito:
        return 2 * len(contexto_explicito)
    if seguimento and (recentes_na_afirmacao or recentes_no_contexto):
        return 2 * len(recentes_na_afirmacao) + len(recentes_no_contexto)
    return 0


def _buscar_fatos_relevantes(
    frase: str,
    banco: ConhecimentoDB,
    contexto: Optional[ContextoConversa],
) -> list[FatoConhecimento]:
    palavras_da_frase = _palavras_de_conteudo(frase)
    palavras_recentes = _palavras_de_conteudo(
        _texto_contexto_recente(contexto)
    )
    seguimento = _frase_parece_seguimento(frase, palavras_da_frase)
    pontuados = [
        (
            _pontuar_fato(
                fato,
                palavras_da_frase,
                palavras_recentes,
                seguimento=seguimento,
            ),
            fato,
        )
        for fato in buscar_fatos_confirmados(banco)
    ]
    relevantes = [
        (pontos, fato)
        for pontos, fato in pontuados
        if pontos > 0
    ]
    relevantes.sort(key=lambda item: (-item[0], item[1].id))
    return [fato for _pontos, fato in relevantes[:5]]


def _buscar_relacoes_relevantes(
    entradas: list[EntradaConhecimento],
    banco: ConhecimentoDB,
    relacoes: Optional[RelacoesDB],
) -> list[EntradaConhecimento]:
    if relacoes is None or not entradas:
        return []
    resultado: list[EntradaConhecimento] = []
    vistos: set[int] = set()
    for entrada in entradas:
        for relacionado_id in relacoes.listar_ids(entrada.id):
            if relacionado_id in vistos:
                continue
            relacionado = buscar_conhecimento_por_id_confirmado(
                banco,
                relacionado_id,
            )
            if relacionado is None:
                continue
            resultado.append(relacionado)
            vistos.add(relacionado_id)
    return resultado


def _compor_resposta_dinamica(
    entradas: list[EntradaConhecimento],
    fatos: list[FatoConhecimento],
    relacionadas: list[EntradaConhecimento],
) -> Optional[str]:
    partes: list[str] = []
    for entrada in entradas:
        informacoes = []
        if entrada.tipo:
            informacoes.append(f"categoria: {entrada.tipo}")
        if entrada.significado:
            informacoes.append(entrada.significado)
        if entrada.contexto_uso:
            informacoes.append(
                f"contexto de uso: {entrada.contexto_uso}"
            )
        if entrada.exemplo_uso:
            informacoes.append(f"exemplo: {entrada.exemplo_uso}")
        if informacoes:
            partes.append(f"{entrada.termo}: " + "; ".join(informacoes))

    partes.extend(
        f"{fato.afirmacao} (contexto: {fato.contexto})"
        for fato in fatos
    )
    if relacionadas:
        partes.append(
            "Relações registradas: "
            + ", ".join(entrada.termo for entrada in relacionadas)
        )
    return "; ".join(partes) if partes else None


def _responder_campo_confirmado(
    entrada: EntradaConhecimento,
    campo: str,
) -> str:
    if campo != "resposta_padrao":
        valor = getattr(entrada, campo, None)
        if valor:
            return valor
    composicao = _compor_resposta_dinamica([entrada], [], [])
    if composicao:
        return composicao
    return (
        f"Ainda não tenho informação confirmada suficiente sobre "
        f"'{entrada.termo}'."
    )


def _mencao_da_entrada(
    entrada: EntradaConhecimento,
    posicao: int = 0,
) -> Mencao:
    tipo = entrada.tipo.casefold() if entrada.tipo else None
    return Mencao(
        texto_original=entrada.termo,
        forma_normalizada=_normalizar_unidade_textual(entrada.termo),
        tipo_lexical_conhecido=tipo,
        numero_e_genero=_inferir_numero_e_genero(entrada.termo, tipo),
        posicao_na_frase=posicao,
        eh_sujeito=posicao == 0,
    )


def _tentar_resolver_desambiguacao(
    frase: str,
    pendencia: DesambiguacaoPendente,
    banco: ConhecimentoDB,
) -> tuple[Optional[EntradaConhecimento], list[EntradaConhecimento]]:
    entradas = [
        entrada
        for candidato_id in pendencia.candidato_ids
        if (
            entrada := buscar_conhecimento_por_id_confirmado(
                banco,
                candidato_id,
            )
        )
        is not None
    ]
    if not entradas:
        return None, []

    resposta = frase.strip()
    numero = re.fullmatch(r"(\d+)[.)]?", resposta)
    if numero:
        indice = int(numero.group(1)) - 1
        if 0 <= indice < len(entradas):
            return entradas[indice], entradas
        return None, entradas

    pistas = _palavras_de_conteudo(resposta)
    pontuacoes = [
        (
            len(pistas & _palavras_de_conteudo(entrada.contexto_uso or "")),
            entrada,
        )
        for entrada in entradas
    ]
    maior = max(pontos for pontos, _entrada in pontuacoes)
    melhores = [
        entrada for pontos, entrada in pontuacoes if pontos == maior
    ]
    if maior > 0 and len(melhores) == 1:
        return melhores[0], entradas
    return None, entradas


def _responder_esclarecimento_pendente(
    frase: str,
    banco: ConhecimentoDB,
    contexto: ContextoConversa,
    frase_normalizada: str,
) -> list[str]:
    pendencia = contexto.desambiguacao_pendente
    if pendencia is None:
        return []
    entrada, opcoes = _tentar_resolver_desambiguacao(
        frase,
        pendencia,
        banco,
    )
    if entrada is None:
        if not opcoes:
            contexto.desambiguacao_pendente = None
            mensagem = (
                "Os sentidos que estavam aguardando esclarecimento não "
                "estão mais disponíveis com informações confirmadas."
            )
        else:
            mensagem = (
                "Não consegui relacionar essa resposta a um dos contextos. "
                "Escolha um dos números ou informe o contexto mostrado: "
                + "; ".join(
                    f"{indice}. {opcao.contexto_uso or 'contexto não informado'}"
                    for indice, opcao in enumerate(opcoes, start=1)
                )
                + "."
            )
        contexto.registrar_turno(frase_normalizada)
        return [mensagem]

    contexto.desambiguacao_pendente = None
    if pendencia.campo:
        resposta = _responder_campo_confirmado(entrada, pendencia.campo)
    else:
        resposta = _compor_resposta_dinamica([entrada], [], [])
        if resposta is None:
            resposta = (
                f"Ainda não tenho informação confirmada suficiente sobre "
                f"'{entrada.termo}'."
            )
    return _finalizar_com_contexto(
        [resposta],
        contexto=contexto,
        frase_normalizada=frase_normalizada,
        banco=banco,
        topico=entrada.termo,
        mencoes=[_mencao_da_entrada(entrada)],
    )


def _parece_nova_pergunta(frase: str) -> bool:
    if "?" not in frase:
        return False
    normalizada = _normalizar_unidade_textual(frase)
    return normalizada.startswith(
        (
            "o que ",
            "qual ",
            "quem ",
            "onde ",
            "quando ",
            "como ",
            "por que ",
        )
    )


def _extrair_nome_apresentado(frase: str) -> Optional[str]:
    """Extrai nome informado explicitamente durante a conversa atual."""
    correspondencia = re.search(
        r"(?:^|[.!?]\s*)(?:meu\s+nome\s+(?:é|e)|me\s+chamo|eu\s+me\s+chamo|"
        r"eu\s+sou|sou)\s+"
        r"([\wÀ-ÿ]+(?:[ '\u2019-][\wÀ-ÿ]+){0,2})"
        r"(?=\s*[.!?,;]|$)",
        frase,
        flags=re.IGNORECASE | re.UNICODE,
    )
    if correspondencia is None:
        return None
    nome = " ".join(correspondencia.group(1).split())
    if not nome or any(
        len(palavra) == 1 and palavra.casefold() in {"e", "o", "a"}
        for palavra in nome.split()
    ):
        return None
    return nome


def _responder_intencao_conversa(
    frase: str,
    frase_original: str,
    contexto: Optional[ContextoConversa],
) -> Optional[list[str]]:
    """Responde intenções sociais sem depender de fichas aprendidas."""
    intencao = rotear(frase).intencao
    normalizada = _normalizar_unidade_textual(frase)

    if intencao == Intencao.RESPONDER_SAUDACAO:
        if "bom dia" in normalizada:
            return ["Olá! Bom dia! Como posso ajudar?"]
        if "boa tarde" in normalizada:
            return ["Olá! Boa tarde! Como posso ajudar?"]
        if "boa noite" in normalizada:
            return ["Olá! Boa noite! Como posso ajudar?"]
        return ["Olá! Como posso ajudar?"]

    if intencao == Intencao.PERGUNTAR_ESTADO_SOCIAL:
        return ["Tudo certo por aqui. Obrigada por perguntar! E você?"]

    if intencao == Intencao.PERGUNTAR_NOME:
        nome = _extrair_nome_apresentado(frase_original)
        if nome and contexto is not None:
            contexto.nome_interlocutor = nome
            contexto.pergunta_pendente = None
        elif contexto is not None and not contexto.nome_interlocutor:
            contexto.pergunta_pendente = "nome_interlocutor"
        if nome:
            return [f"Meu nome é Isana. Prazer, {nome}."]
        if contexto is not None and contexto.nome_interlocutor:
            return ["Meu nome é Isana."]
        return ["Meu nome é Isana. E o seu?"]

    if intencao == Intencao.DESPEDIDA:
        return ["Até logo!"]

    return None


def _extrair_nome_resposta_pendente(
    frase_original: str,
    frase_normalizada: str,
    banco: ConhecimentoDB,
) -> Optional[str]:
    """Interpreta uma resposta curta como nome apenas após pedido de nome."""
    if re.search(r"[?!]", frase_original):
        return None
    correspondencia = re.fullmatch(
        r"\s*([\wÀ-ÿ]+(?:[ '\u2019-][\wÀ-ÿ]+){0,2})\s*[.,!]?\s*",
        frase_original,
        flags=re.UNICODE,
    )
    if correspondencia is None:
        return None
    nome = " ".join(correspondencia.group(1).split())
    if _normalizar_unidade_textual(nome) in {
        "sim",
        "nao",
        "não",
        "ok",
        "claro",
        "nao sei",
        "não sei",
    }:
        return None
    palavras_nome = nome.split()
    particulas_de_nome = {"da", "das", "de", "do", "dos", "e"}
    if len(palavras_nome) > 1 and any(
        not palavra[:1].isupper()
        and palavra.casefold() not in particulas_de_nome
        for palavra in palavras_nome
    ):
        return None
    entradas = [
        entrada
        for entrada in listar_conhecimento_confirmado(banco)
        if entrada.tipo
        or entrada.significado
        or entrada.contexto_uso
        or entrada.exemplo_uso
    ]
    if _grupos_de_sentidos(frase_normalizada, entradas):
        return None
    return nome


def _resposta_aguarda_nome(frase: str, resposta: str) -> bool:
    frase_normalizada = _normalizar_unidade_textual(frase)
    resposta_normalizada = _normalizar_unidade_textual(resposta)
    if "nome" in frase_normalizada.split():
        return bool(
            re.search(r"\be o seu(?: nome)?\s*[.!?]?$", resposta_normalizada)
            or re.search(r"\bqual (?:e )?o seu nome\b", resposta_normalizada)
        )
    return bool(
        re.search(r"\bqual (?:e )?o seu nome\b", resposta_normalizada)
    )


def _responder_conversa_contextual(
    frase: str,
    banco: ConhecimentoDB,
    *,
    relacoes: Optional[RelacoesDB],
    contexto: Optional[ContextoConversa],
    frase_normalizada: str,
    frase_original: str,
) -> list[str]:
    """Recupera e compõe somente conhecimento confirmado e contextual."""
    entradas_confirmadas = [
        entrada
        for entrada in listar_conhecimento_confirmado(banco)
        if entrada.tipo
        or entrada.significado
        or entrada.contexto_uso
        or entrada.exemplo_uso
    ]
    grupos = _grupos_de_sentidos(frase, entradas_confirmadas)
    if contexto is not None:
        sugestao = _buscar_sugestao_digitacao(
            frase,
            banco,
            entradas_confirmadas,
            grupos,
        )
        if sugestao is not None:
            trecho_digitado, candidatos = sugestao
            contexto.correcao_digitacao_pendente = CorrecaoDigitacaoPendente(
                frase_original=frase_original,
                trecho_digitado=trecho_digitado,
                candidatos=candidatos,
            )
            contexto.desambiguacao_pendente = None
            contexto.pergunta_pendente = None
            return _finalizar_com_contexto(
                [_mensagem_sugestao_digitacao(trecho_digitado, candidatos)],
                contexto=contexto,
                frase_normalizada=frase_normalizada,
                banco=banco,
            )
    interpretacao = interpretar_pergunta(frase)
    campo_solicitado = interpretacao[0] if interpretacao else None
    termo_solicitado = interpretacao[1] if interpretacao else None

    grupos_alvo = grupos
    if campo_solicitado and termo_solicitado:
        alvo_normalizado = _normalizar_unidade_textual(termo_solicitado)
        grupo_exato = next(
            (
                grupo
                for grupo in grupos
                if _normalizar_unidade_textual(grupo[0]) == alvo_normalizado
            ),
            None,
        )
        if grupo_exato is None:
            palavras_alvo = _palavras_de_conteudo(termo_solicitado)
            grupo_exato = next(
                (
                    grupo
                    for grupo in grupos
                    if _palavras_de_conteudo(grupo[0]) & palavras_alvo
                ),
                None,
            )
        grupos_alvo = [grupo_exato] if grupo_exato else []

    texto_recente = _texto_contexto_recente(contexto)
    pistas_da_frase = _palavras_de_conteudo(frase)
    seguimento = _frase_parece_seguimento(frase, pistas_da_frase)
    pistas_recentes = (
        _palavras_de_conteudo(texto_recente)
        if seguimento
        else set()
    )

    if (
        not grupos_alvo
        and not campo_solicitado
        and contexto is not None
        and seguimento
    ):
        termo_ativo = contexto.topico_atual
        if termo_ativo:
            grupo_ativo = next(
                (
                    entrada
                    for entrada in entradas_confirmadas
                    if _normalizar_unidade_textual(entrada.termo)
                    == _normalizar_unidade_textual(termo_ativo)
                ),
                None,
            )
            if grupo_ativo is not None:
                grupos_alvo = [(grupo_ativo.termo, [grupo_ativo])]
        if not grupos_alvo and contexto.entidades_ativas:
            mencao_ativa = max(
                contexto.entidades_ativas,
                key=lambda mencao: (
                    mencao.turno_em_que_apareceu,
                    mencao.eh_sujeito,
                ),
            )
            entrada_ativa = next(
                (
                    entrada
                    for entrada in entradas_confirmadas
                    if _normalizar_unidade_textual(entrada.termo)
                    == mencao_ativa.forma_normalizada
                ),
                None,
            )
            if entrada_ativa is not None:
                grupos_alvo = [(entrada_ativa.termo, [entrada_ativa])]

    selecionadas: list[EntradaConhecimento] = []
    for termo, opcoes in grupos_alvo:
        entrada, ambigua = _selecionar_sentido_com_contexto(
            termo,
            opcoes,
            pistas_da_frase,
            pistas_recentes,
        )
        if ambigua:
            if contexto is not None:
                contexto.desambiguacao_pendente = DesambiguacaoPendente(
                    consulta=frase,
                    termo=termo,
                    campo=campo_solicitado,
                    candidato_ids=tuple(opcao.id for opcao in opcoes),
                )
                contexto.registrar_turno(frase_normalizada)
            return [_mensagem_sentidos_ambiguos(termo, opcoes)]
        if entrada is not None:
            selecionadas.append(entrada)

    if campo_solicitado:
        if selecionadas:
            resposta = _compor_resposta_explicativa(selecionadas[0])
            if resposta is None:
                resposta = _responder_campo_confirmado(
                    selecionadas[0],
                    campo_solicitado,
                )
        else:
            alvo = termo_solicitado or frase
            resposta = (
                f"Ainda não sei o campo solicitado sobre '{alvo}' com "
                "informação confirmada."
            )
        return _finalizar_com_contexto(
            [resposta],
            contexto=contexto,
            frase_normalizada=frase,
            banco=banco,
            topico=selecionadas[0].termo if selecionadas else None,
            mencoes=(
                [_mencao_da_entrada(selecionadas[0])]
                if selecionadas
                else []
            ),
        )

    unidades_frase = tokenizar(
        frase,
        [entrada.termo for entrada in entradas_confirmadas],
    )
    if len(selecionadas) > 1 and unidades_frase:
        primeira_unidade = _normalizar_unidade_textual(unidades_frase[0])
        saudacao_confirmada = next(
            (
                entrada
                for entrada in selecionadas
                if _normalizar_unidade_textual(entrada.termo)
                == primeira_unidade
            ),
            None,
        )
        if (
            saudacao_confirmada is not None
            and rotear(unidades_frase[0]).intencao
            == Intencao.RESPONDER_SAUDACAO
        ):
            resposta_social = _responder_intencao_conversa(
                unidades_frase[0],
                frase_original,
                contexto,
            )
            if resposta_social is not None:
                return _finalizar_com_contexto(
                    resposta_social,
                    contexto=contexto,
                    frase_normalizada=frase_normalizada,
                    banco=banco,
                    topico=saudacao_confirmada.termo,
                    mencoes=[_mencao_da_entrada(saudacao_confirmada)],
                )

    fatos = _buscar_fatos_relevantes(frase, banco, contexto)
    relacionadas = _buscar_relacoes_relevantes(
        selecionadas,
        banco,
        relacoes,
    )
    frase_conversacional = _remover_vocativo_inicial(frase)
    if (
        len(selecionadas) == 1
        and _entrada_eh_conversacional(
            frase_conversacional,
            selecionadas[0],
            EXPRESSOES_CONVERSACIONAIS,
        )
    ):
        resposta = _compor_resposta_conversacional(
            selecionadas[0],
            contexto.nome_interlocutor if contexto is not None else None,
        )
        if resposta is None:
            resposta = "Entendi."
        if (
            contexto is not None
            and _resposta_aguarda_nome(frase, resposta)
        ):
            contexto.pergunta_pendente = "nome_interlocutor"
    else:
        consulta_de_termo_unico = (
            len(selecionadas) == 1
            and len(pistas_da_frase) == 1
            and _normalizar_unidade_textual(frase)
            == _normalizar_unidade_textual(selecionadas[0].termo)
        )
        if fatos or relacionadas:
            resposta = _compor_resposta_dinamica(
                [],
                fatos,
                relacionadas,
            )
        elif consulta_de_termo_unico:
            resposta = _compor_resposta_dinamica(
                selecionadas,
                [],
                [],
            )
        else:
            resposta = None
    if resposta is None:
        resposta = (
            f"Ainda não sei responder a '{frase}' com o conhecimento "
            "confirmado que está disponível."
        )
    return _finalizar_com_contexto(
        [resposta],
        contexto=contexto,
        frase_normalizada=frase,
        banco=banco,
        topico=selecionadas[0].termo if selecionadas else None,
        mencoes=(
            [
                _mencao_da_entrada(entrada, indice)
                for indice, entrada in enumerate(selecionadas)
            ]
            if selecionadas
            else None
        ),
    )


def _mensagem_ambiguidade_de_pronome(
    resolucao: object,
) -> str:
    """Pede esclarecimento sem escolher uma referência arbitrariamente."""
    pronome = getattr(resolucao, "pronome", "essa referência")
    candidatos = getattr(resolucao, "candidatos", ())
    nomes = []
    vistos: set[str] = set()
    for mencao in candidatos:
        nome = mencao.forma_normalizada
        if nome not in vistos:
            vistos.add(nome)
            nomes.append(f"'{nome}'")
    if nomes:
        opcoes = ", ".join(nomes)
        return (
            f"Não consegui identificar a quem '{pronome}' se refere. "
            f"Você quer dizer {opcoes}?"
        )
    return (
        f"Não consegui identificar a quem '{pronome}' se refere. "
        "Pode esclarecer?"
    )


def _finalizar_com_contexto(
    respostas: list[str],
    *,
    contexto: Optional[ContextoConversa],
    frase_normalizada: str,
    banco: ConhecimentoDB,
    topico: Optional[str] = None,
    mencoes: Optional[list[Mencao]] = None,
) -> list[str]:
    if contexto is not None:
        contexto.registrar_turno(
            frase_normalizada,
            (
                mencoes
                if mencoes is not None
                else _extrair_mencoes_contexto(frase_normalizada, banco)
            ),
            topico=topico,
        )
    return respostas


def processar_frase(
    frase: str,
    banco: ConhecimentoDB,
    perguntar: RespostaUsuario = input,
    *,
    relacoes: Optional[RelacoesDB] = None,
    projeto_dir: Path = BASE_DIR,
    origem_resposta: str = "usuario",
    usar_internet: bool = False,
    modo_aprendizagem: bool = True,
    permissao_memoria: Optional[Permissao] = None,
    permissao_relacao: Optional[Permissao] = None,
    contexto: Optional[ContextoConversa] = None,
    propostas: Optional[PropostasAprendizagem] = None,
    ao_aceitar_sugestao: Optional[Callable[[str], None]] = None,
) -> list[str]:
    """Consulta frases ou aprende o assunto informado conforme o modo."""

    frase_original = frase
    try:
        resposta_proposta = _processar_comando_proposta(
            frase_original,
            banco,
            perguntar,
            propostas=propostas,
            modo_aprendizagem=modo_aprendizagem,
            permissao_memoria=permissao_memoria,
        )
    except AprendizagemCancelada:
        return ["Proposta cancelada; nenhum conteúdo foi alterado."]
    if resposta_proposta is not None:
        if contexto is not None:
            contexto.pergunta_pendente = None
        return resposta_proposta

    frase_normalizada = normalizar_frase(frase)
    frase = frase_normalizada
    if contexto is not None:
        resolucao = contexto.resolver_frase(frase_normalizada)
        if resolucao.ambiguidades:
            contexto.registrar_turno(frase_normalizada)
            return [
                _mensagem_ambiguidade_de_pronome(
                    resolucao.ambiguidades[0],
                )
            ]
        frase = resolucao.frase_resolvida
    log.passo(
        "main",
        "processar_frase",
        "entrada normalizada",
        {
            "frase_original": frase_original,
            "frase_normalizada": frase_normalizada,
            "frase_resolvida": frase,
        },
    )

    if (
        not modo_aprendizagem
        and contexto is not None
        and contexto.correcao_digitacao_pendente is not None
    ):
        pendencia = contexto.correcao_digitacao_pendente
        estado, candidato = _interpretar_resposta_correcao(
            frase_original,
            pendencia,
        )
        if estado == "aceita" and candidato is not None:
            contexto.correcao_digitacao_pendente = None
            frase_corrigida = _substituir_trecho_digitado(
                pendencia.frase_original,
                pendencia.trecho_digitado,
                candidato,
            )
            if frase_corrigida == pendencia.frase_original:
                return _finalizar_com_contexto(
                    [
                        "Não consegui aplicar a correção confirmada. "
                        "Envie a frase novamente."
                    ],
                    contexto=contexto,
                    frase_normalizada=frase_normalizada,
                    banco=banco,
                )
            return processar_frase(
                frase_corrigida,
                banco,
                perguntar,
                relacoes=relacoes,
                projeto_dir=projeto_dir,
                origem_resposta=origem_resposta,
                usar_internet=usar_internet,
                modo_aprendizagem=modo_aprendizagem,
                permissao_memoria=permissao_memoria,
                permissao_relacao=permissao_relacao,
                contexto=contexto,
                propostas=propostas,
                ao_aceitar_sugestao=ao_aceitar_sugestao,
            )
        if estado == "recusada":
            contexto.correcao_digitacao_pendente = None
            return _finalizar_com_contexto(
                [
                    f"Entendi. Não vou substituir "
                    f"'{pendencia.trecho_digitado}' por nenhum termo."
                ],
                contexto=contexto,
                frase_normalizada=frase_normalizada,
                banco=banco,
            )
        if estado == "repetir":
            return _finalizar_com_contexto(
                [
                    "Escolha um dos candidatos numerados ou responda 0 "
                    "se nenhum servir."
                ],
                contexto=contexto,
                frase_normalizada=frase_normalizada,
                banco=banco,
            )
        contexto.correcao_digitacao_pendente = None

    comando_explicito = re.fullmatch(
        r"(termo|fato)\s*:(.*)",
        frase_original.strip(),
        flags=re.DOTALL | re.IGNORECASE,
    )
    if comando_explicito:
        if contexto is not None:
            contexto.desambiguacao_pendente = None
            contexto.pergunta_pendente = None
        tipo_comando = comando_explicito.group(1).casefold()
        conteudo = comando_explicito.group(2).strip()
        if not modo_aprendizagem:
            return _finalizar_com_contexto(
                [
                    "O registro explícito de conhecimento só está "
                    "disponível no modo aprendizagem."
                ],
                contexto=contexto,
                frase_normalizada=frase_normalizada,
                banco=banco,
            )
        if not conteudo:
            return [
                f"Informe o conteúdo após '{tipo_comando}:'. "
                f"Exemplo: {tipo_comando}: conteúdo a aprender."
            ]
        try:
            if tipo_comando == "termo":
                entrada = aprender_termo(
                    conteudo,
                    banco,
                    perguntar,
                    relacoes=relacoes,
                    origem_resposta=origem_resposta,
                    usar_internet=usar_internet,
                    permissao_memoria=permissao_memoria,
                    permissao_relacao=permissao_relacao,
                    ao_aceitar_sugestao=ao_aceitar_sugestao,
                )
                if entrada is None:
                    return [
                        "A proposta não foi confirmada. Nenhum termo novo "
                        "foi gravado."
                    ]
                return [f"Termo registrado: '{entrada.termo}'."]

            fato = aprender_fato(
                conteudo,
                banco,
                perguntar,
                origem_resposta=origem_resposta,
                permissao_memoria=permissao_memoria,
            )
        except AprendizagemCancelada:
            mensagem = (
                "Aprendizagem cancelada. A informação incompleta desta "
                "etapa não foi gravada."
            )
            return [mensagem]
        if fato is None:
            return [
                "A proposta não foi confirmada. Nenhum fato novo ou correção "
                "foi gravado."
            ]
        return [
            f"Fato registrado: '{fato.afirmacao}' "
            f"(contexto: '{fato.contexto}')."
        ]

    if not modo_aprendizagem:
        resposta_social = _responder_intencao_conversa(
            frase,
            frase_original,
            contexto,
        )
        if resposta_social is not None:
            if rotear(frase).intencao == Intencao.RESPONDER_SAUDACAO:
                entradas_saudacao = buscar_conhecimento_confirmado(
                    banco,
                    frase,
                )
                if (
                    len(entradas_saudacao) == 1
                    and _entrada_eh_conversacional(
                        frase,
                        entradas_saudacao[0],
                        EXPRESSOES_CONVERSACIONAIS,
                    )
                ):
                    resposta_confirmada = _compor_resposta_conversacional(
                        entradas_saudacao[0],
                        (
                            contexto.nome_interlocutor
                            if contexto is not None
                            else None
                        ),
                    )
                    if resposta_confirmada is not None:
                        resposta_social = [resposta_confirmada]
            if contexto is not None:
                contexto.desambiguacao_pendente = None
                if rotear(frase).intencao != Intencao.PERGUNTAR_NOME:
                    contexto.pergunta_pendente = None
            return _finalizar_com_contexto(
                resposta_social,
                contexto=contexto,
                frase_normalizada=frase_normalizada,
                banco=banco,
            )

    resposta_ferramenta = _responder_ferramenta(frase)
    if resposta_ferramenta is not None:
        if contexto is not None:
            contexto.desambiguacao_pendente = None
            contexto.pergunta_pendente = None
        return _finalizar_com_contexto(
            resposta_ferramenta,
            contexto=contexto,
            frase_normalizada=frase_normalizada,
            banco=banco,
        )

    if not modo_aprendizagem and contexto is not None:
        nome_apresentado = _extrair_nome_apresentado(frase_original)
        if nome_apresentado is not None:
            contexto.nome_interlocutor = nome_apresentado
            contexto.pergunta_pendente = None
            return _finalizar_com_contexto(
                [f"Prazer, {nome_apresentado}."],
                contexto=contexto,
                frase_normalizada=frase_normalizada,
                banco=banco,
                mencoes=[],
            )

        if contexto.pergunta_pendente == "nome_interlocutor":
            nome_resposta = _extrair_nome_resposta_pendente(
                frase_original,
                frase_normalizada,
                banco,
            )
            contexto.pergunta_pendente = None
            if nome_resposta is not None:
                contexto.nome_interlocutor = nome_resposta
                return _finalizar_com_contexto(
                    [f"Prazer em conhecer, {nome_resposta}."],
                    contexto=contexto,
                    frase_normalizada=frase_normalizada,
                    banco=banco,
                    mencoes=[],
                )

    if contexto is not None and contexto.desambiguacao_pendente is not None:
        if _parece_nova_pergunta(frase):
            contexto.desambiguacao_pendente = None
        else:
            return _responder_esclarecimento_pendente(
                frase,
                banco,
                contexto,
                frase_normalizada,
            )

    if not modo_aprendizagem:
        return _responder_conversa_contextual(
            frase,
            banco,
            relacoes=relacoes,
            contexto=contexto,
            frase_normalizada=frase_normalizada,
            frase_original=frase_original,
        )

    try:
        resposta_pergunta = _responder_pergunta_direta(
            frase,
            banco,
            perguntar,
            relacoes=relacoes,
            projeto_dir=projeto_dir,
            origem_resposta=origem_resposta,
            usar_internet=usar_internet,
            modo_aprendizagem=modo_aprendizagem,
            permissao_memoria=permissao_memoria,
            permissao_relacao=permissao_relacao,
            ao_aceitar_sugestao=ao_aceitar_sugestao,
        )
    except AprendizagemCancelada:
        return [
            "Aprendizagem cancelada. A etapa em andamento não foi gravada."
        ]
    if resposta_pergunta is not None:
        return _finalizar_com_contexto(
            resposta_pergunta,
            contexto=contexto,
            frase_normalizada=frase_normalizada,
            banco=banco,
        )

    tokens = tokenizar(frase, banco.listar_expressoes_compostas())
    log.passo(
        "main",
        "processar_frase",
        "frase tokenizada",
        {"frase": frase, "tokens": tokens},
    )
    if modo_aprendizagem and _entrada_de_aprendizagem_sem_assunto(
        frase,
        tokens,
    ):
        log.passo(
            "main",
            "processar_frase",
            "entrada sem assunto claro; aprendizagem não iniciada",
            {"frase": frase, "tokens": tokens},
        )
        return _finalizar_com_contexto(
            [_mensagem_sem_assunto_de_aprendizagem()],
            contexto=contexto,
            frase_normalizada=frase_normalizada,
            banco=banco,
        )

    if modo_aprendizagem and len(tokens) > 1:
        log.passo(
            "main",
            "processar_frase",
            "usando a entrada completa como assunto de aprendizagem",
            {"assunto": frase, "tokens": tokens},
        )
        try:
            entrada_completa = aprender_termo(
                frase,
                banco,
                perguntar,
                relacoes=relacoes,
                origem_resposta=origem_resposta,
                usar_internet=usar_internet,
                permissao_memoria=permissao_memoria,
                permissao_relacao=permissao_relacao,
                ao_aceitar_sugestao=ao_aceitar_sugestao,
            )
        except AprendizagemCancelada:
            return [
                "Aprendizagem cancelada. A etapa em andamento não foi gravada."
            ]
        resposta = (
            entrada_completa.resposta_padrao or entrada_completa.significado
            if entrada_completa is not None
            else None
        )
        return _finalizar_com_contexto(
            [resposta] if resposta else [],
            contexto=contexto,
            frase_normalizada=frase_normalizada,
            banco=banco,
        )

    respostas: list[str] = []
    desconhecidos: list[str] = []
    for indice, token in enumerate(tokens):
        if len(tokens) > 1 and indice == 0 and eh_vocativo(token):
            log.passo(
                "main",
                "processar_frase",
                "vocativo ignorado antes do assunto",
                {"vocativo": token},
            )
            continue
        entradas = buscar_conhecimento(banco, token)
        log.acao(
            "main",
            "processar_frase",
            "consultar termo",
            {"termo": token, "resultados": len(entradas)},
        )
        if len(entradas) > 1 and not modo_aprendizagem:
            respostas.append(_mensagem_sentidos_ambiguos(token, entradas))
            continue

        entrada_completa = None
        try:
            if len(entradas) > 1:
                entrada_completa = aprender_termo(
                    token,
                    banco,
                    perguntar,
                    relacoes=relacoes,
                    origem_resposta=origem_resposta,
                    usar_internet=usar_internet,
                    permissao_memoria=permissao_memoria,
                    permissao_relacao=permissao_relacao,
                    ao_aceitar_sugestao=ao_aceitar_sugestao,
                )
            else:
                entrada_completa = next(
                    (item for item in entradas if item.completa),
                    None,
                )
            if entrada_completa is None:
                if not modo_aprendizagem:
                    desconhecidos.append(token)
                    continue
                entrada_completa = aprender_termo(
                    token,
                    banco,
                    perguntar,
                    relacoes=relacoes,
                    origem_resposta=origem_resposta,
                    usar_internet=usar_internet,
                    permissao_memoria=permissao_memoria,
                    permissao_relacao=permissao_relacao,
                    ao_aceitar_sugestao=ao_aceitar_sugestao,
                )
                if entrada_completa is None:
                    continue
        except AprendizagemCancelada:
            return [
                "Aprendizagem cancelada. A etapa em andamento não foi gravada."
            ]
        resposta = (
            entrada_completa.resposta_padrao
            or entrada_completa.significado
            if entrada_completa is not None
            else None
        )
        if resposta:
            respostas.append(resposta)
    if desconhecidos:
        respostas.append(
            _mensagem_termos_desconhecidos(frase, desconhecidos, banco)
        )
    return _finalizar_com_contexto(
        respostas,
        contexto=contexto,
        frase_normalizada=frase_normalizada,
        banco=banco,
    )


