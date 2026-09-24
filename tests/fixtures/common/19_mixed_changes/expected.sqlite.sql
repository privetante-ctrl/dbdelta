-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- drop table legacy_scores
-- DANGER drop-table: Dropping legacy_scores permanently deletes all of its rows.
DROP TABLE "legacy_scores";

-- create table leagues
CREATE TABLE "leagues" (
    "id" integer NOT NULL,
    "name" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("name")
);

-- rebuild table players: SQLite cannot make these changes in place
--   drop column players.nickname
--   add column players.email text
--   change type of players.name from varchar(50) to varchar(100)
--   change type of players.rating from integer to bigint
--   set default of players.rating to 1200
--   make players.rating NOT NULL
--   drop foreign key players (team_id) -> teams (id)
--   add foreign key players (team_id) -> teams (id) ON DELETE SET NULL
--   drop check constraint on players ("rating" > 0)
--   add check constraint on players ("rating" >= 0)
--   drop index ix_players_nickname on players (nickname)
--   create unique index ux_players_email on players (email)
--   drop default of players.rating
-- DANGER drop-column: Dropping players.nickname permanently deletes its value in every row.
-- WARNING check-violations: Rows already in players may violate CHECK ("rating" >= 0), which
--   makes the migration fail.
-- WARNING foreign-key: SQLite does not check existing rows of players when a foreign key is
--   added. The migration runs PRAGMA foreign_key_check, which lists rows without a match but
--   does not stop the migration.
-- WARNING set-not-null: Making players.rating NOT NULL fails if any row holds NULL.
-- WARNING sqlite-rebuild: SQLite cannot make these changes to players in place, so the table is
--   rebuilt: a new table is created, every row is copied, the old table is dropped and the new
--   one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
CREATE TABLE "_dbdelta_new_players" (
    "id" integer NOT NULL,
    "team_id" integer,
    "name" varchar(100) NOT NULL,
    "rating" bigint NOT NULL DEFAULT 1200,
    "email" text,
    PRIMARY KEY ("id"),
    CHECK ("rating" >= 0),
    FOREIGN KEY ("team_id") REFERENCES "teams" ("id") ON DELETE SET NULL
);

INSERT INTO "_dbdelta_new_players" ("id", "team_id", "name", "rating") SELECT "id", "team_id", "name", "rating" FROM "players";

DROP TABLE "players";

ALTER TABLE "_dbdelta_new_players" RENAME TO "players";

CREATE UNIQUE INDEX "ux_players_email" ON "players" ("email");

-- rebuild table teams: SQLite cannot make these changes in place
--   add column teams.league_id integer
--   add foreign key teams (league_id) -> leagues (id)
-- WARNING foreign-key: SQLite does not check existing rows of teams when a foreign key is added.
--   The migration runs PRAGMA foreign_key_check, which lists rows without a match but does not
--   stop the migration.
-- WARNING sqlite-rebuild: SQLite cannot make these changes to teams in place, so the table is
--   rebuilt: a new table is created, every row is copied, the old table is dropped and the new
--   one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
CREATE TABLE "_dbdelta_new_teams" (
    "id" integer NOT NULL,
    "name" text NOT NULL,
    "league_id" integer,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("league_id") REFERENCES "leagues" ("id")
);

INSERT INTO "_dbdelta_new_teams" ("id", "name") SELECT "id", "name" FROM "teams";

DROP TABLE "teams";

ALTER TABLE "_dbdelta_new_teams" RENAME TO "teams";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
