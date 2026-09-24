CREATE TABLE articles (
    id integer PRIMARY KEY,
    author text NOT NULL,
    title text NOT NULL,
    published boolean NOT NULL DEFAULT FALSE,
    created_at timestamp NOT NULL
);

CREATE INDEX ix_articles_author ON articles (author);
CREATE UNIQUE INDEX ux_articles_title ON articles (title);
