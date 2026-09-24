BEGIN;

-- change type of accounts.balance from integer to bigint
ALTER TABLE "accounts" ALTER COLUMN "balance" TYPE bigint;

-- change type of accounts.code from varchar(10) to varchar(50)
ALTER TABLE "accounts" ALTER COLUMN "code" TYPE varchar(50);

-- change type of accounts.rate from real to double precision
ALTER TABLE "accounts" ALTER COLUMN "rate" TYPE double precision;

COMMIT;
