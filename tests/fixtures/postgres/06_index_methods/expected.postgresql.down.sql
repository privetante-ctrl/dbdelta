BEGIN;

-- drop index ix_documents_body_hash on documents using hash (body)
DROP INDEX "ix_documents_body_hash";

-- drop index ix_documents_created on documents using brin (created_at)
DROP INDEX "ix_documents_created";

-- drop index ix_documents_tags on documents using gin (tags)
DROP INDEX "ix_documents_tags";

COMMIT;
