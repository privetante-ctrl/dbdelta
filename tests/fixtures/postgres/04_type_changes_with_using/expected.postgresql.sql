BEGIN;

-- change type of measurements.flag from integer to boolean
-- WARNING type-rewrite: There is no automatic conversion from integer to boolean, so values are
--   converted with USING and any value that does not convert makes the migration fail. Changing
--   measurements.flag from integer to boolean makes PostgreSQL rewrite the whole table and its
--   indexes while holding an ACCESS EXCLUSIVE lock that blocks reads and writes.
ALTER TABLE "measurements" ALTER COLUMN "flag" TYPE boolean USING "flag"::boolean;

-- change type of measurements.payload from json to jsonb
-- WARNING type-rewrite: There is no automatic conversion from json to jsonb, so values are
--   converted with USING and any value that does not convert makes the migration fail. Changing
--   measurements.payload from json to jsonb makes PostgreSQL rewrite the whole table and its
--   indexes while holding an ACCESS EXCLUSIVE lock that blocks reads and writes.
ALTER TABLE "measurements" ALTER COLUMN "payload" TYPE jsonb USING "payload"::jsonb;

-- change type of measurements.reading from text to integer
-- WARNING type-rewrite: There is no automatic conversion from text to integer, so values are
--   converted with USING and any value that does not convert makes the migration fail. Changing
--   measurements.reading from text to integer makes PostgreSQL rewrite the whole table and its
--   indexes while holding an ACCESS EXCLUSIVE lock that blocks reads and writes.
ALTER TABLE "measurements" ALTER COLUMN "reading" TYPE integer USING "reading"::integer;

-- change type of measurements.taken from text to date
-- WARNING type-rewrite: There is no automatic conversion from text to date, so values are
--   converted with USING and any value that does not convert makes the migration fail. Changing
--   measurements.taken from text to date makes PostgreSQL rewrite the whole table and its
--   indexes while holding an ACCESS EXCLUSIVE lock that blocks reads and writes.
ALTER TABLE "measurements" ALTER COLUMN "taken" TYPE date USING "taken"::date;

COMMIT;
