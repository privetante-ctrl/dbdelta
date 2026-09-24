CREATE TABLE leagues (
    id integer PRIMARY KEY,
    name text NOT NULL UNIQUE
);
CREATE TABLE teams (
    id integer PRIMARY KEY,
    name text NOT NULL,
    league_id integer REFERENCES leagues (id)
);
CREATE TABLE players (
    id integer PRIMARY KEY,
    team_id integer REFERENCES teams (id) ON DELETE SET NULL,
    name varchar(100) NOT NULL,
    rating bigint NOT NULL DEFAULT 1200,
    email text,
    CHECK (rating >= 0)
);
CREATE UNIQUE INDEX ux_players_email ON players (email);
