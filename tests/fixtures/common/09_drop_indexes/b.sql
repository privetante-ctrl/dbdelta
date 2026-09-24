CREATE TABLE articles (
    id integer PRIMARY KEY,
    author text NOT NULL,
    title text NOT NULL,
    published boolean NOT NULL DEFAULT FALSE,
    created_at timestamp NOT NULL
);
