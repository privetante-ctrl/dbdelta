-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rebuild table products: SQLite cannot make these changes in place
--   drop unique constraint products_sku_unique on products (sku)
--   add unique constraint on products (name)
-- WARNING sqlite-rebuild: SQLite cannot make these changes to products in place, so the table is
--   rebuilt: a new table is created, every row is copied, the old table is dropped and the new
--   one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
-- WARNING unique-duplicates: Rows already in products may contain duplicates of (name), which
--   make adding the unique constraint fail.
CREATE TABLE "_dbdelta_new_products" (
    "id" integer NOT NULL,
    "sku" text NOT NULL,
    "name" text NOT NULL,
    PRIMARY KEY ("id"),
    UNIQUE ("name")
);

INSERT INTO "_dbdelta_new_products" ("id", "sku", "name") SELECT "id", "sku", "name" FROM "products";

DROP TABLE "products";

ALTER TABLE "_dbdelta_new_products" RENAME TO "products";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
