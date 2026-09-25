BEGIN;

-- create index ix_articles_author on articles (author)
-- WARNING index-lock: Building ix_articles_author blocks inserts, updates and deletes on
--   articles (SHARE lock) until the whole table has been indexed.
CREATE INDEX "ix_articles_author" ON "articles" ("author");

-- create index ix_articles_author_created on articles (author, created_at DESC)
-- WARNING index-lock: Building ix_articles_author_created blocks inserts, updates and deletes on
--   articles (SHARE lock) until the whole table has been indexed.
CREATE INDEX "ix_articles_author_created" ON "articles" ("author", "created_at" DESC);

-- create index ix_articles_recent on articles (created_at DESC) where "published" = TRUE
-- WARNING index-lock: Building ix_articles_recent blocks inserts, updates and deletes on
--   articles (SHARE lock) until the whole table has been indexed.
CREATE INDEX "ix_articles_recent" ON "articles" ("created_at" DESC) WHERE "published" = TRUE;

-- create unique index ux_articles_title on articles (LOWER("title"))
-- WARNING index-lock: Building ux_articles_title blocks inserts, updates and deletes on articles
--   (SHARE lock) until the whole table has been indexed.
-- WARNING unique-duplicates: Rows already in articles may contain duplicates of
--   (LOWER("title")), which make adding the unique index fail.
CREATE UNIQUE INDEX "ux_articles_title" ON "articles" ((LOWER("title")));

COMMIT;
