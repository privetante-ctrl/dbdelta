BEGIN;

-- drop foreign key books (author_id) -> authors (id)
ALTER TABLE "books" DROP CONSTRAINT "books_author_id_fkey";

-- add foreign key books (author_id) -> authors (id) ON DELETE CASCADE
ALTER TABLE "books" ADD FOREIGN KEY ("author_id") REFERENCES "authors" ("id") ON DELETE CASCADE;

-- add foreign key reviews (book_id) -> books (id) ON DELETE SET NULL
ALTER TABLE "reviews" ADD FOREIGN KEY ("book_id") REFERENCES "books" ("id") ON DELETE SET NULL;

COMMIT;
