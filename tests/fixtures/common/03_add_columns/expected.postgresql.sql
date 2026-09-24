BEGIN;

-- add column users.nickname text
ALTER TABLE "users" ADD COLUMN "nickname" text;

-- add column users.active boolean NOT NULL DEFAULT TRUE
ALTER TABLE "users" ADD COLUMN "active" boolean NOT NULL DEFAULT TRUE;

-- add column users.score integer DEFAULT 0
ALTER TABLE "users" ADD COLUMN "score" integer DEFAULT 0;

COMMIT;
