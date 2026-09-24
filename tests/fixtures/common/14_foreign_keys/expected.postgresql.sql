BEGIN;

-- drop foreign key books (author_id) -> authors (id)
ALTER TABLE "books" DROP CONSTRAINT "books_author_id_fkey";

-- add foreign key books (author_id) -> authors (id) ON DELETE CASCADE
-- WARNING foreign-key: Adding the foreign key checks every row of books while holding SHARE ROW
--   EXCLUSIVE locks on books and authors, which block writes to both; rows without a match make
--   the migration fail.
ALTER TABLE "books" ADD FOREIGN KEY ("author_id") REFERENCES "authors" ("id") ON DELETE CASCADE;

-- add foreign key reviews (book_id) -> books (id) ON DELETE SET NULL
-- WARNING foreign-key: Adding the foreign key checks every row of reviews while holding SHARE
--   ROW EXCLUSIVE locks on reviews and books, which block writes to both; rows without a match
--   make the migration fail.
ALTER TABLE "reviews" ADD FOREIGN KEY ("book_id") REFERENCES "books" ("id") ON DELETE SET NULL;

COMMIT;
