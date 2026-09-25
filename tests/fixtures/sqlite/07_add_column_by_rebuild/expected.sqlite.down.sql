BEGIN;

-- drop column logs.logged_at
-- DANGER drop-column: Dropping logs.logged_at permanently deletes its value in every row.
ALTER TABLE "logs" DROP COLUMN "logged_at";

COMMIT;
