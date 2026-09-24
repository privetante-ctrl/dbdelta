-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rebuild table accounts: SQLite cannot make these changes in place
--   change type of accounts.balance from integer to bigint
--   change type of accounts.code from varchar(10) to varchar(50)
--   change type of accounts.rate from real to double precision
CREATE TABLE "_dbdelta_new_accounts" (
    "id" integer NOT NULL,
    "balance" bigint NOT NULL,
    "code" varchar(50),
    "rate" double precision,
    PRIMARY KEY ("id")
);

INSERT INTO "_dbdelta_new_accounts" ("id", "balance", "code", "rate") SELECT "id", "balance", "code", "rate" FROM "accounts";

DROP TABLE "accounts";

ALTER TABLE "_dbdelta_new_accounts" RENAME TO "accounts";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
