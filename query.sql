-- MNS - Medical Notification System
-- Full schema + seed data (guideline catalog and procedure library).
--
-- Fresh install:        sudo mysql < query.sql
-- Existing database:    see migrations/ - run the numbered files you have not
--                       run yet, in order, then this file.
-- (see README for the full setup steps)
--
-- Safe to re-run: tables are CREATE ... IF NOT EXISTS, and the seed data at
-- the bottom is an upsert, so re-running refreshes texts in place.

CREATE DATABASE IF NOT EXISTS MNS
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE MNS;

-- ---------------------------------------------------------------------------
-- people
-- ---------------------------------------------------------------------------

-- Named `users` (plural) because USER is a built-in function name in MySQL.
CREATE TABLE IF NOT EXISTS users
(
    id                 INT AUTO_INCREMENT PRIMARY KEY,

    -- login credentials
    email              VARCHAR(255) NOT NULL UNIQUE,
    password_hash      VARCHAR(60)  NOT NULL,  -- bcrypt output is always 60 chars

    name               VARCHAR(40)  NOT NULL,
    surname            VARCHAR(40)  NULL,

    -- profile (onboarding step 3). NULL until filled in.
    birth_date         DATE         NULL,
    sex                ENUM ('female', 'male', 'other') NULL,
    country            VARCHAR(40)  NULL,
    phone              VARCHAR(20)  NULL,       -- for SMS reminders; optional

    -- settings
    language           ENUM ('en', 'lv') NOT NULL DEFAULT 'en',
    reminders_on       BOOLEAN      NOT NULL DEFAULT TRUE,
    reminder_lead_days SMALLINT     NOT NULL DEFAULT 7,   -- start reminding N days before
    remind_push        BOOLEAN      NOT NULL DEFAULT TRUE,
    remind_sms         BOOLEAN      NOT NULL DEFAULT FALSE,

    -- onboarding step 2: when they agreed to the plain-language data notice
    consent_at         TIMESTAMP    NULL,

    created_at         TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP
) ENGINE = InnoDB;

-- A condition the user has themselves (personal) or that runs in the family.
-- `note` is the free text for code = 'other'.
CREATE TABLE IF NOT EXISTS risk_factors
(
    user_id INT NOT NULL,
    code    ENUM ('cancer', 'diabetes', 'heart', 'other') NOT NULL,
    scope   ENUM ('personal', 'family') NOT NULL,
    note    VARCHAR(200) NULL,

    PRIMARY KEY (user_id, code, scope),
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- recommended checks (the guideline catalog)
-- NULL in min_age / max_age / sex / country means "no restriction".
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS checkup_types
(
    id                   INT AUTO_INCREMENT PRIMARY KEY,
    code                 VARCHAR(40)  NOT NULL UNIQUE,
    name                 VARCHAR(80)  NOT NULL,
    name_lv              VARCHAR(80)  NULL,
    category             ENUM ('screening', 'vaccination', 'checkup') NOT NULL,
    coverage             ENUM ('state', 'private') NOT NULL,

    interval_months      SMALLINT     NOT NULL,
    min_age              SMALLINT     NULL,
    max_age              SMALLINT     NULL,
    sex                  ENUM ('female', 'male') NULL,
    country              VARCHAR(40)  NULL,

    -- risk_only = 1: only shown to people with risk_factor (personal or family).
    -- risk_only = 0: everyone gets it; people with risk_factor get it from
    --                risk_min_age and every risk_interval_months instead.
    risk_factor          ENUM ('cancer', 'diabetes', 'heart') NULL,
    risk_only            BOOLEAN      NOT NULL DEFAULT FALSE,
    risk_interval_months SMALLINT     NULL,
    risk_min_age         SMALLINT     NULL,

    summary              VARCHAR(300) NOT NULL,
    summary_lv           VARCHAR(300) NULL,
    more_info            TEXT         NULL,
    preparation          TEXT         NULL,
    source_url           VARCHAR(255) NULL,
    procedure_code       VARCHAR(40)  NULL      -- links to procedures.code for the prep guide
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- the user's own plan (the Add screen)
-- ---------------------------------------------------------------------------

-- An appointment, vaccine shot, test... that the user added themselves.
-- repeat_every + repeat_unit set  = repeats on a schedule
-- both NULL                       = manual dates only (see task_events)
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

-- One dated occurrence of a task. A repeating task always has its next
-- occurrence here; finishing one (done or missed) creates the next.
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

-- Things the user did. done_on may be in the past: backdating is expected.
CREATE TABLE IF NOT EXISTS log_entries
(
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT          NOT NULL,
    checkup_type_id INT          NULL,      -- a recommended check
    task_id         INT          NULL,      -- or one of the user's own tasks
    title           VARCHAR(80)  NOT NULL,
    category        VARCHAR(40)  NOT NULL,
    done_on         DATE         NOT NULL,
    renew_on        DATE         NULL,      -- vaccines: when it needs renewing, if known
    notes           TEXT         NULL,
    attachment_name VARCHAR(255) NULL,      -- original file name, for display
    attachment_path VARCHAR(255) NULL,      -- file name inside app/uploads/
    created_at      TIMESTAMP    NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (checkup_type_id) REFERENCES checkup_types (id) ON DELETE SET NULL,
    FOREIGN KEY (task_id) REFERENCES tasks (id) ON DELETE SET NULL,
    INDEX idx_log_user_type (user_id, checkup_type_id, done_on),
    INDEX idx_log_user_category (user_id, category, done_on)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- procedure preparation library (the Info screen)
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS procedures
(
    id         INT AUTO_INCREMENT PRIMARY KEY,
    code       VARCHAR(40)  NOT NULL UNIQUE,
    name       VARCHAR(80)  NOT NULL,
    name_lv    VARCHAR(80)  NULL,
    keywords   VARCHAR(255) NULL,   -- extra search words, both languages
    summary    VARCHAR(500) NOT NULL,
    summary_lv VARCHAR(500) NULL
) ENGINE = InnoDB;

-- One checklist line. hours_before is when a reminder for it makes sense.
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

-- "Set reminder" on a procedure: when the appointment is ...
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

-- ... and, per checklist line, whether it is ticked and when to remind.
CREATE TABLE IF NOT EXISTS prep_plan_items
(
    id        INT AUTO_INCREMENT PRIMARY KEY,
    plan_id   INT      NOT NULL,
    step_id   INT      NOT NULL,
    checked   BOOLEAN  NOT NULL DEFAULT FALSE,
    remind_at DATETIME NULL,        -- NULL = no reminder for this line
    sent_at   DATETIME NULL,

    UNIQUE KEY uq_plan_step (plan_id, step_id),
    FOREIGN KEY (plan_id) REFERENCES prep_plans (id) ON DELETE CASCADE,
    FOREIGN KEY (step_id) REFERENCES procedure_steps (id) ON DELETE CASCADE,
    INDEX idx_prep_due (sent_at, remind_at)
) ENGINE = InnoDB;

-- ---------------------------------------------------------------------------
-- notifications
--
-- Every reminder and broadcast on every channel. channel = 'push' rows are
-- the in-app inbox and the pop-ups; accepted_at stays NULL until the user
-- presses Accept, and until then the pop-up keeps coming back. The reminder
-- loop also reads this table so it sends at most one reminder per item a day.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS notifications
(
    id              INT AUTO_INCREMENT PRIMARY KEY,
    user_id         INT           NOT NULL,
    checkup_type_id INT           NULL,
    task_event_id   INT           NULL,
    prep_item_id    INT           NULL,
    channel         ENUM ('push', 'sms') NOT NULL,
    kind            ENUM ('overdue', 'due_soon', 'prep', 'broadcast') NOT NULL,
    message         VARCHAR(1000) NOT NULL,
    status          ENUM ('delivered', 'sent', 'dry_run', 'skipped', 'failed') NOT NULL,
    detail          VARCHAR(255)  NULL,
    accepted_at     TIMESTAMP     NULL,
    created_at      TIMESTAMP     NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (checkup_type_id) REFERENCES checkup_types (id) ON DELETE SET NULL,
    FOREIGN KEY (task_event_id) REFERENCES task_events (id) ON DELETE CASCADE,
    FOREIGN KEY (prep_item_id) REFERENCES prep_plan_items (id) ON DELETE CASCADE,
    INDEX idx_notif_inbox (user_id, channel, accepted_at, created_at)
) ENGINE = InnoDB;


-- ===========================================================================
-- SEED DATA
--
-- DEMO CONTENT. Intervals, age ranges and preparation steps are a reasonable
-- starting point for Latvia but have NOT been reviewed by a clinician, and
-- the Latvian texts have not been proofread by a native speaker. Check both
-- before relying on them.
-- ===========================================================================

INSERT INTO checkup_types
(code, name, name_lv, category, coverage, interval_months, min_age, max_age, sex, country,
 risk_factor, risk_only, risk_interval_months, risk_min_age,
 summary, summary_lv, more_info, preparation, source_url, procedure_code)
VALUES
('cervical_screening', 'Cervical screening', 'Dzemdes kakla skrīnings', 'screening', 'state', 36, 25, 65, 'female', 'Latvia',
 NULL, FALSE, NULL, NULL,
 'Recommended every 3 years for ages 25-65, per Latvia''s national screening programme.',
 'Ieteicams reizi 3 gados vecumā no 25 līdz 65 gadiem, saskaņā ar Latvijas valsts skrīninga programmu.',
 'A cervical smear looks for cell changes in the cervix before they can turn into cancer. Most cervical cancers are caused by long-lasting HPV infection. Risk is higher for smokers and people with a weakened immune system. Changes found early are easy to treat.',
 'Book for a day when you are not on your period. Avoid intercourse, tampons, and vaginal creams for 48 hours before. The test itself takes a few minutes.',
 'https://www.vmnvd.gov.lv', 'cervical_smear'),

('breast_screening', 'Mammography', 'Mamogrāfija', 'screening', 'state', 24, 50, 69, 'female', 'Latvia',
 'cancer', FALSE, 12, 40,
 'Recommended every 2 years for ages 50-69, per Latvia''s national screening programme.',
 'Ieteicama reizi 2 gados vecumā no 50 līdz 69 gadiem, saskaņā ar Latvijas valsts skrīninga programmu.',
 'A mammogram is a low-dose X-ray of the breast that can find tumours too small to feel. A close relative with breast or ovarian cancer raises your risk - talk to your doctor about starting earlier.',
 'Do not use deodorant, powder or lotion on the day - they can show up on the X-ray. Wear a two-piece outfit. Bring previous mammograms if you have them.',
 'https://www.vmnvd.gov.lv', 'mammography'),

('colorectal_screening', 'Bowel cancer screening', 'Zarnu vēža skrīnings', 'screening', 'state', 24, 50, 74, NULL, 'Latvia',
 'cancer', FALSE, 12, 40,
 'A home stool test every 2 years for ages 50-74, per Latvia''s national screening programme.',
 'Mājās veicams fēču tests reizi 2 gados vecumā no 50 līdz 74 gadiem, saskaņā ar Latvijas valsts skrīninga programmu.',
 'The test looks for hidden blood in stool, an early sign of bowel polyps or cancer. Family history of bowel cancer, inflammatory bowel disease and smoking all raise the risk.',
 'Get the test kit from your family doctor. Follow the kit instructions, and return the sample within the time stated on it.',
 'https://www.vmnvd.gov.lv', NULL),

('prostate_check', 'Prostate check (PSA)', 'Prostatas pārbaude (PSA)', 'screening', 'private', 24, 50, 75, 'male', NULL,
 'cancer', FALSE, 12, 45,
 'A PSA blood test every 2 years from age 50 - discuss the pros and cons with your doctor first.',
 'PSA asins analīze reizi 2 gados no 50 gadu vecuma - vispirms pārrunājiet ieguvumus un riskus ar ārstu.',
 'PSA is a protein made by the prostate; a raised level can mean cancer, but also infection or enlargement. A father or brother with prostate cancer raises your risk.',
 'Avoid ejaculation and cycling for 48 hours before the blood draw - both can raise PSA temporarily.',
 NULL, NULL),

('blood_test', 'Blood test', 'Asins analīzes', 'checkup', 'state', 12, 18, NULL, NULL, NULL,
 NULL, FALSE, NULL, NULL,
 'A basic blood count once a year, usually ordered by your family doctor.',
 'Pilna asins aina reizi gadā, parasti pēc ģimenes ārsta nosūtījuma.',
 'A complete blood count checks red cells, white cells and platelets. It can show anaemia, infection and many other conditions before they cause symptoms.',
 'Usually no fasting needed for a blood count alone - but if glucose or cholesterol are added, fast for 8-12 hours (water is fine).',
 NULL, 'blood_test_fasting'),

('cholesterol', 'Cholesterol check', 'Holesterīna pārbaude', 'checkup', 'state', 60, 40, NULL, NULL, NULL,
 'heart', FALSE, 12, 20,
 'A lipid panel every 5 years from 40 - yearly from 20 if you or your family have heart disease.',
 'Lipīdu profils reizi 5 gados no 40 gadu vecuma - katru gadu no 20 gadiem, ja jums vai ģimenē ir sirds slimības.',
 'High cholesterol has no symptoms but builds up in artery walls, raising the risk of heart attack and stroke. Inherited high cholesterol (familial hypercholesterolaemia) can start in childhood.',
 'Fast for 9-12 hours beforehand - water is fine. Take your usual medicines unless told otherwise.',
 NULL, 'blood_test_fasting'),

('blood_glucose', 'Blood sugar test', 'Cukura līmeņa pārbaude', 'checkup', 'state', 36, 45, NULL, NULL, NULL,
 'diabetes', FALSE, 12, 30,
 'A fasting glucose or HbA1c test every 3 years from 45 - yearly from 30 if diabetes affects you or your family.',
 'Glikozes vai HbA1c analīze reizi 3 gados no 45 gadu vecuma - katru gadu no 30 gadiem, ja diabēts ir jums vai ģimenē.',
 'Type 2 diabetes develops slowly and often without symptoms. A parent or sibling with diabetes, being overweight, and inactivity all raise the risk.',
 'For fasting glucose, eat nothing for 8 hours beforehand - water is fine. HbA1c needs no fasting.',
 NULL, 'blood_test_fasting'),

('blood_pressure', 'Blood pressure check', 'Asinsspiediena pārbaude', 'checkup', 'state', 12, 18, NULL, NULL, NULL,
 'heart', FALSE, 6, 18,
 'Have your blood pressure measured at least once a year.',
 'Mēriet asinsspiedienu vismaz reizi gadā.',
 'High blood pressure rarely causes symptoms but is a leading cause of stroke and heart disease.',
 'No caffeine, exercise or smoking for 30 minutes before. Sit quietly for 5 minutes first.',
 NULL, NULL),

('skin_check', 'Skin check', 'Ādas pārbaude', 'screening', 'private', 12, 18, NULL, NULL, NULL,
 'cancer', TRUE, NULL, NULL,
 'A yearly mole check by a dermatologist, since cancer affects you or your family.',
 'Ikgadēja dzimumzīmju pārbaude pie dermatologa, jo vēzis ir bijis jums vai ģimenē.',
 'A dermatologist checks moles and skin spots for signs of melanoma and other skin cancers. Fair skin, many moles, sunburns and family history raise the risk.',
 'Remove nail polish and make-up. Note any mole that has changed in size, shape or colour.',
 NULL, NULL),

('dental_checkup', 'Dental check-up', 'Zobārsta apskate', 'checkup', 'private', 12, 18, NULL, NULL, NULL,
 NULL, FALSE, NULL, NULL,
 'A dental check-up and cleaning once a year.',
 'Zobārsta apskate un zobu tīrīšana reizi gadā.',
 'Regular check-ups catch decay and gum disease early, when treatment is quick and cheap.',
 'Brush and floss beforehand. Bring a list of medicines you take.',
 NULL, NULL),

('eye_exam', 'Eye exam', 'Redzes pārbaude', 'checkup', 'private', 24, 40, NULL, NULL, NULL,
 'diabetes', FALSE, 12, 30,
 'An eye exam every 2 years from 40 - glaucoma risk rises with age.',
 'Redzes pārbaude reizi 2 gados no 40 gadu vecuma - glaukomas risks pieaug ar vecumu.',
 'An eye exam checks sight and eye pressure, and looks for glaucoma and diabetic eye disease, which cause no symptoms early on.',
 'Bring your current glasses or contact lenses. Your pupils may be dilated - do not plan to drive straight after.',
 NULL, 'eye_dilation'),

('tbe_booster', 'Encephalitis booster', 'Ērču encefalīta revakcinācija', 'vaccination', 'private', 60, 1, NULL, NULL, 'Latvia',
 NULL, FALSE, NULL, NULL,
 'A tick-borne encephalitis booster every 5 years - Latvia is a high-risk area.',
 'Ērču encefalīta revakcinācija reizi 5 gados - Latvija ir augsta riska teritorija.',
 'Tick-borne encephalitis is a viral brain infection spread by tick bites. Latvia has one of the highest rates in Europe. After the first 3 doses, a booster keeps protection up.',
 'No preparation needed. Bring your vaccination record so the dose can be written in.',
 'https://www.spkc.gov.lv', 'vaccination'),

('tetanus_diphtheria', 'Tetanus & diphtheria booster', 'Stingumkrampju un difterijas revakcinācija', 'vaccination', 'state', 120, 18, NULL, NULL, NULL,
 NULL, FALSE, NULL, NULL,
 'A tetanus-diphtheria booster every 10 years for adults.',
 'Pieaugušajiem stingumkrampju un difterijas revakcinācija reizi 10 gados.',
 'Tetanus enters through wounds and diphtheria spreads between people; both can be fatal. Protection fades, so adults need a booster every 10 years.',
 'No preparation needed. Bring your vaccination record so the dose can be written in.',
 'https://www.spkc.gov.lv', 'vaccination'),

('flu_vaccine', 'Flu vaccine', 'Gripas vakcīna', 'vaccination', 'private', 12, 18, NULL, NULL, NULL,
 NULL, FALSE, NULL, NULL,
 'A flu vaccine every autumn - the strains change each year.',
 'Gripas vakcīna katru rudeni - vīrusa celmi katru gadu mainās.',
 'Flu vaccines are updated every year to match the strains expected that winter. They matter most for people over 65, pregnant people, and anyone with a chronic illness.',
 'No preparation needed. Tell the nurse if you have a fever on the day.',
 NULL, 'vaccination')

-- MySQL 8.0.20+ prefers the alias form over VALUES(col) in the update list.
AS new
ON DUPLICATE KEY UPDATE
    name = new.name, name_lv = new.name_lv, category = new.category, coverage = new.coverage,
    interval_months = new.interval_months, min_age = new.min_age, max_age = new.max_age,
    sex = new.sex, country = new.country, risk_factor = new.risk_factor, risk_only = new.risk_only,
    risk_interval_months = new.risk_interval_months, risk_min_age = new.risk_min_age,
    summary = new.summary, summary_lv = new.summary_lv, more_info = new.more_info,
    preparation = new.preparation, source_url = new.source_url, procedure_code = new.procedure_code;


INSERT INTO procedures (code, name, name_lv, keywords, summary, summary_lv)
VALUES
('gastroscopy', 'Gastroscopy', 'Gastroskopija',
 'endoscopy stomach oesophagus FGDS endoskopija kuņģis barības vads',
 'A thin, flexible camera is passed through your mouth to look at your oesophagus, stomach and the start of your small intestine. It takes 5-15 minutes. You can ask for a throat spray or light sedation.',
 'Caur muti ievada plānu, lokanu kameru, lai apskatītu barības vadu, kuņģi un tievās zarnas sākumu. Tas aizņem 5-15 minūtes. Varat lūgt rīkles aerosolu vai vieglu sedāciju.'),
('colonoscopy', 'Colonoscopy', 'Kolonoskopija',
 'bowel colon endoscopy zarnas resnā zarna endoskopija',
 'A camera looks at the inside of your large bowel. It can find and remove polyps before they turn into cancer. The bowel must be completely empty, so preparation starts days before.',
 'Ar kameru apskata resnās zarnas iekšpusi. Izmeklējuma laikā var atrast un noņemt polipus, pirms tie pārvēršas vēzī. Zarnām jābūt pilnīgi tukšām, tāpēc sagatavošanās sākas vairākas dienas iepriekš.'),
('blood_test_fasting', 'Fasting blood test', 'Asins analīzes tukšā dūšā',
 'blood glucose cholesterol lipids asinis glikoze holesterīns tukšā dūšā',
 'Some blood tests - glucose, cholesterol and lipids - need an empty stomach to give an accurate result. The draw itself takes a few minutes.',
 'Dažām analīzēm - glikozei, holesterīnam un lipīdiem - vajadzīgs tukšs kuņģis, lai rezultāts būtu precīzs. Pati asins paņemšana aizņem dažas minūtes.'),
('mri', 'MRI scan', 'Magnētiskā rezonanse (MR)',
 'MRI magnetic resonance scan MR magnētiskā rezonanse',
 'An MRI uses a strong magnet to make detailed pictures of the body. It is painless but loud, and you lie still in a narrow tunnel for 15-60 minutes. Metal is not allowed in the room.',
 'MR izmanto spēcīgu magnētu, lai iegūtu detalizētus ķermeņa attēlus. Tas nesāp, bet ir skaļi, un 15-60 minūtes jāguļ nekustīgi šaurā tunelī. Telpā nedrīkst ienest metālu.'),
('ct_contrast', 'CT scan with contrast', 'Datortomogrāfija ar kontrastvielu',
 'CT computed tomography contrast DT datortomogrāfija kontrastviela',
 'A CT scan is a fast X-ray scan. Contrast dye is injected into a vein to make blood vessels and organs show up more clearly. It can make you feel warm for a moment.',
 'DT ir ātra rentgena izmeklēšana. Vēnā ievada kontrastvielu, lai asinsvadi un orgāni būtu labāk redzami. Uz mirkli var justies silti.'),
('mammography', 'Mammography', 'Mamogrāfija',
 'mammogram breast screening krūts mamogrāfija skrīnings',
 'A low-dose X-ray of the breasts. Each breast is pressed flat for a few seconds, which can be uncomfortable but is quick.',
 'Krūšu rentgenizmeklēšana ar zemu starojuma devu. Katru krūti uz dažām sekundēm saspiež, kas var būt nepatīkami, bet ātri.'),
('cervical_smear', 'Cervical smear', 'Dzemdes kakla uztriepe',
 'pap smear cervical screening HPV uztriepe dzemdes kakls ginekologs',
 'A nurse or gynaecologist takes a small sample of cells from the cervix with a soft brush. It takes a few minutes.',
 'Māsa vai ginekologs ar mīkstu birstīti paņem nelielu šūnu paraugu no dzemdes kakla. Tas aizņem dažas minūtes.'),
('abdominal_ultrasound', 'Abdominal ultrasound', 'Vēdera dobuma ultrasonogrāfija',
 'ultrasound sonography USG ultrasonogrāfija vēders sonogrāfija',
 'Sound waves make pictures of your liver, gallbladder, kidneys and other organs. Painless, about 20 minutes, with cold gel on your belly.',
 'Skaņas viļņi rada aknu, žultspūšļa, nieru un citu orgānu attēlus. Nesāpīgi, apmēram 20 minūtes, uz vēdera uzklāj vēsu gelu.'),
('vaccination', 'Vaccination', 'Vakcinācija',
 'vaccine shot jab booster vakcīna pote potēšana',
 'A quick injection, usually in the upper arm. You wait about 15 minutes afterwards in case of a reaction.',
 'Ātra injekcija, parasti augšdelmā. Pēc tam apmēram 15 minūtes jāuzgaida, ja nu rodas reakcija.'),
('surgery_anaesthesia', 'Surgery under general anaesthesia', 'Operācija vispārējā anestēzijā',
 'surgery operation anaesthesia narcosis operācija anestēzija narkoze',
 'You will be fully asleep during the operation. Most rules exist to keep your stomach empty and to get you home safely afterwards.',
 'Operācijas laikā jūs pilnībā gulēsiet. Lielākā daļa noteikumu ir, lai kuņģis būtu tukšs un lai pēc tam droši nokļūtu mājās.'),
('tooth_extraction', 'Tooth extraction', 'Zoba ekstrakcija',
 'dentist tooth removal wisdom tooth zobārsts zoba izraušana gudrības zobs',
 'The dentist numbs the area and removes the tooth. Expect some swelling and soreness for a few days.',
 'Zobārsts atsāpina vietu un izņem zobu. Dažas dienas var būt pietūkums un sāpīgums.'),
('eye_dilation', 'Eye exam with dilating drops', 'Acu pārbaude ar zīlīšu paplašināšanu',
 'eye exam dilation ophthalmologist acis oftalmologs zīlītes',
 'Drops widen your pupils so the doctor can see the back of your eye. Your sight will be blurry and light-sensitive for 4-6 hours.',
 'Pilieni paplašina zīlītes, lai ārsts varētu apskatīt acs dibenu. Redze 4-6 stundas būs neskaidra un jutīga pret gaismu.')
AS new
ON DUPLICATE KEY UPDATE
    name = new.name, name_lv = new.name_lv, keywords = new.keywords,
    summary = new.summary, summary_lv = new.summary_lv;


-- Steps are matched to their procedure by code, and upserted on
-- (procedure_id, position) so users' saved checklists keep their step ids.
INSERT INTO procedure_steps (procedure_id, position, text, text_lv, hours_before)
SELECT p.id, s.position, s.text, s.text_lv, s.hours_before
FROM procedures p
JOIN (
    SELECT 'gastroscopy' AS code, 1 AS position, 'Ask your doctor whether to pause blood thinners or diabetes medicine' AS text, 'Jautājiet ārstam, vai jāpārtrauc asins šķidrinātāji vai diabēta zāles' AS text_lv, 168 AS hours_before
    UNION ALL SELECT 'gastroscopy', 2, 'Arrange for someone to take you home if you have sedation', 'Norunājiet, kas jūs aizvedīs mājās, ja saņemsiet sedāciju', 48
    UNION ALL SELECT 'gastroscopy', 3, 'Stop eating - nothing solid from now on', 'Pārtrauciet ēst - no šī brīža neko cietu', 8
    UNION ALL SELECT 'gastroscopy', 4, 'Only small sips of water from now on, then nothing', 'No šī brīža tikai daži malki ūdens, pēc tam neko', 4
    UNION ALL SELECT 'gastroscopy', 5, 'Take your passport or ID card and the referral', 'Paņemiet pasi vai ID karti un nosūtījumu', 2
    UNION ALL SELECT 'gastroscopy', 6, 'Do not drive for the rest of the day if you had sedation', 'Ja saņēmāt sedāciju, līdz dienas beigām nevadiet auto', NULL

    UNION ALL SELECT 'colonoscopy', 1, 'Ask your doctor whether to pause blood thinners or iron tablets', 'Jautājiet ārstam, vai jāpārtrauc asins šķidrinātāji vai dzelzs tabletes', 168
    UNION ALL SELECT 'colonoscopy', 2, 'Start a low-fibre diet: no seeds, nuts, whole grains or raw vegetables', 'Sāciet diētu ar maz šķiedrvielām: bez sēklām, riekstiem, pilngraudiem un svaigiem dārzeņiem', 72
    UNION ALL SELECT 'colonoscopy', 3, 'Clear liquids only from now on - water, clear broth, tea', 'No šī brīža tikai dzidri šķidrumi - ūdens, dzidrs buljons, tēja', 24
    UNION ALL SELECT 'colonoscopy', 4, 'Start the bowel preparation drink exactly as instructed', 'Sāciet dzert zarnu attīrīšanas šķīdumu tieši pēc instrukcijas', 18
    UNION ALL SELECT 'colonoscopy', 5, 'Arrange for someone to take you home', 'Norunājiet, kas jūs aizvedīs mājās', 48
    UNION ALL SELECT 'colonoscopy', 6, 'Stop drinking completely', 'Pilnībā pārtrauciet dzert', 2
    UNION ALL SELECT 'colonoscopy', 7, 'Take your passport or ID card and the referral', 'Paņemiet pasi vai ID karti un nosūtījumu', 2

    UNION ALL SELECT 'blood_test_fasting', 1, 'Stop eating - water only from now on', 'Pārtrauciet ēst - no šī brīža tikai ūdens', 12
    UNION ALL SELECT 'blood_test_fasting', 2, 'No coffee, juice, alcohol or chewing gum', 'Bez kafijas, sulas, alkohola un košļājamās gumijas', 12
    UNION ALL SELECT 'blood_test_fasting', 3, 'Drink a glass of water - it makes the draw easier', 'Izdzeriet glāzi ūdens - tas atvieglo asins paņemšanu', 1
    UNION ALL SELECT 'blood_test_fasting', 4, 'Take your ID and the referral', 'Paņemiet personu apliecinošu dokumentu un nosūtījumu', 1

    UNION ALL SELECT 'mri', 1, 'Tell the clinic about any implant, pacemaker or metal in your body', 'Pastāstiet klīnikai par implantiem, elektrokardiostimulatoru vai metālu ķermenī', 72
    UNION ALL SELECT 'mri', 2, 'If you are claustrophobic, ask about a calming medicine', 'Ja jums ir klaustrofobija, jautājiet par nomierinošām zālēm', 72
    UNION ALL SELECT 'mri', 3, 'Leave jewellery and watches at home', 'Atstājiet rotaslietas un pulksteni mājās', 2
    UNION ALL SELECT 'mri', 4, 'Take your ID and the referral', 'Paņemiet personu apliecinošu dokumentu un nosūtījumu', 2

    UNION ALL SELECT 'ct_contrast', 1, 'Tell the clinic about kidney problems, diabetes medicine (metformin) or a contrast allergy', 'Pastāstiet klīnikai par nieru problēmām, diabēta zālēm (metformīnu) vai alerģiju pret kontrastvielu', 72
    UNION ALL SELECT 'ct_contrast', 2, 'Stop eating - clear drinks are fine', 'Pārtrauciet ēst - dzidri dzērieni atļauti', 4
    UNION ALL SELECT 'ct_contrast', 3, 'Take your ID and the referral', 'Paņemiet personu apliecinošu dokumentu un nosūtījumu', 2
    UNION ALL SELECT 'ct_contrast', 4, 'Drink plenty of water afterwards to flush out the contrast', 'Pēc tam dzeriet daudz ūdens, lai izvadītu kontrastvielu', NULL

    UNION ALL SELECT 'mammography', 1, 'Bring previous mammograms if they were done elsewhere', 'Paņemiet iepriekšējās mamogrammas, ja tās veiktas citur', 24
    UNION ALL SELECT 'mammography', 2, 'No deodorant, powder or lotion today', 'Šodien nelietojiet dezodorantu, pūderi vai losjonu', 3
    UNION ALL SELECT 'mammography', 3, 'Wear a two-piece outfit', 'Uzvelciet divdaļīgu apģērbu', 3
    UNION ALL SELECT 'mammography', 4, 'Take your ID', 'Paņemiet personu apliecinošu dokumentu', 1

    UNION ALL SELECT 'cervical_smear', 1, 'Check the date is not during your period - rebook if it is', 'Pārbaudiet, vai datums nesakrīt ar menstruācijām - ja sakrīt, pārceliet', 72
    UNION ALL SELECT 'cervical_smear', 2, 'No intercourse, tampons or vaginal creams from now on', 'No šī brīža bez dzimumakta, tamponiem un vaginālajiem krēmiem', 48
    UNION ALL SELECT 'cervical_smear', 3, 'Take your ID', 'Paņemiet personu apliecinošu dokumentu', 1

    UNION ALL SELECT 'abdominal_ultrasound', 1, 'Stop eating - water only from now on', 'Pārtrauciet ēst - no šī brīža tikai ūdens', 6
    UNION ALL SELECT 'abdominal_ultrasound', 2, 'Drink 1 litre of water and do not empty your bladder (pelvic scans only)', 'Izdzeriet 1 litru ūdens un neiztukšojiet urīnpūsli (tikai mazā iegurņa izmeklējumam)', 1
    UNION ALL SELECT 'abdominal_ultrasound', 3, 'Take your ID and the referral', 'Paņemiet personu apliecinošu dokumentu un nosūtījumu', 1

    UNION ALL SELECT 'vaccination', 1, 'Find your vaccination record so the dose can be written in', 'Sameklējiet vakcinācijas pasi, lai devu varētu ierakstīt', 24
    UNION ALL SELECT 'vaccination', 2, 'Eat normally and wear a top with loose sleeves', 'Paēdiet kā parasti un uzvelciet apģērbu ar platām piedurknēm', 2
    UNION ALL SELECT 'vaccination', 3, 'Tell the nurse if you have a fever or a new allergy', 'Pastāstiet māsai, ja jums ir drudzis vai jauna alerģija', NULL
    UNION ALL SELECT 'vaccination', 4, 'Wait 15 minutes at the clinic afterwards', 'Pēc tam 15 minūtes uzgaidiet klīnikā', NULL

    UNION ALL SELECT 'surgery_anaesthesia', 1, 'Arrange for someone to take you home and stay with you overnight', 'Norunājiet, kas jūs aizvedīs mājās un paliks pie jums pa nakti', 72
    UNION ALL SELECT 'surgery_anaesthesia', 2, 'No smoking or alcohol from now on', 'No šī brīža nesmēķējiet un nelietojiet alkoholu', 24
    UNION ALL SELECT 'surgery_anaesthesia', 3, 'Shower, and remove nail polish and jewellery', 'Nomazgājieties dušā, noņemiet nagu laku un rotaslietas', 12
    UNION ALL SELECT 'surgery_anaesthesia', 4, 'Stop eating - nothing solid from now on', 'Pārtrauciet ēst - no šī brīža neko cietu', 6
    UNION ALL SELECT 'surgery_anaesthesia', 5, 'Stop drinking - not even water', 'Pārtrauciet dzert - pat ne ūdeni', 2
    UNION ALL SELECT 'surgery_anaesthesia', 6, 'Take your passport or ID card, referral and list of medicines', 'Paņemiet pasi vai ID karti, nosūtījumu un zāļu sarakstu', 2

    UNION ALL SELECT 'tooth_extraction', 1, 'Get painkillers in advance (ask which ones are fine for you)', 'Iegādājieties pretsāpju līdzekļus (pajautājiet, kuri jums piemēroti)', 24
    UNION ALL SELECT 'tooth_extraction', 2, 'Eat a light meal - you should not eat for 2 hours afterwards', 'Paēdiet vieglu maltīti - 2 stundas pēc tam nedrīkstēs ēst', 3
    UNION ALL SELECT 'tooth_extraction', 3, 'Take your ID', 'Paņemiet personu apliecinošu dokumentu', 1

    UNION ALL SELECT 'eye_dilation', 1, 'Arrange a lift - you should not drive for 4-6 hours afterwards', 'Norunājiet transportu - 4-6 stundas pēc tam nedrīkst vadīt auto', 24
    UNION ALL SELECT 'eye_dilation', 2, 'Take sunglasses for the way home', 'Paņemiet saulesbrilles ceļam uz mājām', 1
    UNION ALL SELECT 'eye_dilation', 3, 'Bring your current glasses or contact lenses', 'Paņemiet savas brilles vai kontaktlēcas', 1
) AS s ON s.code = p.code
ON DUPLICATE KEY UPDATE
    text = s.text, text_lv = s.text_lv, hours_before = s.hours_before;
