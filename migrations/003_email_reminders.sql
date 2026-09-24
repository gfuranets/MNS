-- 003 - reminder emails (Gmail), sent once per item instead of every day.
--
-- For a database that already has 001 and 002 applied. Run it ONCE:
--
--   sudo mysql < migrations/003_email_reminders.sql
--
-- What changes:
--   users          + remind_email (on by default - everyone has an email).
--   notifications  channel gains 'email'.
--                  + due_on: which due date a reminder was about. An email
--                  goes out once per item per due date; when the item is
--                  done, its next due date gets its own email.
--   tasks          + remind_every_minutes: a task can ask to be emailed
--                  again every N minutes until done (1 = demo, 1440 = daily).

USE MNS;

ALTER TABLE users
    ADD COLUMN remind_email BOOLEAN NOT NULL DEFAULT TRUE AFTER remind_sms;

ALTER TABLE notifications
    MODIFY channel ENUM ('push', 'sms', 'email') NOT NULL,
    ADD COLUMN due_on DATE NULL AFTER prep_item_id;

ALTER TABLE tasks
    ADD COLUMN remind_every_minutes INT NULL AFTER repeat_unit;
