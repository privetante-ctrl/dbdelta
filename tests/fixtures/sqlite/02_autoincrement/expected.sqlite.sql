-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rebuild table events: SQLite cannot make these changes in place
--   change identity of events.id from none to autoincrement
-- WARNING sqlite-rebuild: SQLite cannot make these changes to events in place, so the table is
--   rebuilt: a new table is created, every row is copied, the old table is dropped and the new
--   one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
CREATE TABLE "_dbdelta_new_events" (
    "id" integer NOT NULL PRIMARY KEY AUTOINCREMENT,
    "kind" text NOT NULL
);

INSERT INTO "_dbdelta_new_events" ("id", "kind") SELECT "id", "kind" FROM "events";

DROP TABLE "events";

ALTER TABLE "_dbdelta_new_events" RENAME TO "events";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
