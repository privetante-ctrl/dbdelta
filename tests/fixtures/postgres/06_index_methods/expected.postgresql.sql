BEGIN;

-- create index ix_documents_body_hash on documents using hash (body)
CREATE INDEX "ix_documents_body_hash" ON "documents" USING hash ("body");

-- create index ix_documents_created on documents using brin (created_at)
CREATE INDEX "ix_documents_created" ON "documents" USING brin ("created_at");

-- create index ix_documents_tags on documents using gin (tags)
CREATE INDEX "ix_documents_tags" ON "documents" USING gin ("tags");

COMMIT;
