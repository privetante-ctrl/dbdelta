-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- drop table leagues
-- DANGER drop-table: Dropping leagues permanently deletes all of its rows.
DROP TABLE "leagues";

-- create table legacy_scores
-- IRREVERSIBLE: The up migration dropped table legacy_scores with its rows; this creates it
--   again, empty.
CREATE TABLE "legacy_scores" (
    "id" integer NOT NULL,
    "player_id" integer,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("player_id") REFERENCES "players" ("id")
);

-- rebuild table players: SQLite cannot make these changes in place
--   drop column players.email
--   add column players.nickname text
--   change type of players.name from varchar(100) to varchar(50)
--   change type of players.rating from bigint to integer
--   set default of players.rating to 1000
--   allow NULL in players.rating
--   drop foreign key players (team_id) -> teams (id) ON DELETE SET NULL
--   add foreign key players (team_id) -> teams (id)
--   drop check constraint on players ("rating" >= 0)
--   add check constraint on players ("rating" > 0)
--   drop unique index ux_players_email on players (email)
--   create index ix_players_nickname on players (nickname)
--   drop default of players.rating
-- IRREVERSIBLE: The up migration dropped players.nickname with its values; this adds it again
--   with every value NULL.
-- DANGER drop-column: Dropping players.email permanently deletes its value in every row.
-- WARNING check-violations: Rows already in players may violate CHECK ("rating" > 0), which
--   makes the migration fail.
-- WARNING foreign-key: SQLite does not check existing rows of players when a foreign key is
--   added. The migration runs PRAGMA foreign_key_check, which lists rows without a match but
--   does not stop the migration.
-- WARNING sqlite-rebuild: SQLite cannot make these changes to players in place, so the table is
--   rebuilt: a new table is created, every row is copied, the old table is dropped and the new
--   one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
-- INFO narrowing-type: players.name changes from varchar(100) to the narrower varchar(50).
--   SQLite does not enforce declared lengths or ranges, so stored values stay as they are.
-- INFO narrowing-type: players.rating changes from bigint to the narrower integer. SQLite does
--   not enforce declared lengths or ranges, so stored values stay as they are.
CREATE TABLE "_dbdelta_new_players" (
    "id" integer NOT NULL,
    "team_id" integer,
    "name" varchar(50) NOT NULL,
    "nickname" text,
    "rating" integer DEFAULT 1000,
    PRIMARY KEY ("id"),
    CHECK ("rating" > 0),
    FOREIGN KEY ("team_id") REFERENCES "teams" ("id")
);

INSERT INTO "_dbdelta_new_players" ("id", "team_id", "name", "rating") SELECT "id", "team_id", "name", "rating" FROM "players";

DROP TABLE "players";

ALTER TABLE "_dbdelta_new_players" RENAME TO "players";

CREATE INDEX "ix_players_nickname" ON "players" ("nickname");

-- rebuild table teams: SQLite cannot make these changes in place
--   drop column teams.league_id
--   drop foreign key teams (league_id) -> leagues (id)
-- DANGER drop-column: Dropping teams.league_id permanently deletes its value in every row.
-- WARNING sqlite-rebuild: SQLite cannot make these changes to teams in place, so the table is
--   rebuilt: a new table is created, every row is copied, the old table is dropped and the new
--   one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
CREATE TABLE "_dbdelta_new_teams" (
    "id" integer NOT NULL,
    "name" text NOT NULL,
    PRIMARY KEY ("id")
);

INSERT INTO "_dbdelta_new_teams" ("id", "name") SELECT "id", "name" FROM "teams";

DROP TABLE "teams";

ALTER TABLE "_dbdelta_new_teams" RENAME TO "teams";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
