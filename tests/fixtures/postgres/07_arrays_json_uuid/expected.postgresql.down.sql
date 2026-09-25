BEGIN;

-- drop column profiles.aliases
-- DANGER drop-column: Dropping profiles.aliases permanently deletes its value in every row.
ALTER TABLE "profiles" DROP COLUMN "aliases";

-- drop column profiles.external_id
-- DANGER drop-column: Dropping profiles.external_id permanently deletes its value in every row.
ALTER TABLE "profiles" DROP COLUMN "external_id";

-- drop column profiles.preferences
-- DANGER drop-column: Dropping profiles.preferences permanently deletes its value in every row.
ALTER TABLE "profiles" DROP COLUMN "preferences";

-- change type of profiles.settings from jsonb to json
-- IRREVERSIBLE: The up migration converted profiles.settings from json to jsonb, which may have
--   rounded, cut or reformatted values; converting back does not restore them.
-- WARNING type-rewrite: There is no automatic conversion from jsonb to json, so values are
--   converted with USING and any value that does not convert makes the migration fail. Changing
--   profiles.settings from jsonb to json makes PostgreSQL rewrite the whole table and its
--   indexes while holding an ACCESS EXCLUSIVE lock that blocks reads and writes.
ALTER TABLE "profiles" ALTER COLUMN "settings" TYPE json USING "settings"::json;

COMMIT;
