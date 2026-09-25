### dbdelta: 10 changes, 10 risks: 3 danger, 7 warning.

❌ **Check failed: 3 dangerous changes. Review them, then rerun with --allow-destructive to accept them.**

From `current.sql` to `desired.sql` (postgresql).

| # | Change | Risk |
|--:|--------|------|
| 1 | rename column orders.created to created\_at | 🟠 warning |
| 2 | change values of enum type order\_status from ('new', 'paid', 'shipped') to ('new', 'paid', 'shipped', 'refunded') |  |
| 3 | drop column customers.phone | 🔴 danger |
| 4 | add column customers.loyalty\_tier text NOT NULL | 🔴 danger |
| 5 | change type of customers.email from varchar(255) to varchar(120) | 🔴 danger |
| 6 | create unique index ux\_customers\_email on customers (LOWER("email")) | 🟠 warning |
| 7 | drop foreign key order\_items (product\_id) -> products (id) |  |
| 8 | add foreign key order\_items (product\_id) -> products (id) ON DELETE RESTRICT | 🟠 warning |
| 9 | add check constraint on order\_items ("quantity" > 0) | 🟠 warning |
| 10 | create index ix\_orders\_customer on orders (customer\_id) | 🟠 warning |

#### Risks

- 🔴 **danger** `narrowing-type` on customers.email

  customers.email changes from varchar(255) to the narrower varchar(120). Values longer than 120 characters make the migration fail.

  **Safer:** Check the data with the query below and clean up values that do not fit, or keep the wider type.

  <details>
  <summary>Check before migrating</summary>

  ```sql
  SELECT count(*) FROM "customers" WHERE length("customers"."email") > 120
  ```
  </details>

- 🔴 **danger** `add-not-null-column` on customers.loyalty\_tier

  customers.loyalty\_tier is added as NOT NULL without a default, which fails as soon as customers holds any row: existing rows would have no value.

  **Safer:** Add the column as nullable or with a DEFAULT, fill it for existing rows, then make it NOT NULL in a later step. In PostgreSQL 11 and later, ADD COLUMN with a constant DEFAULT is instant.

  <details>
  <summary>Check before migrating</summary>

  ```sql
  SELECT count(*) FROM "customers"
  ```
  </details>

- 🔴 **danger** `drop-column` on customers.phone

  Dropping customers.phone permanently deletes its value in every row.

  **Safer:** Stop reading and writing the column in the application and deploy that first, back the values up, then drop the column in a later migration (expand and contract).

  <details>
  <summary>Check before migrating</summary>

  ```sql
  SELECT count(*) FROM "customers" WHERE "customers"."phone" IS NOT NULL
  ```
  </details>

- 🟠 **warning** `check-violations` on check on order\_items ("quantity" > 0)

  Rows already in order\_items may violate CHECK ("quantity" > 0), which makes the migration fail. PostgreSQL checks every row while holding an ACCESS EXCLUSIVE lock that blocks reads and writes.

  **Safer:** Fix the violating rows first. On a large table, add the constraint with NOT VALID and run ALTER TABLE ... VALIDATE CONSTRAINT separately; validating does not block writes.

  <details>
  <summary>Check before migrating</summary>

  ```sql
  SELECT count(*) FROM "order_items" WHERE NOT ("quantity" > 0)
  ```
  </details>

- 🟠 **warning** `rename` on column orders.created

  Renaming column orders.created to created\_at keeps its data, but application code, views, functions and triggers that still use the old name fail. The database updates keys, indexes and foreign keys itself.

  **Safer:** Deploy application code that accepts both names first, or rename in steps: add the new column, write to both, backfill, switch reads, then drop the old one.

- 🟠 **warning** `type-rewrite` on customers.email

  Changing customers.email from varchar(255) to varchar(120) makes PostgreSQL rewrite the whole table and its indexes while holding an ACCESS EXCLUSIVE lock that blocks reads and writes.

  **Safer:** On a large table, add a new column of the new type, backfill it in batches, switch the application over and drop the old column; otherwise run the migration in a maintenance window.

- 🟠 **warning** `foreign-key` on foreign key order\_items (product\_id) -> products

  Adding the foreign key checks every row of order\_items while holding SHARE ROW EXCLUSIVE locks on order\_items and products, which block writes to both; rows without a match make the migration fail.

  **Safer:** Add the constraint with NOT VALID, which only takes a brief lock, then run ALTER TABLE ... VALIDATE CONSTRAINT in a separate transaction; validating does not block writes.

  <details>
  <summary>Check before migrating</summary>

  ```sql
  SELECT count(*) FROM "order_items" AS child WHERE child."product_id" IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "products" AS parent WHERE parent."id" = child."product_id")
  ```
  </details>

- 🟠 **warning** `index-lock` on index ix\_orders\_customer on orders

  Building ix\_orders\_customer blocks inserts, updates and deletes on orders (SHARE lock) until the whole table has been indexed.

  **Safer:** Run with --concurrent-indexes to build it with CREATE INDEX CONCURRENTLY outside the transaction: it takes longer but does not block writes.

- 🟠 **warning** `index-lock` on index ux\_customers\_email on customers

  Building ux\_customers\_email blocks inserts, updates and deletes on customers (SHARE lock) until the whole table has been indexed.

  **Safer:** Run with --concurrent-indexes to build it with CREATE INDEX CONCURRENTLY outside the transaction: it takes longer but does not block writes.

- 🟠 **warning** `unique-duplicates` on unique index on customers (LOWER("email"))

  Rows already in customers may contain duplicates of (LOWER("email")), which make adding the unique index fail.

  **Safer:** Remove the duplicates first.

  <details>
  <summary>Check before migrating</summary>

  ```sql
  SELECT LOWER("email"), count(*) FROM "customers" WHERE LOWER("email") IS NOT NULL GROUP BY LOWER("email") HAVING count(*) > 1
  ```
  </details>

<details>
<summary>Migration SQL</summary>

```sql
-- Migration from current.sql to desired.sql (postgresql), generated by dbdelta 0.1.0.dev0.
-- 10 changes, 10 risks: 3 danger, 7 warning.
-- Read the comments marked DANGER, WARNING and INFO before running it.

-- New enum values are committed first: PostgreSQL cannot use an enum value in the
-- transaction that added it.
BEGIN;

-- change values of enum type order_status from ('new', 'paid', 'shipped') to ('new', 'paid', 'shipped', 'refunded')
ALTER TYPE "order_status" ADD VALUE 'refunded' AFTER 'shipped';

COMMIT;

BEGIN;

-- rename column orders.created to created_at
-- WARNING rename: Renaming column orders.created to created_at keeps its data, but application
--   code, views, functions and triggers that still use the old name fail. The database updates
--   keys, indexes and foreign keys itself.
ALTER TABLE "orders" RENAME COLUMN "created" TO "created_at";

-- drop foreign key order_items (product_id) -> products (id)
ALTER TABLE "order_items" DROP CONSTRAINT "order_items_product_id_fkey";

-- drop column customers.phone
-- DANGER drop-column: Dropping customers.phone permanently deletes its value in every row.
ALTER TABLE "customers" DROP COLUMN "phone";

-- add column customers.loyalty_tier text NOT NULL
-- DANGER add-not-null-column: customers.loyalty_tier is added as NOT NULL without a default,
--   which fails as soon as customers holds any row: existing rows would have no value.
ALTER TABLE "customers" ADD COLUMN "loyalty_tier" text NOT NULL;

-- change type of customers.email from varchar(255) to varchar(120)
-- DANGER narrowing-type: customers.email changes from varchar(255) to the narrower varchar(120).
--   Values longer than 120 characters make the migration fail.
-- WARNING type-rewrite: Changing customers.email from varchar(255) to varchar(120) makes
--   PostgreSQL rewrite the whole table and its indexes while holding an ACCESS EXCLUSIVE lock
--   that blocks reads and writes.
ALTER TABLE "customers" ALTER COLUMN "email" TYPE varchar(120);

-- add check constraint on order_items ("quantity" > 0)
-- WARNING check-violations: Rows already in order_items may violate CHECK ("quantity" > 0),
--   which makes the migration fail. PostgreSQL checks every row while holding an ACCESS
--   EXCLUSIVE lock that blocks reads and writes.
ALTER TABLE "order_items" ADD CHECK ("quantity" > 0);

-- create unique index ux_customers_email on customers (LOWER("email"))
-- WARNING index-lock: Building ux_customers_email blocks inserts, updates and deletes on
--   customers (SHARE lock) until the whole table has been indexed.
-- WARNING unique-duplicates: Rows already in customers may contain duplicates of
--   (LOWER("email")), which make adding the unique index fail.
CREATE UNIQUE INDEX "ux_customers_email" ON "customers" ((LOWER("email")));

-- create index ix_orders_customer on orders (customer_id)
-- WARNING index-lock: Building ix_orders_customer blocks inserts, updates and deletes on orders
--   (SHARE lock) until the whole table has been indexed.
CREATE INDEX "ix_orders_customer" ON "orders" ("customer_id");

-- add foreign key order_items (product_id) -> products (id) ON DELETE RESTRICT
-- WARNING foreign-key: Adding the foreign key checks every row of order_items while holding
--   SHARE ROW EXCLUSIVE locks on order_items and products, which block writes to both; rows
--   without a match make the migration fail.
ALTER TABLE "order_items" ADD FOREIGN KEY ("product_id") REFERENCES "products" ("id") ON DELETE RESTRICT;

COMMIT;
```
</details>
