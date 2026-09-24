BEGIN;

-- drop index ix_users_legacy on users (legacy_code)
DROP INDEX "ix_users_legacy";

-- drop column users.legacy_code
-- DANGER drop-column: Dropping users.legacy_code permanently deletes its value in every row.
ALTER TABLE "users" DROP COLUMN "legacy_code";

-- drop column users.note
-- DANGER drop-column: Dropping users.note permanently deletes its value in every row.
ALTER TABLE "users" DROP COLUMN "note";

COMMIT;
