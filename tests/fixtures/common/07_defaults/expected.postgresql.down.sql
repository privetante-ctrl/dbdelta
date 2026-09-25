BEGIN;

-- drop default of settings.created_at
ALTER TABLE "settings" ALTER COLUMN "created_at" DROP DEFAULT;

-- drop default of settings.page_size
ALTER TABLE "settings" ALTER COLUMN "page_size" DROP DEFAULT;

-- set default of settings.level to 1
ALTER TABLE "settings" ALTER COLUMN "level" SET DEFAULT 1;

-- set default of settings.theme to 'light'
ALTER TABLE "settings" ALTER COLUMN "theme" SET DEFAULT 'light';

COMMIT;
