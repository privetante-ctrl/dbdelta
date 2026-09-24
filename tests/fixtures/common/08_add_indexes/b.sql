CREATE TABLE articles (
    id integer PRIMARY KEY,
    author text NOT NULL,
    title text NOT NULL,
    published boolean NOT NULL DEFAULT FALSE,
    created_at timestamp NOT NULL
);

CREATE INDEX ix_articles_author ON articles (author);
CREATE UNIQUE INDEX ux_articles_title ON articles (lower(title));
CREATE INDEX ix_articles_recent ON articles (created_at DESC) WHERE published = TRUE;
CREATE INDEX ix_articles_author_created ON articles (author, created_at DESC);
