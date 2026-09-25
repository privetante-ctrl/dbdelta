CREATE TABLE teams (
    id integer PRIMARY KEY,
    name text NOT NULL
);
CREATE TABLE users (
    id integer PRIMARY KEY,
    team_id integer REFERENCES teams (id),
    nickname text UNIQUE,
    email text,
    bio text,
    CHECK (nickname <> '')
);
CREATE INDEX ix_users_nickname ON users (nickname);
CREATE TABLE posts (
    id integer PRIMARY KEY,
    author_id integer REFERENCES users (id),
    body text
);
