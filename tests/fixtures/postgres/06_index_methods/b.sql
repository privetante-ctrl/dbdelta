CREATE TABLE documents (
    id integer PRIMARY KEY,
    tags text[] NOT NULL DEFAULT '{}',
    body text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ix_documents_tags ON documents USING gin (tags);
CREATE INDEX ix_documents_body_hash ON documents USING hash (body);
CREATE INDEX ix_documents_created ON documents USING brin (created_at);
