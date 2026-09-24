CREATE TABLE settings (
    id integer PRIMARY KEY,
    theme text DEFAULT 'light',
    page_size integer,
    level integer DEFAULT 1,
    created_at timestamp
);
