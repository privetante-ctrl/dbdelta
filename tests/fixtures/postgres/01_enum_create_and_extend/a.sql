CREATE TYPE post_status AS ENUM ('draft', 'published');
CREATE TABLE posts (
    id integer PRIMARY KEY,
    status post_status NOT NULL DEFAULT 'draft'
);
