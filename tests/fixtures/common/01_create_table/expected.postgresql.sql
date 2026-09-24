BEGIN;

-- create table posts
CREATE TABLE "posts" (
    "id" integer NOT NULL,
    "user_id" integer NOT NULL,
    "title" text NOT NULL DEFAULT 'untitled',
    "body" text,
    PRIMARY KEY ("id"),
    FOREIGN KEY ("user_id") REFERENCES "users" ("id") ON DELETE CASCADE
);

CREATE INDEX "ix_posts_user" ON "posts" ("user_id");

COMMIT;
