-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rename table members to users
-- WARNING rename: Renaming table members to users keeps its data, but application code, views,
--   functions and triggers that still use the old name fail. The database updates keys, indexes
--   and foreign keys itself.
ALTER TABLE "members" RENAME TO "users";

-- rename column users.nick_name to nickname
-- WARNING rename: Renaming column users.nick_name to nickname keeps its data, but application
--   code, views, functions and triggers that still use the old name fail. The database updates
--   keys, indexes and foreign keys itself.
ALTER TABLE "users" RENAME COLUMN "nick_name" TO "nickname";

-- rebuild table users: SQLite cannot make these changes in place
--   allow NULL in users.email
--   add unique constraint on users (nickname)
-- WARNING sqlite-rebuild: SQLite cannot make these changes to users in place, so the table is
--   rebuilt: a new table is created, every row is copied, the old table is dropped and the new
--   one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
-- WARNING unique-duplicates: Rows already in users may contain duplicates of (nickname), which
--   make adding the unique constraint fail.
CREATE TABLE "_dbdelta_new_users" (
    "id" integer NOT NULL,
    "team_id" integer,
    "nickname" text,
    "email" text,
    "bio" text,
    PRIMARY KEY ("id"),
    UNIQUE ("nickname"),
    CHECK ("nickname" <> ''),
    FOREIGN KEY ("team_id") REFERENCES "teams" ("id")
);

INSERT INTO "_dbdelta_new_users" ("id", "team_id", "nickname", "email", "bio") SELECT "id", "team_id", "nickname", "email", "bio" FROM "users";

DROP TABLE "users";

ALTER TABLE "_dbdelta_new_users" RENAME TO "users";

CREATE INDEX "ix_users_nickname" ON "users" ("nickname");

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
