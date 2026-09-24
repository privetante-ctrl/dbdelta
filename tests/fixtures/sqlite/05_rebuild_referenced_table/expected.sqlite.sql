-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rebuild table owners: SQLite cannot make these changes in place
--   make owners.name NOT NULL
-- WARNING set-not-null: Making owners.name NOT NULL fails if any row holds NULL.
-- WARNING sqlite-rebuild: SQLite cannot make these changes to owners in place, so the table is
--   rebuilt: a new table is created, every row is copied, the old table is dropped and the new
--   one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
CREATE TABLE "_dbdelta_new_owners" (
    "id" integer NOT NULL,
    "name" text NOT NULL,
    PRIMARY KEY ("id")
);

INSERT INTO "_dbdelta_new_owners" ("id", "name") SELECT "id", "name" FROM "owners";

DROP TABLE "owners";

ALTER TABLE "_dbdelta_new_owners" RENAME TO "owners";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
