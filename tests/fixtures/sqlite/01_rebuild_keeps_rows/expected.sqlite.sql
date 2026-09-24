-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rebuild table items: SQLite cannot make these changes in place
--   make items.name NOT NULL
--   change type of items.price from integer to real
--   set default of items.price to 0
--   make items.price NOT NULL
--   add unique constraint on items (name)
--   add check constraint on items ("price" >= 0)
--   drop index ix_items_name on items (name)
--   create index ix_items_name on items (name DESC)
CREATE TABLE "_dbdelta_new_items" (
    "id" integer NOT NULL,
    "name" text NOT NULL,
    "price" real NOT NULL DEFAULT 0,
    "note" text,
    PRIMARY KEY ("id"),
    UNIQUE ("name"),
    CHECK ("price" >= 0)
);

INSERT INTO "_dbdelta_new_items" ("id", "name", "price", "note") SELECT "id", "name", "price", "note" FROM "items";

DROP TABLE "items";

ALTER TABLE "_dbdelta_new_items" RENAME TO "items";

CREATE INDEX "ix_items_name" ON "items" ("name" DESC);

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
