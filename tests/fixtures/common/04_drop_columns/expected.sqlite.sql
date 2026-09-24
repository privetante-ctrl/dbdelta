BEGIN;

-- drop index ix_users_legacy on users (legacy_code)
DROP INDEX "ix_users_legacy";

-- drop column users.legacy_code
ALTER TABLE "users" DROP COLUMN "legacy_code";

-- drop column users.note
ALTER TABLE "users" DROP COLUMN "note";

COMMIT;
