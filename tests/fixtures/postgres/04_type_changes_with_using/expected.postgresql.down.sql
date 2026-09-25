BEGIN;

-- change type of measurements.flag from boolean to integer
-- IRREVERSIBLE: The up migration converted measurements.flag from integer to boolean, which may
--   have rounded, cut or reformatted values; converting back does not restore them.
-- WARNING type-rewrite: There is no automatic conversion from boolean to integer, so values are
--   converted with USING and any value that does not convert makes the migration fail. Changing
--   measurements.flag from boolean to integer makes PostgreSQL rewrite the whole table and its
--   indexes while holding an ACCESS EXCLUSIVE lock that blocks reads and writes.
ALTER TABLE "measurements" ALTER COLUMN "flag" TYPE integer USING "flag"::integer;

-- change type of measurements.payload from jsonb to json
-- IRREVERSIBLE: The up migration converted measurements.payload from json to jsonb, which may
--   have rounded, cut or reformatted values; converting back does not restore them.
-- WARNING type-rewrite: There is no automatic conversion from jsonb to json, so values are
--   converted with USING and any value that does not convert makes the migration fail. Changing
--   measurements.payload from jsonb to json makes PostgreSQL rewrite the whole table and its
--   indexes while holding an ACCESS EXCLUSIVE lock that blocks reads and writes.
ALTER TABLE "measurements" ALTER COLUMN "payload" TYPE json USING "payload"::json;

-- change type of measurements.reading from integer to text
-- IRREVERSIBLE: The up migration converted measurements.reading from text to integer, which may
--   have rounded, cut or reformatted values; converting back does not restore them.
-- WARNING type-rewrite: Changing measurements.reading from integer to text makes PostgreSQL
--   rewrite the whole table and its indexes while holding an ACCESS EXCLUSIVE lock that blocks
--   reads and writes.
ALTER TABLE "measurements" ALTER COLUMN "reading" TYPE text;

-- change type of measurements.taken from date to text
-- IRREVERSIBLE: The up migration converted measurements.taken from text to date, which may have
--   rounded, cut or reformatted values; converting back does not restore them.
-- WARNING type-rewrite: Changing measurements.taken from date to text makes PostgreSQL rewrite
--   the whole table and its indexes while holding an ACCESS EXCLUSIVE lock that blocks reads and
--   writes.
ALTER TABLE "measurements" ALTER COLUMN "taken" TYPE text;

COMMIT;
