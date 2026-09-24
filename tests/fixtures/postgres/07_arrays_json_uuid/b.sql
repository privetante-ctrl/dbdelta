CREATE TABLE profiles (
    id integer PRIMARY KEY,
    settings jsonb,
    external_id uuid,
    aliases varchar(30)[],
    preferences jsonb NOT NULL DEFAULT '{}'
);
