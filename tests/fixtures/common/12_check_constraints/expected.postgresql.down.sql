BEGIN;

-- drop check constraint on orders ("quantity" >= 0)
ALTER TABLE "orders" DROP CONSTRAINT "orders_quantity_check";

-- drop check constraint orders_price_positive on orders ("price" > 0)
ALTER TABLE "orders" DROP CONSTRAINT "orders_price_positive";

-- add check constraint on orders ("quantity" > 0)
-- WARNING check-violations: Rows already in orders may violate CHECK ("quantity" > 0), which
--   makes the migration fail. PostgreSQL checks every row while holding an ACCESS EXCLUSIVE lock
--   that blocks reads and writes.
ALTER TABLE "orders" ADD CHECK ("quantity" > 0);

COMMIT;
