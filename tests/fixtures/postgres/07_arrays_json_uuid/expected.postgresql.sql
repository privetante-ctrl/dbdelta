BEGIN;

-- add column profiles.external_id uuid
ALTER TABLE "profiles" ADD COLUMN "external_id" uuid;

-- add column profiles.aliases varchar(30)[]
ALTER TABLE "profiles" ADD COLUMN "aliases" varchar(30)[];

-- add column profiles.preferences jsonb NOT NULL DEFAULT '{}'
ALTER TABLE "profiles" ADD COLUMN "preferences" jsonb NOT NULL DEFAULT '{}';

-- change type of profiles.settings from json to jsonb
ALTER TABLE "profiles" ALTER COLUMN "settings" TYPE jsonb USING "settings"::jsonb;

COMMIT;
