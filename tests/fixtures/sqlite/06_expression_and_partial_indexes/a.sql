CREATE TABLE people (
    id INTEGER PRIMARY KEY,
    email TEXT,
    deleted_at DATETIME
);
CREATE INDEX ix_people_email ON people (email);
