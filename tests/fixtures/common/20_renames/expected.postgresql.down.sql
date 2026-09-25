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

-- allow NULL in users.email
ALTER TABLE "users" ALTER COLUMN "email" DROP NOT NULL;

-- add unique constraint on users (nickname)
-- WARNING unique-duplicates: Rows already in users may contain duplicates of (nickname), which
--   make adding the unique constraint fail.
ALTER TABLE "users" ADD UNIQUE ("nickname");

COMMIT;
