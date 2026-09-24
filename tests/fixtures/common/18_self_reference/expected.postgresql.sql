BEGIN;

-- create table comments
CREATE TABLE "comments" (
    "id" integer NOT NULL,
    "reply_to" integer,
    "body" text NOT NULL,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("reply_to") REFERENCES "comments" ("id")
);

-- add column categories.parent_id integer
ALTER TABLE "categories" ADD COLUMN "parent_id" integer;

-- add foreign key categories (parent_id) -> categories (id)
-- WARNING foreign-key: Adding the foreign key checks every row of categories while holding SHARE
--   ROW EXCLUSIVE locks on categories and categories, which block writes to both; rows without a
--   match make the migration fail.
ALTER TABLE "categories" ADD FOREIGN KEY ("parent_id") REFERENCES "categories" ("id");

COMMIT;
