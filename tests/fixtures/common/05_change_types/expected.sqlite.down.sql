-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rebuild table accounts: SQLite cannot make these changes in place
--   change type of accounts.balance from bigint to integer
--   change type of accounts.code from varchar(50) to varchar(10)
--   change type of accounts.rate from double precision to real
-- IRREVERSIBLE: The up migration converted accounts.rate from real to double precision, which
--   may have rounded, cut or reformatted values; converting back does not restore them.
-- WARNING sqlite-rebuild: SQLite cannot make these changes to accounts in place, so the table is
--   rebuilt: a new table is created, every row is copied, the old table is dropped and the new
--   one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
-- INFO narrowing-type: accounts.balance changes from bigint to the narrower integer. SQLite does
--   not enforce declared lengths or ranges, so stored values stay as they are.
-- INFO narrowing-type: accounts.code changes from varchar(50) to the narrower varchar(10).
--   SQLite does not enforce declared lengths or ranges, so stored values stay as they are.
-- INFO narrowing-type: accounts.rate changes from double precision to the narrower real. SQLite
--   does not enforce declared lengths or ranges, so stored values stay as they are.
CREATE TABLE "_dbdelta_new_accounts" (
    "id" integer NOT NULL,
    "balance" integer NOT NULL,
    "code" varchar(10),
    "rate" real,
    PRIMARY KEY ("id")
);

INSERT INTO "_dbdelta_new_accounts" ("id", "balance", "code", "rate") SELECT "id", "balance", "code", "rate" FROM "accounts";

DROP TABLE "accounts";

ALTER TABLE "_dbdelta_new_accounts" RENAME TO "accounts";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
