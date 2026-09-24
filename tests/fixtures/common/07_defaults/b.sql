CREATE TABLE settings (
    id integer PRIMARY KEY,
    theme text DEFAULT 'dark',
    page_size integer DEFAULT 10,
    level integer,
    created_at timestamp DEFAULT CURRENT_TIMESTAMP
);
