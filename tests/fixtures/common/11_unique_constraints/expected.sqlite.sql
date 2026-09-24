-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rebuild table products: SQLite cannot make these changes in place
--   drop unique constraint on products (name)
--   add unique constraint products_sku_unique on products (sku)
CREATE TABLE "_dbdelta_new_products" (
    "id" integer NOT NULL,
    "sku" text NOT NULL,
    "name" text NOT NULL,
    PRIMARY KEY ("id"),
    CONSTRAINT "products_sku_unique" UNIQUE ("sku")
);

INSERT INTO "_dbdelta_new_products" ("id", "sku", "name") SELECT "id", "sku", "name" FROM "products";

DROP TABLE "products";

ALTER TABLE "_dbdelta_new_products" RENAME TO "products";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
