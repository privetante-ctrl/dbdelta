BEGIN;

-- recreate enum type mood with values ('sad', 'meh', 'ok', 'happy')
-- WARNING enum-values: Reordering the values of mood changes how they sort and compare.
--   PostgreSQL cannot remove or reorder enum values, so the type is recreated and every column
--   using it is converted, rewriting those tables under an ACCESS EXCLUSIVE lock that blocks
--   reads and writes.
ALTER TYPE "mood" RENAME TO "mood__dbdelta_old";

CREATE TYPE "mood" AS ENUM ('sad', 'meh', 'ok', 'happy');

ALTER TABLE "entries" ALTER COLUMN "mood" DROP DEFAULT;

ALTER TABLE "entries" ALTER COLUMN "mood" TYPE "mood" USING "mood"::text::"mood";

ALTER TABLE "entries" ALTER COLUMN "mood" SET DEFAULT 'ok';

ALTER TABLE "entries" ALTER COLUMN "history" TYPE "mood"[] USING "history"::text[]::"mood"[];

DROP TYPE "mood__dbdelta_old";

COMMIT;
