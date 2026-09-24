CREATE TABLE tags (
    name text NOT NULL,
    label text,
    PRIMARY KEY (name)
);
CREATE TABLE memberships (
    user_id integer NOT NULL,
    group_id integer NOT NULL,
    PRIMARY KEY (user_id, group_id)
);
