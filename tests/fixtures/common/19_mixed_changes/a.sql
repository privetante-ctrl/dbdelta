CREATE TABLE teams (
    id integer PRIMARY KEY,
    name text NOT NULL
);
CREATE TABLE players (
    id integer PRIMARY KEY,
    team_id integer REFERENCES teams (id),
    name varchar(50) NOT NULL,
    nickname text,
    rating integer DEFAULT 1000,
    CHECK (rating > 0)
);
CREATE INDEX ix_players_nickname ON players (nickname);
CREATE TABLE legacy_scores (
    id integer PRIMARY KEY,
    player_id integer REFERENCES players (id)
);
