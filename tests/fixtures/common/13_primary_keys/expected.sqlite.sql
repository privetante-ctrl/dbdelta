-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rebuild table memberships: SQLite cannot make these changes in place
--   drop primary key on memberships (user_id)
--   add primary key on memberships (user_id, group_id)
CREATE TABLE "_dbdelta_new_memberships" (
    "user_id" integer NOT NULL,
    "group_id" integer NOT NULL,
    PRIMARY KEY ("user_id", "group_id")
);

INSERT INTO "_dbdelta_new_memberships" ("user_id", "group_id") SELECT "user_id", "group_id" FROM "memberships";

DROP TABLE "memberships";

ALTER TABLE "_dbdelta_new_memberships" RENAME TO "memberships";

-- rebuild table tags: SQLite cannot make these changes in place
--   add primary key on tags (name)
CREATE TABLE "_dbdelta_new_tags" (
    "name" text NOT NULL,
    "label" text,
    PRIMARY KEY ("name")
);

INSERT INTO "_dbdelta_new_tags" ("name", "label") SELECT "name", "label" FROM "tags";

DROP TABLE "tags";

ALTER TABLE "_dbdelta_new_tags" RENAME TO "tags";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
