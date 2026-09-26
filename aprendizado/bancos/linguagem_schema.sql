-- HEN-ISANA — Fase 1.1
-- Schema físico inicial do banco linguístico novo.
-- Este DDL não lê nem escreve bancos legados.

PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE fontes (
    id INTEGER PRIMARY KEY,
    tipo TEXT NOT NULL CHECK (tipo IN (
        'manual', 'professor', 'llama', 'agente', 'internet', 'legado', 'sistema'
    )),
    identificador TEXT NOT NULL CHECK (trim(identificador) <> ''),
    origem TEXT NOT NULL CHECK (trim(origem) <> ''),
    descricao TEXT,
    confiabilidade REAL NOT NULL DEFAULT 0.5
        CHECK (confiabilidade BETWEEN 0.0 AND 1.0),
    estado TEXT NOT NULL DEFAULT 'candidato'
        CHECK (estado IN ('candidato', 'aprovado', 'recusado', 'revertido')),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (tipo, identificador)
);

CREATE TABLE lexemas (
    id INTEGER PRIMARY KEY,
    lema TEXT NOT NULL CHECK (trim(lema) <> ''),
    categoria_lexical TEXT NOT NULL CHECK (trim(categoria_lexical) <> ''),
    descricao TEXT,
    estado TEXT NOT NULL DEFAULT 'candidato'
        CHECK (estado IN ('candidato', 'aprovado', 'recusado', 'revertido')),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (lema, categoria_lexical)
);

CREATE TABLE formas_lexicais (
    id INTEGER PRIMARY KEY,
    lexema_id INTEGER NOT NULL,
    forma TEXT NOT NULL CHECK (trim(forma) <> ''),
    normalizada TEXT NOT NULL CHECK (trim(normalizada) <> ''),
    tipo_forma TEXT NOT NULL DEFAULT 'flexionada'
        CHECK (tipo_forma IN ('base', 'flexionada', 'variante', 'ortografica')),
    estado TEXT NOT NULL DEFAULT 'candidato'
        CHECK (estado IN ('candidato', 'aprovado', 'recusado', 'revertido')),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lexema_id) REFERENCES lexemas(id) ON DELETE CASCADE,
    UNIQUE (lexema_id, normalizada)
);

CREATE TABLE analises_morfologicas (
    id INTEGER PRIMARY KEY,
    forma_lexical_id INTEGER NOT NULL,
    classe_gramatical TEXT NOT NULL CHECK (trim(classe_gramatical) <> ''),
    genero TEXT,
    numero TEXT,
    pessoa TEXT,
    tempo TEXT,
    modo TEXT,
    aspecto TEXT,
    voz TEXT,
    confianca REAL NOT NULL DEFAULT 0.5
        CHECK (confianca BETWEEN 0.0 AND 1.0),
    FOREIGN KEY (forma_lexical_id) REFERENCES formas_lexicais(id) ON DELETE CASCADE
);

CREATE TABLE sentidos (
    id INTEGER PRIMARY KEY,
    lexema_id INTEGER NOT NULL,
    definicao TEXT NOT NULL CHECK (trim(definicao) <> ''),
    contexto_uso TEXT,
    classe_gramatical TEXT,
    dominio TEXT,
    estado TEXT NOT NULL DEFAULT 'candidato'
        CHECK (estado IN ('candidato', 'aprovado', 'recusado', 'revertido')),
    confianca REAL NOT NULL DEFAULT 0.5
        CHECK (confianca BETWEEN 0.0 AND 1.0),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (lexema_id) REFERENCES lexemas(id) ON DELETE CASCADE
);

CREATE TABLE conceitos (
    id INTEGER PRIMARY KEY,
    chave TEXT NOT NULL CHECK (trim(chave) <> ''),
    rotulo TEXT NOT NULL CHECK (trim(rotulo) <> ''),
    descricao TEXT,
    tipo TEXT NOT NULL CHECK (trim(tipo) <> ''),
    estado TEXT NOT NULL DEFAULT 'candidato'
        CHECK (estado IN ('candidato', 'aprovado', 'recusado', 'revertido')),
    confianca REAL NOT NULL DEFAULT 0.5
        CHECK (confianca BETWEEN 0.0 AND 1.0),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (chave)
);

CREATE TABLE sentidos_conceitos (
    sentido_id INTEGER NOT NULL,
    conceito_id INTEGER NOT NULL,
    tipo_ligacao TEXT NOT NULL
        CHECK (tipo_ligacao IN ('principal', 'relacionado', 'equivalente', 'instanciacao')),
    confianca REAL NOT NULL DEFAULT 0.5
        CHECK (confianca BETWEEN 0.0 AND 1.0),
    estado TEXT NOT NULL DEFAULT 'candidato'
        CHECK (estado IN ('candidato', 'aprovado', 'recusado', 'revertido')),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (sentido_id, conceito_id),
    FOREIGN KEY (sentido_id) REFERENCES sentidos(id) ON DELETE CASCADE,
    FOREIGN KEY (conceito_id) REFERENCES conceitos(id) ON DELETE CASCADE
);

CREATE TABLE expressoes (
    id INTEGER PRIMARY KEY,
    forma TEXT NOT NULL CHECK (trim(forma) <> ''),
    normalizada TEXT NOT NULL CHECK (trim(normalizada) <> ''),
    tipo TEXT NOT NULL
        CHECK (tipo IN ('fixa', 'semi_fixa', 'conversacional', 'produtiva')),
    fixidez REAL NOT NULL DEFAULT 0.5
        CHECK (fixidez BETWEEN 0.0 AND 1.0),
    estado TEXT NOT NULL DEFAULT 'candidato'
        CHECK (estado IN ('candidato', 'aprovado', 'recusado', 'revertido')),
    confianca REAL NOT NULL DEFAULT 0.5
        CHECK (confianca BETWEEN 0.0 AND 1.0),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (normalizada)
);

CREATE TABLE expressao_componentes (
    expressao_id INTEGER NOT NULL,
    ordem INTEGER NOT NULL CHECK (ordem > 0),
    tipo_componente TEXT NOT NULL
        CHECK (tipo_componente IN ('lexema', 'literal', 'variavel')),
    texto TEXT,
    lexema_id INTEGER,
    opcional INTEGER NOT NULL DEFAULT 0 CHECK (opcional IN (0, 1)),
    restricao TEXT,
    PRIMARY KEY (expressao_id, ordem),
    CHECK (
        (tipo_componente = 'lexema' AND lexema_id IS NOT NULL)
        OR (tipo_componente IN ('literal', 'variavel') AND texto IS NOT NULL
            AND trim(texto) <> '')
    ),
    FOREIGN KEY (expressao_id) REFERENCES expressoes(id) ON DELETE CASCADE,
    FOREIGN KEY (lexema_id) REFERENCES lexemas(id) ON DELETE RESTRICT
);

CREATE TABLE proposicoes (
    id INTEGER PRIMARY KEY,
    predicado_sentido_id INTEGER,
    predicado_conceito_id INTEGER,
    tipo_predicado TEXT NOT NULL
        CHECK (tipo_predicado IN ('propriedade', 'evento', 'estado', 'relacao', 'operador')),
    polaridade TEXT NOT NULL DEFAULT 'afirmativa'
        CHECK (polaridade IN ('afirmativa', 'negativa', 'interrogativa')),
    modalidade TEXT NOT NULL DEFAULT 'assertiva'
        CHECK (modalidade IN (
            'assertiva', 'epistemica', 'deontica', 'desejo',
            'hipotetica', 'citada', 'condicional'
        )),
    tempo_referencia TEXT,
    escopo_id INTEGER,
    estado TEXT NOT NULL DEFAULT 'candidato'
        CHECK (estado IN ('candidato', 'aprovado', 'recusado', 'revertido')),
    confianca REAL NOT NULL DEFAULT 0.5
        CHECK (confianca BETWEEN 0.0 AND 1.0),
    fonte_id INTEGER,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (predicado_sentido_id IS NOT NULL OR predicado_conceito_id IS NOT NULL),
    CHECK (escopo_id IS NULL OR escopo_id <> id),
    FOREIGN KEY (predicado_sentido_id) REFERENCES sentidos(id) ON DELETE RESTRICT,
    FOREIGN KEY (predicado_conceito_id) REFERENCES conceitos(id) ON DELETE RESTRICT,
    FOREIGN KEY (escopo_id) REFERENCES proposicoes(id) ON DELETE SET NULL,
    FOREIGN KEY (fonte_id) REFERENCES fontes(id) ON DELETE RESTRICT
);

CREATE TABLE proposicao_argumentos (
    id INTEGER PRIMARY KEY,
    proposicao_id INTEGER NOT NULL,
    ordem INTEGER NOT NULL CHECK (ordem > 0),
    papel TEXT NOT NULL CHECK (trim(papel) <> ''),
    alvo_tipo TEXT NOT NULL
        CHECK (alvo_tipo IN ('conceito', 'sentido', 'proposicao', 'fato')),
    alvo_id INTEGER NOT NULL CHECK (alvo_id > 0),
    funcao_sintatica TEXT,
    confianca REAL NOT NULL DEFAULT 0.5
        CHECK (confianca BETWEEN 0.0 AND 1.0),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (proposicao_id, ordem),
    FOREIGN KEY (proposicao_id) REFERENCES proposicoes(id) ON DELETE CASCADE
);

CREATE TABLE fatos (
    id INTEGER PRIMARY KEY,
    proposicao_id INTEGER NOT NULL,
    estado TEXT NOT NULL DEFAULT 'candidato'
        CHECK (estado IN ('candidato', 'aprovado', 'recusado', 'revertido')),
    validade_inicio TEXT,
    validade_fim TEXT,
    fonte_id INTEGER NOT NULL,
    confianca REAL NOT NULL DEFAULT 0.5
        CHECK (confianca BETWEEN 0.0 AND 1.0),
    contexto TEXT,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    atualizado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (validade_fim IS NULL OR validade_inicio IS NULL OR validade_fim >= validade_inicio),
    FOREIGN KEY (proposicao_id) REFERENCES proposicoes(id) ON DELETE RESTRICT,
    FOREIGN KEY (fonte_id) REFERENCES fontes(id) ON DELETE RESTRICT
);

CREATE TABLE relacoes_semanticas (
    id INTEGER PRIMARY KEY,
    tipo_relacao TEXT NOT NULL CHECK (trim(tipo_relacao) <> ''),
    origem_tipo TEXT NOT NULL
        CHECK (origem_tipo IN (
            'conceito', 'sentido', 'proposicao', 'fato', 'expressao'
        )),
    origem_id INTEGER NOT NULL CHECK (origem_id > 0),
    destino_tipo TEXT NOT NULL
        CHECK (destino_tipo IN (
            'conceito', 'sentido', 'proposicao', 'fato', 'expressao'
        )),
    destino_id INTEGER NOT NULL CHECK (destino_id > 0),
    direcao TEXT NOT NULL DEFAULT 'direta'
        CHECK (direcao IN ('direta', 'simetrica')),
    estado TEXT NOT NULL DEFAULT 'candidato'
        CHECK (estado IN ('candidato', 'aprovado', 'recusado', 'revertido')),
    contexto TEXT,
    confianca REAL NOT NULL DEFAULT 0.5
        CHECK (confianca BETWEEN 0.0 AND 1.0),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (NOT (origem_tipo = destino_tipo AND origem_id = destino_id))
);

CREATE TABLE evidencias (
    id INTEGER PRIMARY KEY,
    fonte_id INTEGER NOT NULL,
    alvo_tipo TEXT NOT NULL
        CHECK (alvo_tipo IN (
            'lexema', 'forma_lexical', 'analise_morfologica', 'sentido',
            'conceito', 'expressao', 'proposicao', 'fato', 'relacao_semantica'
        )),
    alvo_id INTEGER NOT NULL CHECK (alvo_id > 0),
    trecho TEXT NOT NULL CHECK (trim(trecho) <> ''),
    referencia TEXT,
    data_evidencia TEXT,
    estado TEXT NOT NULL DEFAULT 'candidato'
        CHECK (estado IN ('candidato', 'aprovado', 'recusado', 'revertido')),
    confianca REAL NOT NULL DEFAULT 0.5
        CHECK (confianca BETWEEN 0.0 AND 1.0),
    revisao_necessaria INTEGER NOT NULL DEFAULT 1 CHECK (revisao_necessaria IN (0, 1)),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (fonte_id) REFERENCES fontes(id) ON DELETE RESTRICT
);

CREATE INDEX idx_lexemas_lema
    ON lexemas(lema COLLATE NOCASE);

CREATE INDEX idx_formas_lexemas
    ON formas_lexicais(lexema_id, normalizada COLLATE NOCASE);

CREATE INDEX idx_analises_formas
    ON analises_morfologicas(forma_lexical_id);

CREATE INDEX idx_sentidos_lexemas
    ON sentidos(lexema_id, estado);

CREATE INDEX idx_sentidos_conceitos_conceito
    ON sentidos_conceitos(conceito_id, estado);

CREATE INDEX idx_expressoes_normalizada
    ON expressoes(normalizada COLLATE NOCASE);

CREATE INDEX idx_componentes_lexemas
    ON expressao_componentes(lexema_id);

CREATE INDEX idx_proposicoes_predicados
    ON proposicoes(predicado_conceito_id, predicado_sentido_id, estado);

CREATE INDEX idx_argumentos_proposicoes
    ON proposicao_argumentos(proposicao_id, ordem);

CREATE INDEX idx_fatos_proposicoes
    ON fatos(proposicao_id, estado);

CREATE INDEX idx_relacoes_origem
    ON relacoes_semanticas(origem_tipo, origem_id, estado);

CREATE INDEX idx_relacoes_destino
    ON relacoes_semanticas(destino_tipo, destino_id, estado);

CREATE INDEX idx_evidencias_alvo
    ON evidencias(alvo_tipo, alvo_id, estado);

CREATE INDEX idx_evidencias_fontes
    ON evidencias(fonte_id, estado);

PRAGMA user_version = 110;

COMMIT;