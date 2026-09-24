BEGIN;

-- drop primary key on memberships (user_id)
ALTER TABLE "memberships" DROP CONSTRAINT "memberships_pkey";

-- add primary key on memberships (user_id, group_id)
-- WARNING unique-duplicates: Rows already in memberships may contain duplicates of (user_id,
--   group_id), which make adding the primary key fail.
ALTER TABLE "memberships" ADD PRIMARY KEY ("user_id", "group_id");

-- add primary key on tags (name)
-- WARNING unique-duplicates: Rows already in tags may contain duplicates of (name), which make
--   adding the primary key fail.
ALTER TABLE "tags" ADD PRIMARY KEY ("name");

COMMIT;
