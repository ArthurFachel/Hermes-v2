-- GeoDB — base estruturada da Bacia do Araripe
-- Cada fato carrega ref_id. O agente cita a referência, nunca o arquivo de origem.

PRAGMA foreign_keys = ON;

-- Identidade da carga. Serve de canario: a versao nao existe em nenhum documento
-- nem no conhecimento do modelo, entao so pode ser respondida consultando a base.
CREATE TABLE metadados (
    chave  TEXT PRIMARY KEY,
    valor  TEXT NOT NULL
);

CREATE TABLE referencias (
    id        INTEGER PRIMARY KEY,
    chave     TEXT NOT NULL UNIQUE,   -- "assine2007"
    autores   TEXT NOT NULL,
    ano       INTEGER,
    titulo    TEXT,
    veiculo   TEXT
);

CREATE TABLE bacias (
    id             INTEGER PRIMARY KEY,
    nome           TEXT NOT NULL UNIQUE,
    area_km2       REAL,
    area_nota      TEXT,
    orientacao     TEXT,
    provincia      TEXT,
    dominio        TEXT,
    contexto       TEXT,
    ref_id         INTEGER REFERENCES referencias(id)
);

CREATE TABLE sequencias (
    id          INTEGER PRIMARY KEY,
    bacia_id    INTEGER NOT NULL REFERENCES bacias(id),
    nome        TEXT NOT NULL,
    ordem       INTEGER NOT NULL,     -- 1 = base
    idade       TEXT,
    descricao   TEXT,
    ref_id      INTEGER REFERENCES referencias(id),
    UNIQUE (bacia_id, nome)
);

CREATE TABLE grupos (
    id          INTEGER PRIMARY KEY,
    bacia_id    INTEGER NOT NULL REFERENCES bacias(id),
    nome        TEXT NOT NULL,
    supergrupo  TEXT,
    ref_id      INTEGER REFERENCES referencias(id),
    UNIQUE (bacia_id, nome)
);

CREATE TABLE formacoes (
    id              INTEGER PRIMARY KEY,
    bacia_id        INTEGER NOT NULL REFERENCES bacias(id),
    grupo_id        INTEGER REFERENCES grupos(id),
    sequencia_id    INTEGER REFERENCES sequencias(id),
    nome            TEXT NOT NULL,
    ordem           INTEGER NOT NULL,   -- 1 = base da coluna
    idade           TEXT,
    litologia       TEXT,
    espessura_m     REAL,               -- valor representativo citado
    espessura_nota  TEXT,               -- "media ~200 m", "ate 450 m"
    ambiente        TEXT,
    fossilifera     INTEGER NOT NULL DEFAULT 1,
    observacoes     TEXT,
    ref_id          INTEGER REFERENCES referencias(id),
    UNIQUE (bacia_id, nome)
);

CREATE TABLE geoquimica (
    id               INTEGER PRIMARY KEY,
    formacao_id      INTEGER NOT NULL REFERENCES formacoes(id),
    litotipo         TEXT,              -- "folhelho pirobetuminoso"
    cot_min          REAL,
    cot_max          REAL,
    cot_nota         TEXT,
    tipo_querogenio  TEXT,
    maturidade       TEXT,
    metodo           TEXT,
    ambiente_mo      TEXT,
    ref_id           INTEGER REFERENCES referencias(id)
);

CREATE TABLE fosseis (
    id            INTEGER PRIMARY KEY,
    formacao_id   INTEGER NOT NULL REFERENCES formacoes(id),
    grupo_bio     TEXT NOT NULL,        -- "peixes", "pterossauros"
    detalhe       TEXT,
    ref_id        INTEGER REFERENCES referencias(id)
);

CREATE TABLE pocos (
    id                    INTEGER PRIMARY KEY,
    bacia_id              INTEGER NOT NULL REFERENCES bacias(id),
    nome                  TEXT NOT NULL UNIQUE,
    sub_bacia             TEXT,
    prof_embasamento_m    REAL,
    observacoes           TEXT,
    ref_id                INTEGER REFERENCES referencias(id)
);

-- Divergencias explicitas na literatura. Existe para que uma consulta sobre o
-- tema devolva SEMPRE as duas posicoes, em vez de depender de o RAG achar as duas.
CREATE TABLE controversias (
    id           INTEGER PRIMARY KEY,
    bacia_id     INTEGER REFERENCES bacias(id),
    tema         TEXT NOT NULL,
    posicao_a    TEXT NOT NULL,
    ref_a_id     INTEGER REFERENCES referencias(id),
    posicao_b    TEXT NOT NULL,
    ref_b_id     INTEGER REFERENCES referencias(id),
    situacao     TEXT
);

-- Busca textual sobre o conteudo descritivo das formacoes.
CREATE VIRTUAL TABLE formacoes_fts USING fts5(
    nome, litologia, ambiente, observacoes,
    content='formacoes', content_rowid='id', tokenize="unicode61"
);

CREATE TRIGGER formacoes_ai AFTER INSERT ON formacoes BEGIN
    INSERT INTO formacoes_fts(rowid, nome, litologia, ambiente, observacoes)
    VALUES (new.id, new.nome, new.litologia, new.ambiente, new.observacoes);
END;
CREATE TRIGGER formacoes_ad AFTER DELETE ON formacoes BEGIN
    INSERT INTO formacoes_fts(formacoes_fts, rowid, nome, litologia, ambiente, observacoes)
    VALUES ('delete', old.id, old.nome, old.litologia, old.ambiente, old.observacoes);
END;
CREATE TRIGGER formacoes_au AFTER UPDATE ON formacoes BEGIN
    INSERT INTO formacoes_fts(formacoes_fts, rowid, nome, litologia, ambiente, observacoes)
    VALUES ('delete', old.id, old.nome, old.litologia, old.ambiente, old.observacoes);
    INSERT INTO formacoes_fts(rowid, nome, litologia, ambiente, observacoes)
    VALUES (new.id, new.nome, new.litologia, new.ambiente, new.observacoes);
END;

CREATE INDEX idx_formacoes_grupo ON formacoes(grupo_id);
CREATE INDEX idx_formacoes_seq   ON formacoes(sequencia_id);
CREATE INDEX idx_geoq_formacao   ON geoquimica(formacao_id);
CREATE INDEX idx_fosseis_formacao ON fosseis(formacao_id);
