BEGIN;

-- drop index ix_people_email on people (email)
DROP INDEX "ix_people_email";

-- create unique index ux_people_email on people (LOWER("email")) where "deleted_at" IS NULL
CREATE UNIQUE INDEX "ux_people_email" ON "people" ((LOWER("email"))) WHERE "deleted_at" IS NULL;

COMMIT;
