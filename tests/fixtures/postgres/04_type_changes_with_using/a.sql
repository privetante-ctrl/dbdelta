CREATE TABLE measurements (
    id integer PRIMARY KEY,
    reading text NOT NULL,
    taken text,
    flag integer,
    payload json
);
