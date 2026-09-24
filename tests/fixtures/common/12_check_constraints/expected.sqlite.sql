-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rebuild table orders: SQLite cannot make these changes in place
--   drop check constraint on orders ("quantity" > 0)
--   add check constraint orders_price_positive on orders ("price" > 0)
--   add check constraint on orders ("quantity" >= 0)
CREATE TABLE "_dbdelta_new_orders" (
    "id" integer NOT NULL,
    "quantity" integer NOT NULL,
    "price" numeric(10,2) NOT NULL,
    PRIMARY KEY ("id"),
    CONSTRAINT "orders_price_positive" CHECK ("price" > 0),
    CHECK ("quantity" >= 0)
);

INSERT INTO "_dbdelta_new_orders" ("id", "quantity", "price") SELECT "id", "quantity", "price" FROM "orders";

DROP TABLE "orders";

ALTER TABLE "_dbdelta_new_orders" RENAME TO "orders";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
