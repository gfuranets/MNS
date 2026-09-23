-- MNS - Medical Notification System
-- Full schema + the guideline catalog.
--
-- Fresh install:        sudo mysql < query.sql
-- Existing database:    sudo mysql < migrations/001_health_tracker.sql
--                       sudo mysql < query.sql
-- (see README for the full setup steps)
--
-- Safe to re-run: tables are CREATE ... IF NOT EXISTS, and the catalog at the
-- bottom is an upsert, so re-running refreshes guideline texts in place.

CREATE DATABASE IF NOT EXISTS MNS
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE MNS;

-- Named `users` (plural) because USER is a built-in function name in MySQL.
CREATE TABLE IF NOT EXISTS users
(
    id             INT AUTO_INCREMENT PRIMARY KEY,

    -- login credentials
    email          VARCHAR(255) NOT NULL UNIQUE,
    password_hash  VARCHAR(60)  NOT NULL,  -- bcrypt output is always 60 chars

    name           VARCHAR(40)  NOT NULL,

    -- profile (onboarding step 2). NULL until filled in.
    -- Birth *year* only: it is all the guidelines need, and less to leak.
    birth_year     SMALLINT     NULL,
    sex            ENUM ('female', 'male', 'other') NULL,
    country        VARCHAR(40)  NULL,

    -- for SMS reminders; optional
    phone          VARCHAR(20)  NULL,

    -- settings
    language       ENUM ('en', 'lv', 'ru')             NOT NULL DEFAULT 'en',
    reminder_style ENUM ('off', 'gentle', 'frequent')  NOT NULL DEFAULT 'gentle',
    remind_push    BOOLEAN      NOT NULL DEFAULT TRUE,
    remind_sms     BOOLEAN      NOT NULL DEFAULT FALSE,

    created_at     TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE = InnoDB;

-- One row per ticked box on the profile page. `note` is the free text for 'other'.
CREATE TABLE IF NOT EXISTS risk_factors
(
    user_id INT NOT NULL,
    code    ENUM ('family_cancer', 'family_diabetes', 'family_heart', 'other') NOT NULL,
    note    VARCHAR(200) NULL,

    PRIMARY KEY (user_id, code),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE = InnoDB;

-- The guideline catalog: what to do, how often, and who it applies to.
-- NULL in min_age / max_age / sex / country means "no restriction".
CREATE TABLE IF NOT EXISTS checkup_types
(
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    code                 VARCHAR(40)  NOT NULL UNIQUE,
    name                 VARCHAR(80)  NOT NULL,
    category             ENUM ('screening', 'vaccination', 'checkup') NOT NULL,
    coverage             ENUM ('state', 'private') NOT NULL,

    interval_months      SMALLINT     NOT NULL,
    min_age              SMALLINT     NULL,
    max_age              SMALLINT     NULL,
    sex                  ENUM ('female', 'male') NULL,
    country              VARCHAR(40)  NULL,

    -- risk_only = 1: only shown to people with risk_factor.
    -- risk_only = 0: everyone gets it; people with risk_factor get it from
    --                risk_min_age and every risk_interval_months instead.
    risk_factor          ENUM ('family_cancer', 'family_diabetes', 'family_heart', 'other') NULL,
    risk_only            BOOLEAN      NOT NULL DEFAULT FALSE,
    risk_interval_months SMALLINT     NULL,
    risk_min_age         SMALLINT     NULL,

    summary              VARCHAR(300) NOT NULL,
    more_info            TEXT         NULL,
    preparation          TEXT         NULL,
    source_url           VARCHAR(255) NULL
) ENGINE = InnoDB;

-- Things the user did. done_on may be in the past: backdating is expected.
CREATE TABLE IF NOT EXISTS log_entries
(
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT          NOT NULL,
    checkup_type_id INT          NULL,      -- NULL = did not match a guideline
    title           VARCHAR(80)  NOT NULL,
    done_on         DATE         NOT NULL,
    notes           TEXT         NULL,
    attachment_name VARCHAR(255) NULL,      -- original file name, for display
    attachment_path VARCHAR(255) NULL,      -- file name inside app/uploads/
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (checkup_type_id) REFERENCES checkup_types (id) ON DELETE SET NULL,
    INDEX idx_log_user_type (user_id, checkup_type_id, done_on)
) ENGINE = InnoDB;

-- "Remind me later": no reminders for that item until `until`.
CREATE TABLE IF NOT EXISTS snoozes
(
    user_id         INT  NOT NULL,
    checkup_type_id INT  NOT NULL,
    until           DATE NOT NULL,

    PRIMARY KEY (user_id, checkup_type_id),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (checkup_type_id) REFERENCES checkup_types (id) ON DELETE CASCADE
) ENGINE = InnoDB;

-- Every reminder and broadcast on every channel. channel = 'push' rows are the
-- in-app inbox; the reminder loop also reads this table so it never nags about
-- the same item twice within the user's chosen cooldown.
CREATE TABLE IF NOT EXISTS notifications
(
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT           NOT NULL,
    checkup_type_id INT           NULL,
    channel         ENUM ('push', 'sms') NOT NULL,
    kind            ENUM ('overdue', 'due_soon', 'broadcast') NOT NULL,
    message         VARCHAR(1000) NOT NULL,
    status          ENUM ('delivered', 'sent', 'dry_run', 'skipped', 'failed') NOT NULL,
    detail          VARCHAR(255)  NULL,
    read_at         TIMESTAMP     NULL,
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (checkup_type_id) REFERENCES checkup_types (id) ON DELETE SET NULL,
    INDEX idx_notif_inbox (user_id, channel, created_at),
    INDEX idx_notif_cooldown (user_id, checkup_type_id, created_at)
) ENGINE = InnoDB;


-- ---------------------------------------------------------------------------
-- Guideline catalog
--
-- DEMO DATA. Intervals and age ranges are a reasonable starting point for
-- Latvia but have NOT been reviewed by a clinician - check them against the
-- National Health Service (vmnvd.gov.lv) before relying on them.
-- ---------------------------------------------------------------------------

INSERT INTO checkup_types
(code, name, category, coverage, interval_months, min_age, max_age, sex, country,
 risk_factor, risk_only, risk_interval_months, risk_min_age,
 summary, more_info, preparation, source_url)
VALUES
('cervical_screening', 'Cervical screening', 'screening', 'state', 36, 25, 65, 'female', 'Latvia',
 NULL, FALSE, NULL, NULL,
 'Recommended every 3 years for ages 25-65, per Latvia''s national screening programme.',
 'A cervical smear looks for cell changes in the cervix before they can turn into cancer. Most cervical cancers are caused by long-lasting HPV infection. Risk is higher for smokers and people with a weakened immune system. Changes found early are easy to treat.',
 'Book for a day when you are not on your period. Avoid intercourse, tampons, and vaginal creams for 48 hours before. The test itself takes a few minutes.',
 'https://www.vmnvd.gov.lv'),

('breast_screening', 'Mammography', 'screening', 'state', 24, 50, 69, 'female', 'Latvia',
 'family_cancer', FALSE, 12, 40,
 'Recommended every 2 years for ages 50-69, per Latvia''s national screening programme.',
 'A mammogram is a low-dose X-ray of the breast that can find tumours too small to feel. A close relative with breast or ovarian cancer raises your risk - talk to your doctor about starting earlier.',
 'Do not use deodorant, powder or lotion on the day - they can show up on the X-ray. Wear a two-piece outfit. Bring previous mammograms if you have them.',
 'https://www.vmnvd.gov.lv'),

('colorectal_screening', 'Bowel cancer screening', 'screening', 'state', 24, 50, 74, NULL, 'Latvia',
 'family_cancer', FALSE, 12, 40,
 'A home stool test every 2 years for ages 50-74, per Latvia''s national screening programme.',
 'The test looks for hidden blood in stool, an early sign of bowel polyps or cancer. Family history of bowel cancer, inflammatory bowel disease and smoking all raise the risk.',
 'Get the test kit from your family doctor. Follow the kit instructions, and return the sample within the time stated on it.',
 'https://www.vmnvd.gov.lv'),

('prostate_check', 'Prostate check (PSA)', 'screening', 'private', 24, 50, 75, 'male', NULL,
 'family_cancer', FALSE, 12, 45,
 'A PSA blood test every 2 years from age 50 - discuss the pros and cons with your doctor first.',
 'PSA is a protein made by the prostate; a raised level can mean cancer, but also infection or enlargement. A father or brother with prostate cancer raises your risk.',
 'Avoid ejaculation and cycling for 48 hours before the blood draw - both can raise PSA temporarily.',
 NULL),

('blood_test', 'Blood test', 'checkup', 'state', 12, 18, NULL, NULL, NULL,
 NULL, FALSE, NULL, NULL,
 'A basic blood count once a year, usually ordered by your family doctor.',
 'A complete blood count checks red cells, white cells and platelets. It can show anaemia, infection and many other conditions before they cause symptoms.',
 'Usually no fasting needed for a blood count alone - but if glucose or cholesterol are added, fast for 8-12 hours (water is fine).',
 NULL),

('cholesterol', 'Cholesterol check', 'checkup', 'state', 60, 40, NULL, NULL, NULL,
 'family_heart', FALSE, 12, 20,
 'A lipid panel every 5 years from 40 - yearly from 20 if heart disease runs in your family.',
 'High cholesterol has no symptoms but builds up in artery walls, raising the risk of heart attack and stroke. Inherited high cholesterol (familial hypercholesterolaemia) can start in childhood.',
 'Fast for 9-12 hours beforehand - water is fine. Take your usual medicines unless told otherwise.',
 NULL),

('blood_glucose', 'Blood sugar test', 'checkup', 'state', 36, 45, NULL, NULL, NULL,
 'family_diabetes', FALSE, 12, 30,
 'A fasting glucose or HbA1c test every 3 years from 45 - yearly from 30 if diabetes runs in your family.',
 'Type 2 diabetes develops slowly and often without symptoms. A parent or sibling with diabetes, being overweight, and inactivity all raise the risk.',
 'For fasting glucose, eat nothing for 8 hours beforehand - water is fine. HbA1c needs no fasting.',
 NULL),

('blood_pressure', 'Blood pressure check', 'checkup', 'state', 12, 18, NULL, NULL, NULL,
 'family_heart', FALSE, 6, 18,
 'Have your blood pressure measured at least once a year.',
 'High blood pressure rarely causes symptoms but is a leading cause of stroke and heart disease.',
 'No caffeine, exercise or smoking for 30 minutes before. Sit quietly for 5 minutes first.',
 NULL),

('skin_check', 'Skin check', 'screening', 'private', 12, 18, NULL, NULL, NULL,
 'family_cancer', TRUE, NULL, NULL,
 'A yearly mole check by a dermatologist, since cancer runs in your family.',
 'A dermatologist checks moles and skin spots for signs of melanoma and other skin cancers. Fair skin, many moles, sunburns and family history raise the risk.',
 'Remove nail polish and make-up. Note any mole that has changed in size, shape or colour.',
 NULL),

('dental_checkup', 'Dental check-up', 'checkup', 'private', 12, 18, NULL, NULL, NULL,
 NULL, FALSE, NULL, NULL,
 'A dental check-up and cleaning once a year.',
 'Regular check-ups catch decay and gum disease early, when treatment is quick and cheap.',
 'Brush and floss beforehand. Bring a list of medicines you take.',
 NULL),

('eye_exam', 'Eye exam', 'checkup', 'private', 24, 40, NULL, NULL, NULL,
 'family_diabetes', FALSE, 12, 30,
 'An eye exam every 2 years from 40 - glaucoma risk rises with age.',
 'An eye exam checks sight and eye pressure, and looks for glaucoma and diabetic eye disease, which cause no symptoms early on.',
 'Bring your current glasses or contact lenses. Your pupils may be dilated - do not plan to drive straight after.',
 NULL),

('tbe_booster', 'Encephalitis booster', 'vaccination', 'private', 60, 1, NULL, NULL, 'Latvia',
 NULL, FALSE, NULL, NULL,
 'A tick-borne encephalitis booster every 5 years - Latvia is a high-risk area.',
 'Tick-borne encephalitis is a viral brain infection spread by tick bites. Latvia has one of the highest rates in Europe. After the first 3 doses, a booster keeps protection up.',
 'No preparation needed. Bring your vaccination record so the dose can be written in.',
 'https://www.spkc.gov.lv'),

('tetanus_diphtheria', 'Tetanus & diphtheria booster', 'vaccination', 'state', 120, 18, NULL, NULL, NULL,
 NULL, FALSE, NULL, NULL,
 'A tetanus-diphtheria booster every 10 years for adults.',
 'Tetanus enters through wounds and diphtheria spreads between people; both can be fatal. Protection fades, so adults need a booster every 10 years.',
 'No preparation needed. Bring your vaccination record so the dose can be written in.',
 'https://www.spkc.gov.lv'),

('flu_vaccine', 'Flu vaccine', 'vaccination', 'private', 12, 18, NULL, NULL, NULL,
 NULL, FALSE, NULL, NULL,
 'A flu vaccine every autumn - the strains change each year.',
 'Flu vaccines are updated every year to match the strains expected that winter. They matter most for people over 65, pregnant people, and anyone with a chronic illness.',
 'No preparation needed. Tell the nurse if you have a fever on the day.',
 NULL)

-- MySQL 8.0.20+ prefers the alias form over VALUES(col) in the update list.
AS new
ON DUPLICATE KEY UPDATE
    name                 = new.name,
    category             = new.category,
    coverage             = new.coverage,
    interval_months      = new.interval_months,
    min_age              = new.min_age,
    max_age              = new.max_age,
    sex                  = new.sex,
    country              = new.country,
    risk_factor          = new.risk_factor,
    risk_only            = new.risk_only,
    risk_interval_months = new.risk_interval_months,
    risk_min_age         = new.risk_min_age,
    summary              = new.summary,
    more_info            = new.more_info,
    preparation          = new.preparation,
    source_url           = new.source_url;
