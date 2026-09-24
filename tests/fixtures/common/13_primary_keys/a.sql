CREATE TABLE tags (
    name text NOT NULL,
    label text
);
CREATE TABLE memberships (
    user_id integer NOT NULL,
    group_id integer NOT NULL,
    PRIMARY KEY (user_id)
);
