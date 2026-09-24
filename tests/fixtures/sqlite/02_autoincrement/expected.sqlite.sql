-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rebuild table events: SQLite cannot make these changes in place
--   change identity of events.id from none to autoincrement
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
