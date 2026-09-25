BEGIN;

-- drop index ix_articles_author on articles (author, created_at)
DROP INDEX "ix_articles_author";

-- drop index ux_articles_title on articles (title)
DROP INDEX "ux_articles_title";

-- create index ix_articles_author on articles (author)
-- WARNING index-lock: Building ix_articles_author blocks inserts, updates and deletes on
--   articles (SHARE lock) until the whole table has been indexed.
CREATE INDEX "ix_articles_author" ON "articles" ("author");

-- create unique index ux_articles_title on articles (title)
-- WARNING index-lock: Building ux_articles_title blocks inserts, updates and deletes on articles
--   (SHARE lock) until the whole table has been indexed.
-- WARNING unique-duplicates: Rows already in articles may contain duplicates of (title), which
--   make adding the unique index fail.
CREATE UNIQUE INDEX "ux_articles_title" ON "articles" ("title");

COMMIT;
