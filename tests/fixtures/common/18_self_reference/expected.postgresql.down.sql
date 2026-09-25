BEGIN;

-- drop foreign key categories (parent_id) -> categories (id)
ALTER TABLE "categories" DROP CONSTRAINT "categories_parent_id_fkey";

-- drop column categories.parent_id
-- DANGER drop-column: Dropping categories.parent_id permanently deletes its value in every row.
ALTER TABLE "categories" DROP COLUMN "parent_id";

-- drop table comments
-- DANGER drop-table: Dropping comments permanently deletes all of its rows.
DROP TABLE "comments";

COMMIT;
