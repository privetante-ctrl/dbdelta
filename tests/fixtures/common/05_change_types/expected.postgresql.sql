BEGIN;

-- change type of accounts.balance from integer to bigint
-- WARNING type-rewrite: Changing accounts.balance from integer to bigint makes PostgreSQL
--   rewrite the whole table and its indexes while holding an ACCESS EXCLUSIVE lock that blocks
--   reads and writes.
ALTER TABLE "accounts" ALTER COLUMN "balance" TYPE bigint;

-- change type of accounts.code from varchar(10) to varchar(50)
ALTER TABLE "accounts" ALTER COLUMN "code" TYPE varchar(50);

-- change type of accounts.rate from real to double precision
-- WARNING type-rewrite: Changing accounts.rate from real to double precision makes PostgreSQL
--   rewrite the whole table and its indexes while holding an ACCESS EXCLUSIVE lock that blocks
--   reads and writes.
ALTER TABLE "accounts" ALTER COLUMN "rate" TYPE double precision;

COMMIT;
