BEGIN;

-- allow NULL in contacts.phone
ALTER TABLE "contacts" ALTER COLUMN "phone" DROP NOT NULL;

-- make contacts.email NOT NULL
-- WARNING set-not-null: Making contacts.email NOT NULL fails if any row holds NULL, and
--   PostgreSQL checks every row while holding an ACCESS EXCLUSIVE lock that blocks reads and
--   writes.
ALTER TABLE "contacts" ALTER COLUMN "email" SET NOT NULL;

COMMIT;
