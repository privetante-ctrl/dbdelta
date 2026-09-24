BEGIN;

-- allow NULL in contacts.phone
ALTER TABLE "contacts" ALTER COLUMN "phone" DROP NOT NULL;

-- make contacts.email NOT NULL
ALTER TABLE "contacts" ALTER COLUMN "email" SET NOT NULL;

COMMIT;
