BEGIN;

-- change type of measurements.flag from integer to boolean
ALTER TABLE "measurements" ALTER COLUMN "flag" TYPE boolean USING "flag"::boolean;

-- change type of measurements.payload from json to jsonb
ALTER TABLE "measurements" ALTER COLUMN "payload" TYPE jsonb USING "payload"::jsonb;

-- change type of measurements.reading from text to integer
ALTER TABLE "measurements" ALTER COLUMN "reading" TYPE integer USING "reading"::integer;

-- change type of measurements.taken from text to date
ALTER TABLE "measurements" ALTER COLUMN "taken" TYPE date USING "taken"::date;

COMMIT;
