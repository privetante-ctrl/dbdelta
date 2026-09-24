BEGIN;

-- drop primary key on memberships (user_id)
ALTER TABLE "memberships" DROP CONSTRAINT "memberships_pkey";

-- add primary key on memberships (user_id, group_id)
ALTER TABLE "memberships" ADD PRIMARY KEY ("user_id", "group_id");

-- add primary key on tags (name)
ALTER TABLE "tags" ADD PRIMARY KEY ("name");

COMMIT;
