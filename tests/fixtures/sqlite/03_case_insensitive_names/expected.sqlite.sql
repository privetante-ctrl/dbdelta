BEGIN;

-- add column Users.name text
ALTER TABLE "Users" ADD COLUMN "name" text;

COMMIT;
