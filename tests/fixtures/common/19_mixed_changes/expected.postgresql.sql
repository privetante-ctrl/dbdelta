BEGIN;

-- drop foreign key players (team_id) -> teams (id)
ALTER TABLE "players" DROP CONSTRAINT "players_team_id_fkey";

-- drop check constraint on players ("rating" > 0)
ALTER TABLE "players" DROP CONSTRAINT "players_rating_check";

-- drop index ix_players_nickname on players (nickname)
DROP INDEX "ix_players_nickname";

-- drop column players.nickname
ALTER TABLE "players" DROP COLUMN "nickname";

-- drop table legacy_scores
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
ALTER TABLE "players" ALTER COLUMN "rating" TYPE bigint;

-- make players.rating NOT NULL
ALTER TABLE "players" ALTER COLUMN "rating" SET NOT NULL;

-- set default of players.rating to 1200
ALTER TABLE "players" ALTER COLUMN "rating" SET DEFAULT 1200;

-- add check constraint on players ("rating" >= 0)
ALTER TABLE "players" ADD CHECK ("rating" >= 0);

-- create unique index ux_players_email on players (email)
CREATE UNIQUE INDEX "ux_players_email" ON "players" ("email");

-- add foreign key players (team_id) -> teams (id) ON DELETE SET NULL
ALTER TABLE "players" ADD FOREIGN KEY ("team_id") REFERENCES "teams" ("id") ON DELETE SET NULL;

-- add foreign key teams (league_id) -> leagues (id)
ALTER TABLE "teams" ADD FOREIGN KEY ("league_id") REFERENCES "leagues" ("id");

COMMIT;
