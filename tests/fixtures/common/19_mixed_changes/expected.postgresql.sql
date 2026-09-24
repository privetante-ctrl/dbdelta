BEGIN;

-- drop foreign key players (team_id) -> teams (id)
ALTER TABLE "players" DROP CONSTRAINT "players_team_id_fkey";

-- drop check constraint on players ("rating" > 0)
ALTER TABLE "players" DROP CONSTRAINT "players_rating_check";

-- drop index ix_players_nickname on players (nickname)
DROP INDEX "ix_players_nickname";

-- drop column players.nickname
-- DANGER drop-column: Dropping players.nickname permanently deletes its value in every row.
ALTER TABLE "players" DROP COLUMN "nickname";

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

-- add column players.email text
ALTER TABLE "players" ADD COLUMN "email" text;

-- add column teams.league_id integer
ALTER TABLE "teams" ADD COLUMN "league_id" integer;

-- drop default of players.rating
ALTER TABLE "players" ALTER COLUMN "rating" DROP DEFAULT;

-- change type of players.name from varchar(50) to varchar(100)
ALTER TABLE "players" ALTER COLUMN "name" TYPE varchar(100);

-- change type of players.rating from integer to bigint
-- WARNING type-rewrite: Changing players.rating from integer to bigint makes PostgreSQL rewrite
--   the whole table and its indexes while holding an ACCESS EXCLUSIVE lock that blocks reads and
--   writes.
ALTER TABLE "players" ALTER COLUMN "rating" TYPE bigint;

-- make players.rating NOT NULL
-- WARNING set-not-null: Making players.rating NOT NULL fails if any row holds NULL, and
--   PostgreSQL checks every row while holding an ACCESS EXCLUSIVE lock that blocks reads and
--   writes.
ALTER TABLE "players" ALTER COLUMN "rating" SET NOT NULL;

-- set default of players.rating to 1200
ALTER TABLE "players" ALTER COLUMN "rating" SET DEFAULT 1200;

-- add check constraint on players ("rating" >= 0)
-- WARNING check-violations: Rows already in players may violate CHECK ("rating" >= 0), which
--   makes the migration fail. PostgreSQL checks every row while holding an ACCESS EXCLUSIVE lock
--   that blocks reads and writes.
ALTER TABLE "players" ADD CHECK ("rating" >= 0);

-- create unique index ux_players_email on players (email)
-- WARNING index-lock: Building ux_players_email blocks inserts, updates and deletes on players
--   (SHARE lock) until the whole table has been indexed.
CREATE UNIQUE INDEX "ux_players_email" ON "players" ("email");

-- add foreign key players (team_id) -> teams (id) ON DELETE SET NULL
-- WARNING foreign-key: Adding the foreign key checks every row of players while holding SHARE
--   ROW EXCLUSIVE locks on players and teams, which block writes to both; rows without a match
--   make the migration fail.
ALTER TABLE "players" ADD FOREIGN KEY ("team_id") REFERENCES "teams" ("id") ON DELETE SET NULL;

-- add foreign key teams (league_id) -> leagues (id)
-- WARNING foreign-key: Adding the foreign key checks every row of teams while holding SHARE ROW
--   EXCLUSIVE locks on teams and leagues, which block writes to both; rows without a match make
--   the migration fail.
ALTER TABLE "teams" ADD FOREIGN KEY ("league_id") REFERENCES "leagues" ("id");

COMMIT;
