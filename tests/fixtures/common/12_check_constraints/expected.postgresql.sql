BEGIN;

-- drop check constraint on orders ("quantity" > 0)
ALTER TABLE "orders" DROP CONSTRAINT "orders_quantity_check";

-- add check constraint on orders ("quantity" >= 0)
ALTER TABLE "orders" ADD CHECK ("quantity" >= 0);

-- add check constraint orders_price_positive on orders ("price" > 0)
ALTER TABLE "orders" ADD CONSTRAINT "orders_price_positive" CHECK ("price" > 0);

COMMIT;
