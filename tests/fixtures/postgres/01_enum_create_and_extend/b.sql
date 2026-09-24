CREATE TYPE post_status AS ENUM ('draft', 'review', 'published', 'archived');
CREATE TYPE priority AS ENUM ('low', 'high');
CREATE TABLE posts (
    id integer PRIMARY KEY,
    status post_status NOT NULL DEFAULT 'review',
    priority priority NOT NULL DEFAULT 'low'
);
