-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rebuild table logs: SQLite cannot make these changes in place
--   add column logs.logged_at timestamp DEFAULT CURRENT_TIMESTAMP
-- WARNING sqlite-rebuild: SQLite cannot make these changes to logs in place, so the table is
--   rebuilt: a new table is created, every row is copied, the old table is dropped and the new
--   one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
CREATE TABLE "_dbdelta_new_logs" (
    "id" integer NOT NULL,
    "message" text NOT NULL,
    "logged_at" timestamp DEFAULT (CURRENT_TIMESTAMP),
    PRIMARY KEY ("id")
);

INSERT INTO "_dbdelta_new_logs" ("id", "message") SELECT "id", "message" FROM "logs";

DROP TABLE "logs";

ALTER TABLE "_dbdelta_new_logs" RENAME TO "logs";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
