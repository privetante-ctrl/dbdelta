-- New enum values are committed first: PostgreSQL cannot use an enum value in the
-- transaction that added it.
BEGIN;

-- change values of enum type post_status from ('draft', 'published') to ('draft', 'review', 'published', 'archived')
ALTER TYPE "post_status" ADD VALUE 'review' AFTER 'draft';

ALTER TYPE "post_status" ADD VALUE 'archived' AFTER 'published';

COMMIT;

BEGIN;

-- create enum type priority ('low', 'high')
CREATE TYPE "priority" AS ENUM ('low', 'high');

-- add column posts.priority priority NOT NULL DEFAULT 'low'
ALTER TABLE "posts" ADD COLUMN "priority" "priority" NOT NULL DEFAULT 'low';

-- set default of posts.status to 'review'
ALTER TABLE "posts" ALTER COLUMN "status" SET DEFAULT 'review';

COMMIT;
