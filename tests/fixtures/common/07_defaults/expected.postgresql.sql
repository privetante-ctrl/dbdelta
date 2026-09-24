BEGIN;

-- drop default of settings.level
ALTER TABLE "settings" ALTER COLUMN "level" DROP DEFAULT;

-- set default of settings.created_at to CURRENT_TIMESTAMP
ALTER TABLE "settings" ALTER COLUMN "created_at" SET DEFAULT CURRENT_TIMESTAMP;

-- set default of settings.page_size to 10
ALTER TABLE "settings" ALTER COLUMN "page_size" SET DEFAULT 10;

-- set default of settings.theme to 'dark'
ALTER TABLE "settings" ALTER COLUMN "theme" SET DEFAULT 'dark';

COMMIT;
