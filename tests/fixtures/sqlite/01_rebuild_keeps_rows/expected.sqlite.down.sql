-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rebuild table items: SQLite cannot make these changes in place
--   allow NULL in items.name
--   change type of items.price from real to integer
--   drop default of items.price
--   allow NULL in items.price
--   drop unique constraint on items (name)
--   drop check constraint on items ("price" >= 0)
--   drop index ix_items_name on items (name DESC)
--   create index ix_items_name on items (name)
-- IRREVERSIBLE: The up migration converted items.price from integer to real, which may have
--   rounded, cut or reformatted values; converting back does not restore them.
-- WARNING sqlite-rebuild: SQLite cannot make these changes to items in place, so the table is
--   rebuilt: a new table is created, every row is copied, the old table is dropped and the new
--   one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
-- INFO narrowing-type: items.price changes from real to the narrower integer. SQLite does not
--   enforce declared lengths or ranges, so stored values stay as they are.
CREATE TABLE "_dbdelta_new_items" (
    "id" integer NOT NULL,
    "name" text,
    "price" integer,
    "note" text,
    PRIMARY KEY ("id")
);

INSERT INTO "_dbdelta_new_items" ("id", "name", "price", "note") SELECT "id", "name", "price", "note" FROM "items";

DROP TABLE "items";

ALTER TABLE "_dbdelta_new_items" RENAME TO "items";

CREATE INDEX "ix_items_name" ON "items" ("name");

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
