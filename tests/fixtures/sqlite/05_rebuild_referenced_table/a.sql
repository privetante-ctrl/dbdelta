CREATE TABLE owners (
    id INTEGER PRIMARY KEY,
    name TEXT
);
CREATE TABLE pets (
    id INTEGER PRIMARY KEY,
    owner_id INTEGER NOT NULL REFERENCES owners (id)
);
