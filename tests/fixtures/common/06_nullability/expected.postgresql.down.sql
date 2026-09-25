BEGIN;

-- allow NULL in contacts.email
ALTER TABLE "contacts" ALTER COLUMN "email" DROP NOT NULL;

-- make contacts.phone NOT NULL
-- WARNING set-not-null: Making contacts.phone NOT NULL fails if any row holds NULL, and
--   PostgreSQL checks every row while holding an ACCESS EXCLUSIVE lock that blocks reads and
--   writes.
ALTER TABLE "contacts" ALTER COLUMN "phone" SET NOT NULL;

COMMIT;
