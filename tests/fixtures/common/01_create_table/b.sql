CREATE TABLE users (
    id integer PRIMARY KEY,
    email varchar(255) NOT NULL
);

CREATE TABLE posts (
    id integer PRIMARY KEY,
    user_id integer NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title text NOT NULL DEFAULT 'untitled',
    body text
);
CREATE INDEX ix_posts_user ON posts (user_id);
