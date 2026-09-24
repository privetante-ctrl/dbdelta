CREATE TABLE Users (
    ID INTEGER PRIMARY KEY,
    Email TEXT
);
CREATE INDEX IX_Users_Email ON Users (Email);
