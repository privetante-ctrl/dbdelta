BEGIN;

-- drop check constraint on orders ("quantity" > 0)
ALTER TABLE "orders" DROP CONSTRAINT "orders_quantity_check";

-- add check constraint on orders ("quantity" >= 0)
-- WARNING check-violations: Rows already in orders may violate CHECK ("quantity" >= 0), which
--   makes the migration fail. PostgreSQL checks every row while holding an ACCESS EXCLUSIVE lock
--   that blocks reads and writes.
ALTER TABLE "orders" ADD CHECK ("quantity" >= 0);

-- add check constraint orders_price_positive on orders ("price" > 0)
-- WARNING check-violations: Rows already in orders may violate CHECK ("price" > 0), which makes
--   the migration fail. PostgreSQL checks every row while holding an ACCESS EXCLUSIVE lock that
--   blocks reads and writes.
ALTER TABLE "orders" ADD CONSTRAINT "orders_price_positive" CHECK ("price" > 0);

COMMIT;
