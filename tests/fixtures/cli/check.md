### dbdelta: 16 changes, 8 risks: 2 danger, 6 warning.

❌ **Check failed: 2 dangerous changes. Review them, then rerun with --allow-destructive to accept them.**

From `a.sql` to `b.sql` (postgresql).

| # | Change | Risk |
|--:|--------|------|
| 1 | create table leagues |  |
| 2 | drop table legacy\_scores | 🔴 danger |
| 3 | drop column players.nickname | 🔴 danger |
| 4 | add column players.email text |  |
| 5 | change type of players.name from varchar(50) to varchar(100) |  |
| 6 | change type of players.rating from integer to bigint | 🟠 warning |
| 7 | set default of players.rating to 1200 |  |
| 8 | make players.rating NOT NULL | 🟠 warning |
| 9 | drop foreign key players (team\_id) -> teams (id) |  |
| 10 | add foreign key players (team\_id) -> teams (id) ON DELETE SET NULL | 🟠 warning |
| 11 | drop check constraint on players ("rating" > 0) |  |
| 12 | add check constraint on players ("rating" >= 0) | 🟠 warning |
| 13 | drop index ix\_players\_nickname on players (nickname) |  |
| 14 | create unique index ux\_players\_email on players (email) | 🟠 warning |
| 15 | add column teams.league\_id integer |  |
| 16 | add foreign key teams (league\_id) -> leagues (id) | 🟠 warning |

#### Risks

- 🔴 **danger** `drop-column` on players.nickname

  Dropping players.nickname permanently deletes its value in every row.

  **Safer:** Stop reading and writing the column in the application and deploy that first, back the values up, then drop the column in a later migration (expand and contract).

  <details>
  <summary>Check before migrating</summary>

  ```sql
  SELECT count(*) FROM "players" WHERE "players"."nickname" IS NOT NULL
  ```
  </details>

- 🔴 **danger** `drop-table` on table legacy\_scores

  Dropping legacy\_scores permanently deletes all of its rows.

  **Safer:** Back the data up first, for example with CREATE TABLE ... AS SELECT, or stop using the table and drop it in a later release once nothing reads it.

  <details>
  <summary>Check before migrating</summary>

  ```sql
  SELECT count(*) FROM "legacy_scores"
  ```
  </details>

- 🟠 **warning** `check-violations` on check on players ("rating" >= 0)

  Rows already in players may violate CHECK ("rating" >= 0), which makes the migration fail. PostgreSQL checks every row while holding an ACCESS EXCLUSIVE lock that blocks reads and writes.

  **Safer:** Fix the violating rows first. On a large table, add the constraint with NOT VALID and run ALTER TABLE ... VALIDATE CONSTRAINT separately; validating does not block writes.

  <details>
  <summary>Check before migrating</summary>

  ```sql
  SELECT count(*) FROM "players" WHERE NOT ("rating" >= 0)
  ```
  </details>

- 🟠 **warning** `foreign-key` on foreign key players (team\_id) -> teams

  Adding the foreign key checks every row of players while holding SHARE ROW EXCLUSIVE locks on players and teams, which block writes to both; rows without a match make the migration fail.

  **Safer:** Add the constraint with NOT VALID, which only takes a brief lock, then run ALTER TABLE ... VALIDATE CONSTRAINT in a separate transaction; validating does not block writes.

  <details>
  <summary>Check before migrating</summary>

  ```sql
  SELECT count(*) FROM "players" AS child WHERE child."team_id" IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "teams" AS parent WHERE parent."id" = child."team_id")
  ```
  </details>

- 🟠 **warning** `foreign-key` on foreign key teams (league\_id) -> leagues

  Adding the foreign key checks every row of teams while holding SHARE ROW EXCLUSIVE locks on teams and leagues, which block writes to both; rows without a match make the migration fail.

  **Safer:** Add the constraint with NOT VALID, which only takes a brief lock, then run ALTER TABLE ... VALIDATE CONSTRAINT in a separate transaction; validating does not block writes.

- 🟠 **warning** `index-lock` on index ux\_players\_email on players

  Building ux\_players\_email blocks inserts, updates and deletes on players (SHARE lock) until the whole table has been indexed.

  **Safer:** Run with --concurrent-indexes to build it with CREATE INDEX CONCURRENTLY outside the transaction: it takes longer but does not block writes.

- 🟠 **warning** `set-not-null` on players.rating

  Making players.rating NOT NULL fails if any row holds NULL, and PostgreSQL checks every row while holding an ACCESS EXCLUSIVE lock that blocks reads and writes.

  **Safer:** Backfill the NULLs first. On a large table, add CHECK (column IS NOT NULL) NOT VALID, validate it in a separate transaction, then SET NOT NULL: PostgreSQL 12 and later use the validated constraint and skip the scan.

  <details>
  <summary>Check before migrating</summary>

  ```sql
  SELECT count(*) FROM "players" WHERE "players"."rating" IS NULL
  ```
  </details>

- 🟠 **warning** `type-rewrite` on players.rating

  Changing players.rating from integer to bigint makes PostgreSQL rewrite the whole table and its indexes while holding an ACCESS EXCLUSIVE lock that blocks reads and writes.

  **Safer:** On a large table, add a new column of the new type, backfill it in batches, switch the application over and drop the old column; otherwise run the migration in a maintenance window.

<details>
<summary>Migration SQL</summary>

```sql
-- Migration from a.sql to b.sql (postgresql), generated by dbdelta <version>.
-- 16 changes, 8 risks: 2 danger, 6 warning.
-- Read the comments marked DANGER, WARNING and INFO before running it.

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
```
</details>
