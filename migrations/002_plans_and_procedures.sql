-- 002 - own tasks, procedure library, daily reminders, consent, EN/LV.
--
-- For a database that already has migration 001 applied. Run it ONCE, then
-- run query.sql to load the new seed data:
--
--   sudo mysql < migrations/002_plans_and_procedures.sql
--   sudo mysql < query.sql
--
-- Nothing is lost. What changes:
--   users         birth_year -> birth_date (1 January of that year - edit it
--                 in the profile), + surname, consent, daily-reminder settings.
--                 Language 'ru' becomes 'en' (the app now speaks EN and LV).
--                 reminder_style becomes reminders_on (off -> false).
--   risk_factors  family_cancer / family_diabetes / family_heart become
--                 cancer / diabetes / heart with scope = 'family'.
--   snoozes       dropped - reminders now repeat daily until marked done.
--   new tables    tasks, task_events, procedures, procedure_steps,
--                 prep_plans, prep_plan_items (same definitions as query.sql).

USE MNS;

-- ---------------------------------------------------------------------------
-- users
-- ---------------------------------------------------------------------------

ALTER TABLE users
    ADD COLUMN surname            VARCHAR(40) NULL AFTER name,
    ADD COLUMN birth_date         DATE        NULL AFTER surname,
    ADD COLUMN reminders_on       BOOLEAN     NOT NULL DEFAULT TRUE AFTER language,
    ADD COLUMN reminder_lead_days SMALLINT    NOT NULL DEFAULT 7 AFTER reminders_on,
    ADD COLUMN consent_at         TIMESTAMP   NULL AFTER remind_sms;

UPDATE users SET birth_date = MAKEDATE(birth_year, 1) WHERE birth_year IS NOT NULL;
UPDATE users SET reminders_on = (reminder_style <> 'off');
UPDATE users SET language = 'en' WHERE language = 'ru';

ALTER TABLE users
    DROP COLUMN birth_year,
    DROP COLUMN reminder_style,
    MODIFY COLUMN language ENUM ('en', 'lv') NOT NULL DEFAULT 'en';

-- ---------------------------------------------------------------------------
-- risk factors: family_x -> x + scope
-- ---------------------------------------------------------------------------

ALTER TABLE risk_factors
    MODIFY COLUMN code ENUM ('family_cancer', 'family_diabetes', 'family_heart', 'other',
                             'cancer', 'diabetes', 'heart') NOT NULL,
    ADD COLUMN scope ENUM ('personal', 'family') NOT NULL DEFAULT 'family' AFTER code;

UPDATE risk_factors SET code = CASE code
    WHEN 'family_cancer'   THEN 'cancer'
    WHEN 'family_diabetes' THEN 'diabetes'
    WHEN 'family_heart'    THEN 'heart'
    ELSE code END;

ALTER TABLE risk_factors
    MODIFY COLUMN code ENUM ('cancer', 'diabetes', 'heart', 'other') NOT NULL,
    MODIFY COLUMN scope ENUM ('personal', 'family') NOT NULL,
    DROP PRIMARY KEY,
    ADD PRIMARY KEY (user_id, code, scope);

-- ---------------------------------------------------------------------------
-- guideline catalog: same risk codes, plus Latvian texts and the prep link
-- ---------------------------------------------------------------------------

ALTER TABLE checkup_types
    MODIFY COLUMN risk_factor ENUM ('family_cancer', 'family_diabetes', 'family_heart', 'other',
                                    'cancer', 'diabetes', 'heart') NULL,
    ADD COLUMN name_lv        VARCHAR(80)  NULL AFTER name,
    ADD COLUMN summary_lv     VARCHAR(300) NULL AFTER summary,
    ADD COLUMN procedure_code VARCHAR(40)  NULL AFTER source_url;

UPDATE checkup_types SET risk_factor = CASE risk_factor
    WHEN 'family_cancer'   THEN 'cancer'
    WHEN 'family_diabetes' THEN 'diabetes'
    WHEN 'family_heart'    THEN 'heart'
    ELSE NULL END
WHERE risk_factor IS NOT NULL;

ALTER TABLE checkup_types
    MODIFY COLUMN risk_factor ENUM ('cancer', 'diabetes', 'heart') NULL;

DROP TABLE IF EXISTS snoozes;

-- ---------------------------------------------------------------------------
-- new tables (identical to query.sql)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS tasks
(
    id               INT AUTO_INCREMENT PRIMARY KEY,
    user_id          INT          NOT NULL,
    title            VARCHAR(80)  NOT NULL,
    category         VARCHAR(40)  NOT NULL,
    description      TEXT         NULL,
    doctor_name      VARCHAR(80)  NULL,
    doctor_specialty VARCHAR(80)  NULL,
    repeat_every     SMALLINT     NULL,
    repeat_unit      ENUM ('day', 'week', 'month', 'year') NULL,
    created_at       TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS task_events
(
    id         INT AUTO_INCREMENT PRIMARY KEY,
    task_id    INT       NOT NULL,
    user_id    INT       NOT NULL,
    due_on     DATE      NOT NULL,
    status     ENUM ('pending', 'done', 'missed') NOT NULL DEFAULT 'pending',
    done_on    DATE      NULL,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    UNIQUE KEY uq_task_date (task_id, due_on),
    FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE CASCADE,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    INDEX idx_events_user (user_id, status, due_on)
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS procedures
(
    id         INT AUTO_INCREMENT PRIMARY KEY,
    code       VARCHAR(40)  NOT NULL UNIQUE,
    name       VARCHAR(80)  NOT NULL,
    name_lv    VARCHAR(80)  NULL,
    keywords   VARCHAR(255) NULL,
    summary    VARCHAR(500) NOT NULL,
    summary_lv VARCHAR(500) NULL
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS procedure_steps
(
    id           INT AUTO_INCREMENT PRIMARY KEY,
    procedure_id INT          NOT NULL,
    position     SMALLINT     NOT NULL,
    text         VARCHAR(255) NOT NULL,
    text_lv      VARCHAR(255) NULL,
    hours_before SMALLINT     NULL,

    UNIQUE KEY uq_step (procedure_id, position),
    FOREIGN KEY (procedure_id) REFERENCES procedures (id) ON DELETE CASCADE
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS prep_plans
(
    id             INT AUTO_INCREMENT PRIMARY KEY,
    user_id        INT       NOT NULL,
    procedure_id   INT       NOT NULL,
    appointment_at DATETIME  NOT NULL,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (procedure_id) REFERENCES procedures (id) ON DELETE CASCADE
) ENGINE = InnoDB;

CREATE TABLE IF NOT EXISTS prep_plan_items
(
    id        INT AUTO_INCREMENT PRIMARY KEY,
    plan_id   INT      NOT NULL,
    step_id   INT      NOT NULL,
    checked   BOOLEAN  NOT NULL DEFAULT FALSE,
    remind_at DATETIME NULL,
    sent_at   DATETIME NULL,

    UNIQUE KEY uq_plan_step (plan_id, step_id),
    FOREIGN KEY (plan_id) REFERENCES prep_plans (id) ON DELETE CASCADE,
    FOREIGN KEY (step_id) REFERENCES procedure_steps (id) ON DELETE CASCADE,
    INDEX idx_prep_due (sent_at, remind_at)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- log entries: category, link to the user's own task, vaccine renewal date
-- ---------------------------------------------------------------------------

ALTER TABLE log_entries
    ADD COLUMN task_id  INT         NULL AFTER checkup_type_id,
    ADD COLUMN category VARCHAR(40) NOT NULL DEFAULT 'other' AFTER title,
    ADD COLUMN renew_on DATE        NULL AFTER done_on,
    ADD FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE SET NULL,
    ADD INDEX idx_log_user_category (user_id, category, done_on);

UPDATE log_entries l JOIN checkup_types c ON c.id = l.checkup_type_id
SET l.category = c.category;

ALTER TABLE log_entries ALTER COLUMN category DROP DEFAULT;

-- ---------------------------------------------------------------------------
-- notifications: Accept instead of read, links to tasks and prep reminders
-- ---------------------------------------------------------------------------

ALTER TABLE notifications
    RENAME COLUMN read_at TO accepted_at,
    MODIFY COLUMN kind ENUM ('overdue', 'due_soon', 'prep', 'broadcast') NOT NULL,
    ADD COLUMN task_event_id INT NULL AFTER checkup_type_id,
    ADD COLUMN prep_item_id  INT NULL AFTER task_event_id,
    ADD FOREIGN KEY (task_event_id) REFERENCES task_events (id) ON DELETE CASCADE,
    ADD FOREIGN KEY (prep_item_id) REFERENCES prep_plan_items (id) ON DELETE CASCADE,
    ADD INDEX idx_notif_inbox_v2 (user_id, channel, accepted_at, created_at),
    DROP INDEX idx_notif_inbox,
    DROP INDEX idx_notif_cooldown;

ALTER TABLE notifications RENAME INDEX idx_notif_inbox_v2 TO idx_notif_inbox;
