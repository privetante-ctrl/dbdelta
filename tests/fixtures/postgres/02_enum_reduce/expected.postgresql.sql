BEGIN;

-- recreate enum type mood with values ('happy', 'ok', 'sad')
-- DANGER enum-values: Value 'meh' is removed from mood; rows that still hold them make the
--   conversion fail. PostgreSQL cannot remove or reorder enum values, so the type is recreated
--   and every column using it is converted, rewriting those tables under an ACCESS EXCLUSIVE
--   lock that blocks reads and writes.
ALTER TYPE "mood" RENAME TO "mood__dbdelta_old";

CREATE TYPE "mood" AS ENUM ('happy', 'ok', 'sad');

ALTER TABLE "entries" ALTER COLUMN "mood" DROP DEFAULT;

ALTER TABLE "entries" ALTER COLUMN "mood" TYPE "mood" USING "mood"::text::"mood";

ALTER TABLE "entries" ALTER COLUMN "mood" SET DEFAULT 'ok';

ALTER TABLE "entries" ALTER COLUMN "history" TYPE "mood"[] USING "history"::text[]::"mood"[];

DROP TYPE "mood__dbdelta_old";

COMMIT;
