BEGIN;

-- drop foreign key orders (customer_id) -> customers (id)
ALTER TABLE "orders" DROP CONSTRAINT "orders_customer_id_fkey";

-- drop primary key customers_pk on customers (id)
ALTER TABLE "customers" DROP CONSTRAINT "customers_pk";

-- add primary key customers_pkey on customers (id)
-- WARNING unique-duplicates: Rows already in customers may contain duplicates of (id), which
--   make adding the primary key fail.
ALTER TABLE "customers" ADD CONSTRAINT "customers_pkey" PRIMARY KEY ("id");

-- add foreign key orders (customer_id) -> customers (id)
ALTER TABLE "orders" ADD FOREIGN KEY ("customer_id") REFERENCES "customers" ("id");

COMMIT;
