-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rebuild table contacts: SQLite cannot make these changes in place
--   make contacts.email NOT NULL
--   allow NULL in contacts.phone
CREATE TABLE "_dbdelta_new_contacts" (
    "id" integer NOT NULL,
    "email" varchar(255) NOT NULL,
    "phone" text,
    PRIMARY KEY ("id")
);

INSERT INTO "_dbdelta_new_contacts" ("id", "email", "phone") SELECT "id", "email", "phone" FROM "contacts";

DROP TABLE "contacts";

ALTER TABLE "_dbdelta_new_contacts" RENAME TO "contacts";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
