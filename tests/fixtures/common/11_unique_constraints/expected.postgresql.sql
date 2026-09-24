BEGIN;

-- drop unique constraint on products (name)
ALTER TABLE "products" DROP CONSTRAINT "products_name_key";

-- add unique constraint products_sku_unique on products (sku)
ALTER TABLE "products" ADD CONSTRAINT "products_sku_unique" UNIQUE ("sku");

COMMIT;
