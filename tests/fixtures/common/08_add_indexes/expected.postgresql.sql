BEGIN;

-- create index ix_articles_author on articles (author)
CREATE INDEX "ix_articles_author" ON "articles" ("author");

-- create index ix_articles_author_created on articles (author, created_at DESC)
CREATE INDEX "ix_articles_author_created" ON "articles" ("author", "created_at" DESC);

-- create index ix_articles_recent on articles (created_at DESC) where "published" = TRUE
CREATE INDEX "ix_articles_recent" ON "articles" ("created_at" DESC) WHERE "published" = TRUE;

-- create unique index ux_articles_title on articles (LOWER("title"))
CREATE UNIQUE INDEX "ux_articles_title" ON "articles" ((LOWER("title")));

COMMIT;
