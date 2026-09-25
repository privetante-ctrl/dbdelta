BEGIN;

-- drop unique index ux_people_email on people (LOWER("email")) where "deleted_at" IS NULL
DROP INDEX "ux_people_email";

-- create index ix_people_email on people (email)
CREATE INDEX "ix_people_email" ON "people" ("email");

COMMIT;
