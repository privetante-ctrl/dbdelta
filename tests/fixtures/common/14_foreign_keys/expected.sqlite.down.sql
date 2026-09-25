-- Foreign keys are switched off while tables are rebuilt or dropped, as SQLite's
-- documented procedure for schema changes requires. PRAGMA foreign_keys has no
-- effect inside a transaction, so it is set outside of it.

PRAGMA foreign_keys = OFF;

BEGIN;

-- rebuild table books: SQLite cannot make these changes in place
--   drop foreign key books (author_id) -> authors (id) ON DELETE CASCADE
--   add foreign key books (author_id) -> authors (id)
-- WARNING foreign-key: SQLite does not check existing rows of books when a foreign key is added.
--   The migration runs PRAGMA foreign_key_check, which lists rows without a match but does not
--   stop the migration.
-- WARNING sqlite-rebuild: SQLite cannot make these changes to books in place, so the table is
--   rebuilt: a new table is created, every row is copied, the old table is dropped and the new
--   one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
CREATE TABLE "_dbdelta_new_books" (
    "id" integer NOT NULL,
    "author_id" integer,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("author_id") REFERENCES "authors" ("id")
);

INSERT INTO "_dbdelta_new_books" ("id", "author_id") SELECT "id", "author_id" FROM "books";

DROP TABLE "books";

ALTER TABLE "_dbdelta_new_books" RENAME TO "books";

-- rebuild table reviews: SQLite cannot make these changes in place
--   drop foreign key reviews (book_id) -> books (id) ON DELETE SET NULL
-- WARNING sqlite-rebuild: SQLite cannot make these changes to reviews in place, so the table is
--   rebuilt: a new table is created, every row is copied, the old table is dropped and the new
--   one renamed. Writes to the database wait meanwhile, a full copy of the table needs free
--   space, and triggers on the table are dropped and not recreated.
CREATE TABLE "_dbdelta_new_reviews" (
    "id" integer NOT NULL,
    "book_id" integer,
    PRIMARY KEY ("id")
);

INSERT INTO "_dbdelta_new_reviews" ("id", "book_id") SELECT "id", "book_id" FROM "reviews";

DROP TABLE "reviews";

ALTER TABLE "_dbdelta_new_reviews" RENAME TO "reviews";

-- Lists rows that violate foreign keys; it must return no rows.
PRAGMA foreign_key_check;

COMMIT;

PRAGMA foreign_keys = ON;
