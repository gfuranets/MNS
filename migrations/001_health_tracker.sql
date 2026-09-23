-- 001 - reshape `users` for the health tracker.
--
-- Only for a database created by the ORIGINAL query.sql (user system only).
-- A fresh install does not need this. Run it ONCE, then run query.sql to add
-- the new tables and the guideline catalog:
--
--   sudo mysql < migrations/001_health_tracker.sql
--   sudo mysql < query.sql
--
-- What changes:
--   birth_date -> birth_year (the year is kept, the day and month are dropped)
--   surname, address, city are dropped - the new onboarding does not ask for them
--   country becomes optional (filled in on the profile page instead of signup)
--   sex and the reminder settings are added

USE MNS;

ALTER TABLE users
    ADD COLUMN birth_year SMALLINT NULL AFTER name,
    ADD COLUMN sex ENUM ('female', 'male', 'other') NULL AFTER birth_year;

UPDATE users SET birth_year = YEAR(birth_date);

ALTER TABLE users
    DROP COLUMN birth_date,
    DROP COLUMN surname,
    DROP COLUMN address,
    DROP COLUMN city,
    MODIFY COLUMN country VARCHAR(40) NULL AFTER sex,
    ADD COLUMN language       ENUM ('en', 'lv', 'ru')            NOT NULL DEFAULT 'en'     AFTER phone,
    ADD COLUMN reminder_style ENUM ('off', 'gentle', 'frequent') NOT NULL DEFAULT 'gentle' AFTER language,
    ADD COLUMN remind_push    BOOLEAN NOT NULL DEFAULT TRUE  AFTER reminder_style,
    ADD COLUMN remind_sms     BOOLEAN NOT NULL DEFAULT FALSE AFTER remind_push;
