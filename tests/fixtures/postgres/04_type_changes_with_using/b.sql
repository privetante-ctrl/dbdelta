CREATE TABLE measurements (
    id integer PRIMARY KEY,
    reading integer NOT NULL,
    taken date,
    flag boolean,
    payload jsonb
);
