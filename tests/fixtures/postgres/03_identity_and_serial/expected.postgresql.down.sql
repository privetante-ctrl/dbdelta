BEGIN;

-- drop table d
-- DANGER drop-table: Dropping d permanently deletes all of its rows.
DROP TABLE "d";

-- change identity of a.id from by default to serial
ALTER TABLE "a" ALTER COLUMN "id" DROP IDENTITY;

CREATE SEQUENCE "a_id_seq" AS integer OWNED BY "a"."id";

SELECT setval('"a_id_seq"', COALESCE(MAX("id"), 0) + 1, false) FROM "a";

ALTER TABLE "a" ALTER COLUMN "id" SET DEFAULT nextval('"a_id_seq"'::regclass);

-- change identity of b.id from always to none
ALTER TABLE "b" ALTER COLUMN "id" DROP IDENTITY;

-- change identity of c.id from none to always
ALTER TABLE "c" ALTER COLUMN "id" ADD GENERATED ALWAYS AS IDENTITY;

SELECT setval(pg_get_serial_sequence('"c"', 'id'), COALESCE(MAX("id"), 0) + 1, false) FROM "c";

COMMIT;
