CREATE TABLE teams (
    id integer PRIMARY KEY,
    name text NOT NULL
);
CREATE TABLE members (
    id integer PRIMARY KEY,
    team_id integer REFERENCES teams (id),
    nick_name text,
    email text NOT NULL,
    bio text,
    CHECK (nick_name <> '')
);
CREATE INDEX ix_users_nickname ON members (nick_name);
CREATE TABLE posts (
    id integer PRIMARY KEY,
    author_id integer REFERENCES members (id),
    body text
);
