-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- drop table comments
-- DANGER drop-table: Dropping comments permanently deletes all of its rows.
DROP TABLE "comments";

-- rebuild table categories: SQLite cannot make these changes in place
--   drop column categories.parent_id
--   drop foreign key categories (parent_id) -> categories (id)
-- DANGER drop-column: Dropping categories.parent_id permanently deletes its value in every row.
-- WARNING sqlite-rebuild: SQLite cannot make these changes to categories in place, so the table
--   is rebuilt: a new table is created, every row is copied, the old table is dropped and the
--   new one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
CREATE TABLE "_dbdelta_new_categories" (
    "id" integer NOT NULL,
    "name" text NOT NULL,
    PRIMARY KEY ("id")
);

INSERT INTO "_dbdelta_new_categories" ("id", "name") SELECT "id", "name" FROM "categories";

DROP TABLE "categories";

ALTER TABLE "_dbdelta_new_categories" RENAME TO "categories";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
