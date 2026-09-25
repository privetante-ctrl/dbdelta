BEGIN;

-- drop primary key on memberships (user_id, group_id)
ALTER TABLE "memberships" DROP CONSTRAINT "memberships_pkey";

-- drop primary key on tags (name)
ALTER TABLE "tags" DROP CONSTRAINT "tags_pkey";

-- add primary key on memberships (user_id)
-- WARNING unique-duplicates: Rows already in memberships may contain duplicates of (user_id),
--   which make adding the primary key fail.
ALTER TABLE "memberships" ADD PRIMARY KEY ("user_id");

COMMIT;
