BEGIN;

-- drop index ix_articles_author on articles (author)
DROP INDEX "ix_articles_author";

-- drop unique index ux_articles_title on articles (title)
DROP INDEX "ux_articles_title";

-- create index ix_articles_author on articles (author, created_at)
CREATE INDEX "ix_articles_author" ON "articles" ("author", "created_at");

-- create index ux_articles_title on articles (title)
CREATE INDEX "ux_articles_title" ON "articles" ("title");

COMMIT;
