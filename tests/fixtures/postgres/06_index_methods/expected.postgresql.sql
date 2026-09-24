BEGIN;

-- create index ix_documents_body_hash on documents using hash (body)
-- WARNING index-lock: Building ix_documents_body_hash blocks inserts, updates and deletes on
--   documents (SHARE lock) until the whole table has been indexed.
CREATE INDEX "ix_documents_body_hash" ON "documents" USING hash ("body");

-- create index ix_documents_created on documents using brin (created_at)
-- WARNING index-lock: Building ix_documents_created blocks inserts, updates and deletes on
--   documents (SHARE lock) until the whole table has been indexed.
CREATE INDEX "ix_documents_created" ON "documents" USING brin ("created_at");

-- create index ix_documents_tags on documents using gin (tags)
-- WARNING index-lock: Building ix_documents_tags blocks inserts, updates and deletes on
--   documents (SHARE lock) until the whole table has been indexed.
CREATE INDEX "ix_documents_tags" ON "documents" USING gin ("tags");

COMMIT;
