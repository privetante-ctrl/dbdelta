BEGIN;

-- drop index ix_articles_author on articles (author)
DROP INDEX "ix_articles_author";

-- drop index ix_articles_author_created on articles (author, created_at DESC)
DROP INDEX "ix_articles_author_created";

-- drop index ix_articles_recent on articles (created_at DESC) where "published" = TRUE
DROP INDEX "ix_articles_recent";

-- drop unique index ux_articles_title on articles (LOWER("title"))
DROP INDEX "ux_articles_title";

COMMIT;
