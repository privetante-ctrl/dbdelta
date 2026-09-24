-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- create table comments
CREATE TABLE "comments" (
    "id" integer NOT NULL,
    "reply_to" integer,
    "body" text NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("reply_to") REFERENCES "comments" ("id")
);

-- rebuild table categories: SQLite cannot make these changes in place
--   add column categories.parent_id integer
--   add foreign key categories (parent_id) -> categories (id)
CREATE TABLE "_dbdelta_new_categories" (
    "id" integer NOT NULL,
    "name" text NOT NULL,
    "parent_id" integer,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("parent_id") REFERENCES "categories" ("id")
);

INSERT INTO "_dbdelta_new_categories" ("id", "name") SELECT "id", "name" FROM "categories";

DROP TABLE "categories";

ALTER TABLE "_dbdelta_new_categories" RENAME TO "categories";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
