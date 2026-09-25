BEGIN;

-- drop unique constraint products_sku_unique on products (sku)
ALTER TABLE "products" DROP CONSTRAINT "products_sku_unique";

-- add unique constraint on products (name)
-- WARNING unique-duplicates: Rows already in products may contain duplicates of (name), which
--   make adding the unique constraint fail.
ALTER TABLE "products" ADD UNIQUE ("name");

COMMIT;
