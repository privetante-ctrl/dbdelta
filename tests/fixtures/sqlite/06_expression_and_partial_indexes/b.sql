CREATE TABLE people (
    id INTEGER PRIMARY KEY,
    email TEXT,
    deleted_at DATETIME
);
CREATE UNIQUE INDEX ux_people_email ON people (lower(email)) WHERE deleted_at IS NULL;
