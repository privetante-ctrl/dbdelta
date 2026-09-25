BEGIN;

-- drop column posts.priority
-- DANGER drop-column: Dropping posts.priority permanently deletes its value in every row.
ALTER TABLE "posts" DROP COLUMN "priority";

-- recreate enum type post_status with values ('draft', 'published')
-- DANGER enum-values: Values 'review', 'archived' are removed from post_status; rows that still
--   hold them make the conversion fail. PostgreSQL cannot remove or reorder enum values, so the
--   type is recreated and every column using it is converted, rewriting those tables under an
--   ACCESS EXCLUSIVE lock that blocks reads and writes.
ALTER TYPE "post_status" RENAME TO "post_status__dbdelta_old";

CREATE TYPE "post_status" AS ENUM ('draft', 'published');

ALTER TABLE "posts" ALTER COLUMN "status" DROP DEFAULT;

ALTER TABLE "posts" ALTER COLUMN "status" TYPE "post_status" USING "status"::text::"post_status";

ALTER TABLE "posts" ALTER COLUMN "status" SET DEFAULT 'draft';

DROP TYPE "post_status__dbdelta_old";

-- set default of posts.status to 'draft'
ALTER TABLE "posts" ALTER COLUMN "status" SET DEFAULT 'draft';

-- drop enum type priority
DROP TYPE "priority";

COMMIT;
