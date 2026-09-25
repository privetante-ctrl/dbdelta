BEGIN;

-- change type of accounts.balance from bigint to integer
-- DANGER narrowing-type: accounts.balance changes from bigint to the narrower integer. Values
--   outside the range of integer make the migration fail.
-- WARNING type-rewrite: Changing accounts.balance from bigint to integer makes PostgreSQL
--   rewrite the whole table and its indexes while holding an ACCESS EXCLUSIVE lock that blocks
--   reads and writes.
ALTER TABLE "accounts" ALTER COLUMN "balance" TYPE integer;

-- change type of accounts.code from varchar(50) to varchar(10)
-- DANGER narrowing-type: accounts.code changes from varchar(50) to the narrower varchar(10).
--   Values longer than 10 characters make the migration fail.
-- WARNING type-rewrite: Changing accounts.code from varchar(50) to varchar(10) makes PostgreSQL
--   rewrite the whole table and its indexes while holding an ACCESS EXCLUSIVE lock that blocks
--   reads and writes.
ALTER TABLE "accounts" ALTER COLUMN "code" TYPE varchar(10);

-- change type of accounts.rate from double precision to real
-- IRREVERSIBLE: The up migration converted accounts.rate from real to double precision, which
--   may have rounded, cut or reformatted values; converting back does not restore them.
-- DANGER narrowing-type: accounts.rate changes from double precision to the narrower real.
--   Values that do not fit make the migration fail, and digits beyond the new precision are
--   rounded away.
-- WARNING type-rewrite: Changing accounts.rate from double precision to real makes PostgreSQL
--   rewrite the whole table and its indexes while holding an ACCESS EXCLUSIVE lock that blocks
--   reads and writes.
ALTER TABLE "accounts" ALTER COLUMN "rate" TYPE real;

COMMIT;
