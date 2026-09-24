BEGIN;

-- drop index ix_people_email on people (email)
DROP INDEX "ix_people_email";

-- create unique index ux_people_email on people (LOWER("email")) where "deleted_at" IS NULL
-- WARNING unique-duplicates: Rows already in people may contain duplicates of (LOWER("email")),
--   which make adding the unique index fail.
CREATE UNIQUE INDEX "ux_people_email" ON "people" ((LOWER("email"))) WHERE "deleted_at" IS NULL;

COMMIT;
