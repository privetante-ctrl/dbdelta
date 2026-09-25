BEGIN;

-- drop column users.active
-- DANGER drop-column: Dropping users.active permanently deletes its value in every row.
ALTER TABLE "users" DROP COLUMN "active";

-- drop column users.nickname
-- DANGER drop-column: Dropping users.nickname permanently deletes its value in every row.
ALTER TABLE "users" DROP COLUMN "nickname";

-- drop column users.score
-- DANGER drop-column: Dropping users.score permanently deletes its value in every row.
ALTER TABLE "users" DROP COLUMN "score";

COMMIT;
