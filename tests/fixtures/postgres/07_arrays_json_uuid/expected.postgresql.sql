BEGIN;

-- add column profiles.external_id uuid
ALTER TABLE "profiles" ADD COLUMN "external_id" uuid;

-- add column profiles.aliases varchar(30)[]
ALTER TABLE "profiles" ADD COLUMN "aliases" varchar(30)[];

-- add column profiles.preferences jsonb NOT NULL DEFAULT '{}'
ALTER TABLE "profiles" ADD COLUMN "preferences" jsonb NOT NULL DEFAULT '{}';

-- change type of profiles.settings from json to jsonb
-- WARNING type-rewrite: There is no automatic conversion from json to jsonb, so values are
--   converted with USING and any value that does not convert makes the migration fail. Changing
--   profiles.settings from json to jsonb makes PostgreSQL rewrite the whole table and its
--   indexes while holding an ACCESS EXCLUSIVE lock that blocks reads and writes.
ALTER TABLE "profiles" ALTER COLUMN "settings" TYPE jsonb USING "settings"::jsonb;

COMMIT;
