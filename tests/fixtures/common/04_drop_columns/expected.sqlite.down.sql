BEGIN;

-- add column users.legacy_code text
-- IRREVERSIBLE: The up migration dropped users.legacy_code with its values; this adds it again
--   with every value NULL.
ALTER TABLE "users" ADD COLUMN "legacy_code" text;

-- add column users.note text
-- IRREVERSIBLE: The up migration dropped users.note with its values; this adds it again with
--   every value NULL.
ALTER TABLE "users" ADD COLUMN "note" text;

-- create index ix_users_legacy on users (legacy_code)
CREATE INDEX "ix_users_legacy" ON "users" ("legacy_code");

COMMIT;
