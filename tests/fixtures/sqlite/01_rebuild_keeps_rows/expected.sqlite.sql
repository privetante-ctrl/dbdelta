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
-- WARNING check-violations: Rows already in items may violate CHECK ("price" >= 0), which makes
--   the migration fail.
-- WARNING set-not-null: Making items.name NOT NULL fails if any row holds NULL.
-- WARNING set-not-null: Making items.price NOT NULL fails if any row holds NULL.
-- WARNING sqlite-rebuild: SQLite cannot make these changes to items in place, so the table is
--   rebuilt: a new table is created, every row is copied, the old table is dropped and the new
--   one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
-- WARNING unique-duplicates: Rows already in items may contain duplicates of (name), which make
--   adding the unique constraint fail.
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
