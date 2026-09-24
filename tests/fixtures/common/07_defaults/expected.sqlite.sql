-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rebuild table settings: SQLite cannot make these changes in place
--   set default of settings.theme to 'dark'
--   set default of settings.page_size to 10
--   drop default of settings.level
--   set default of settings.created_at to CURRENT_TIMESTAMP
-- WARNING sqlite-rebuild: SQLite cannot make these changes to settings in place, so the table is
--   rebuilt: a new table is created, every row is copied, the old table is dropped and the new
--   one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
CREATE TABLE "_dbdelta_new_settings" (
    "id" integer NOT NULL,
    "theme" text DEFAULT 'dark',
    "page_size" integer DEFAULT 10,
    "level" integer,
    "created_at" timestamp DEFAULT (CURRENT_TIMESTAMP),
    PRIMARY KEY ("id")
);

INSERT INTO "_dbdelta_new_settings" ("id", "theme", "page_size", "level", "created_at") SELECT "id", "theme", "page_size", "level", "created_at" FROM "settings";

DROP TABLE "settings";

ALTER TABLE "_dbdelta_new_settings" RENAME TO "settings";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
