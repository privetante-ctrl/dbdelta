-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rename table users to members
-- WARNING rename: Renaming table users to members keeps its data, but application code, views,
--   functions and triggers that still use the old name fail. The database updates keys, indexes
--   and foreign keys itself.
ALTER TABLE "users" RENAME TO "members";

-- rename column members.nickname to nick_name
-- WARNING rename: Renaming column members.nickname to nick_name keeps its data, but application
--   code, views, functions and triggers that still use the old name fail. The database updates
--   keys, indexes and foreign keys itself.
ALTER TABLE "members" RENAME COLUMN "nickname" TO "nick_name";

-- rebuild table members: SQLite cannot make these changes in place
--   make members.email NOT NULL
--   drop unique constraint on members (nick_name)
-- WARNING set-not-null: Making members.email NOT NULL fails if any row holds NULL.
-- WARNING sqlite-rebuild: SQLite cannot make these changes to members in place, so the table is
--   rebuilt: a new table is created, every row is copied, the old table is dropped and the new
--   one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
CREATE TABLE "_dbdelta_new_members" (
    "id" integer NOT NULL,
    "team_id" integer,
    "nick_name" text,
    "email" text NOT NULL,
    "bio" text,
    PRIMARY KEY ("id"),
    CHECK ("nick_name" <> ''),
    FOREIGN KEY ("team_id") REFERENCES "teams" ("id")
);

INSERT INTO "_dbdelta_new_members" ("id", "team_id", "nick_name", "email", "bio") SELECT "id", "team_id", "nick_name", "email", "bio" FROM "members";

DROP TABLE "members";

ALTER TABLE "_dbdelta_new_members" RENAME TO "members";

CREATE INDEX "ix_users_nickname" ON "members" ("nick_name");

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
