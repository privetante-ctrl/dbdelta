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

-- drop unique constraint users_nickname_key on members (nick_name)
ALTER TABLE "members" DROP CONSTRAINT "users_nickname_key";

-- make members.email NOT NULL
-- WARNING set-not-null: Making members.email NOT NULL fails if any row holds NULL, and
--   PostgreSQL checks every row while holding an ACCESS EXCLUSIVE lock that blocks reads and
--   writes.
ALTER TABLE "members" ALTER COLUMN "email" SET NOT NULL;

COMMIT;
