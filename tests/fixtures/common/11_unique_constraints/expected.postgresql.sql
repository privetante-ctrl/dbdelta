BEGIN;

-- drop unique constraint on products (name)
ALTER TABLE "products" DROP CONSTRAINT "products_name_key";

-- add unique constraint products_sku_unique on products (sku)
-- WARNING unique-duplicates: Rows already in products may contain duplicates of (sku), which
--   make adding the unique constraint fail.
ALTER TABLE "products" ADD CONSTRAINT "products_sku_unique" UNIQUE ("sku");

COMMIT;
