CREATE TABLE documents (
    id integer PRIMARY KEY,
    tags text[] NOT NULL DEFAULT '{}',
    body text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
