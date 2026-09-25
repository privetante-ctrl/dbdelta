BEGIN;

-- drop foreign key players (team_id) -> teams (id) ON DELETE SET NULL
ALTER TABLE "players" DROP CONSTRAINT "players_team_id_fkey";

-- drop foreign key teams (league_id) -> leagues (id)
ALTER TABLE "teams" DROP CONSTRAINT "teams_league_id_fkey";

-- drop check constraint on players ("rating" >= 0)
ALTER TABLE "players" DROP CONSTRAINT "players_rating_check";

-- drop unique index ux_players_email on players (email)
DROP INDEX "ux_players_email";

-- drop column players.email
-- DANGER drop-column: Dropping players.email permanently deletes its value in every row.
ALTER TABLE "players" DROP COLUMN "email";

-- drop column teams.league_id
-- DANGER drop-column: Dropping teams.league_id permanently deletes its value in every row.
ALTER TABLE "teams" DROP COLUMN "league_id";

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

-- add column players.nickname text
-- IRREVERSIBLE: The up migration dropped players.nickname with its values; this adds it again
--   with every value NULL.
ALTER TABLE "players" ADD COLUMN "nickname" text;

-- drop default of players.rating
ALTER TABLE "players" ALTER COLUMN "rating" DROP DEFAULT;

-- allow NULL in players.rating
ALTER TABLE "players" ALTER COLUMN "rating" DROP NOT NULL;

-- change type of players.name from varchar(100) to varchar(50)
-- DANGER narrowing-type: players.name changes from varchar(100) to the narrower varchar(50).
--   Values longer than 50 characters make the migration fail.
-- WARNING type-rewrite: Changing players.name from varchar(100) to varchar(50) makes PostgreSQL
--   rewrite the whole table and its indexes while holding an ACCESS EXCLUSIVE lock that blocks
--   reads and writes.
ALTER TABLE "players" ALTER COLUMN "name" TYPE varchar(50);

-- change type of players.rating from bigint to integer
-- DANGER narrowing-type: players.rating changes from bigint to the narrower integer. Values
--   outside the range of integer make the migration fail.
-- WARNING type-rewrite: Changing players.rating from bigint to integer makes PostgreSQL rewrite
--   the whole table and its indexes while holding an ACCESS EXCLUSIVE lock that blocks reads and
--   writes.
ALTER TABLE "players" ALTER COLUMN "rating" TYPE integer;

-- set default of players.rating to 1000
ALTER TABLE "players" ALTER COLUMN "rating" SET DEFAULT 1000;

-- add check constraint on players ("rating" > 0)
-- WARNING check-violations: Rows already in players may violate CHECK ("rating" > 0), which
--   makes the migration fail. PostgreSQL checks every row while holding an ACCESS EXCLUSIVE lock
--   that blocks reads and writes.
ALTER TABLE "players" ADD CHECK ("rating" > 0);

-- create index ix_players_nickname on players (nickname)
-- WARNING index-lock: Building ix_players_nickname blocks inserts, updates and deletes on
--   players (SHARE lock) until the whole table has been indexed.
CREATE INDEX "ix_players_nickname" ON "players" ("nickname");

-- add foreign key players (team_id) -> teams (id)
-- WARNING foreign-key: Adding the foreign key checks every row of players while holding SHARE
--   ROW EXCLUSIVE locks on players and teams, which block writes to both; rows without a match
--   make the migration fail.
ALTER TABLE "players" ADD FOREIGN KEY ("team_id") REFERENCES "teams" ("id");

COMMIT;
