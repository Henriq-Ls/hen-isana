-- HEN-ISANA — infraestrutura auxiliar de migração auditável.
-- Este schema é separado de linguagem.db e não contém conhecimento canônico.

PRAGMA foreign_keys = ON;

BEGIN;

CREATE TABLE propostas_migracao (
    proposta_id TEXT PRIMARY KEY,
    idempotencia TEXT NOT NULL UNIQUE,
    hash_conteudo TEXT NOT NULL,
    conteudo_json TEXT NOT NULL,
    versao_contrato TEXT NOT NULL,
    versao_mapeamento TEXT NOT NULL,
    lote TEXT,
    origem TEXT NOT NULL,
    estado TEXT NOT NULL
        CHECK (estado IN (
            'proposta', 'em_revisao', 'autorizada',
            'aplicada', 'recusada', 'erro'
        )),
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revisado_em TEXT,
    autorizado_em TEXT,
    aplicado_em TEXT,
    revisor TEXT,
    autorizador TEXT,
    hash_conteudo_autorizado TEXT,
    resultado_aplicacao TEXT,
    erro TEXT
);

CREATE INDEX idx_propostas_migracao_estado
    ON propostas_migracao(estado);

CREATE INDEX idx_propostas_migracao_lote
    ON propostas_migracao(lote);

CREATE TABLE mapa_aplicacao_migracao (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    proposta_id TEXT NOT NULL,
    objeto_id TEXT NOT NULL,
    tipo TEXT NOT NULL,
    id_fisico TEXT NOT NULL,
    disposicao TEXT NOT NULL
        CHECK (disposicao IN ('criado', 'reutilizado')),
    identidade_logica TEXT NOT NULL,
    lote TEXT,
    execucao_id TEXT NOT NULL,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (proposta_id, objeto_id, tipo, id_fisico),
    FOREIGN KEY (proposta_id)
        REFERENCES propostas_migracao(proposta_id)
        ON DELETE CASCADE
);

CREATE INDEX idx_mapa_aplicacao_proposta
    ON mapa_aplicacao_migracao(proposta_id);

CREATE INDEX idx_mapa_aplicacao_execucao
    ON mapa_aplicacao_migracao(execucao_id);

CREATE TABLE checkpoints_migracao (
    checkpoint_id TEXT PRIMARY KEY,
    caminho_banco TEXT NOT NULL,
    arquivo_checkpoint TEXT NOT NULL UNIQUE,
    lote TEXT,
    manifesto_hash TEXT NOT NULL,
    hash_banco TEXT NOT NULL,
    estado_execucao TEXT NOT NULL,
    criado_em TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

PRAGMA user_version = 1;

COMMIT;
