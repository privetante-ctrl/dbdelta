BEGIN;

-- drop column users.name
-- DANGER drop-column: Dropping users.name permanently deletes its value in every row.
ALTER TABLE "users" DROP COLUMN "name";

COMMIT;
