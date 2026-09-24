-- Demo data for the example user: lab results (vitamins, minerals, heavy
-- metals, blood count, lipids...) from five blood draws over two years, and
-- the state-paid checks they have already done.
--
--   sudo mysql < query.sql        (first - creates lab_tests and its catalog)
--   sudo mysql < demo_data.sql
--
-- Safe to re-run: every row it adds has notes starting with "[demo]", and
-- those are deleted first. The user is picked by email - change @email to
-- load the same data for someone else. If no user has that email, the first
-- INSERT fails on user_id NOT NULL and nothing is written.
--
-- The values are made up, chosen to show trends on a chart: vitamin D low
-- every winter and recovering with supplements, iron stores dipping then
-- rebuilding, LDL creeping up (the user has heart disease in the family),
-- a trace of lead and mercury well under the limits.

USE MNS;
-- Match the tables, so comparing them with the text literals below is allowed.
SET NAMES utf8mb4 COLLATE utf8mb4_unicode_ci;

SET @email = 'furanetsgeorgiy@gmail.com';
SET @uid = (SELECT id FROM users WHERE email = @email);

START TRANSACTION;

-- lab_reports rows go with their log entries (ON DELETE SET NULL would
-- otherwise leave them behind), and lab_results go with lab_reports (CASCADE).
DELETE FROM lab_reports WHERE user_id = @uid AND notes LIKE '[demo]%';
DELETE FROM log_entries WHERE user_id = @uid AND notes LIKE '[demo]%';

-- State-paid checks already done. Yearly check-up last October = due again
-- in a couple of weeks (shows as "upcoming"); tetanus booster good until 2035.
INSERT INTO log_entries (user_id, checkup_type_id, title, category, done_on, renew_on, notes)
SELECT @uid, c.id, c.name, c.category, v.done_on, v.renew_on, v.notes
FROM checkup_types c
JOIN (VALUES
    ROW('family_doctor_checkup', DATE '2024-10-14', NULL,               '[demo] Blood pressure 118/76, BMI 22.4. Referred for blood tests.'),
    ROW('tetanus_diphtheria',    DATE '2025-06-18', DATE '2035-06-18', '[demo] Td booster before a summer job on a building site.'),
    ROW('family_doctor_checkup', DATE '2025-10-06', NULL,               '[demo] Blood pressure 121/78. Discussed family history of heart disease.')
) AS v (code, done_on, renew_on, notes) ON v.code = c.code;

-- One log entry per blood draw, linked from its lab report.

-- 2024-10-14: 20 values
INSERT INTO log_entries (user_id, title, category, done_on, notes)
VALUES (@uid, 'Blood test', 'checkup', '2024-10-14', '[demo] First full panel - baseline.');
INSERT INTO lab_reports (user_id, taken_at, lab_name, log_entry_id, notes)
VALUES (@uid, '2024-10-14 08:10', 'Demo laboratory', LAST_INSERT_ID(), '[demo] First full panel - baseline.');
SET @report = LAST_INSERT_ID();
INSERT INTO lab_results (report_id, lab_test_id, value, comparator, ref_low, ref_high)
SELECT @report, t.id, v.value, v.comparator, t.ref_low, t.ref_high
FROM lab_tests t
JOIN (VALUES
    ROW('vitamin_d', 21.4, NULL),
    ROW('vitamin_b12', 412, NULL),
    ROW('folate', 7.9, NULL),
    ROW('iron', 16.8, NULL),
    ROW('ferritin', 38, NULL),
    ROW('magnesium', 0.81, NULL),
    ROW('zinc', 13.1, NULL),
    ROW('calcium', 2.36, NULL),
    ROW('copper', 15.2, NULL),
    ROW('lead', 18, NULL),
    ROW('mercury', 1.0, '<'),
    ROW('hemoglobin', 148, NULL),
    ROW('wbc', 6.4, NULL),
    ROW('glucose', 4.9, NULL),
    ROW('cholesterol_total', 4.6, NULL),
    ROW('ldl', 2.7, NULL),
    ROW('hdl', 1.32, NULL),
    ROW('triglycerides', 1.05, NULL),
    ROW('tsh', 1.92, NULL),
    ROW('crp', 1.1, NULL)
) AS v (code, value, comparator) ON v.code = t.code;

-- 2025-03-10: 10 values
INSERT INTO log_entries (user_id, title, category, done_on, notes)
VALUES (@uid, 'Blood test', 'checkup', '2025-03-10', '[demo] End of winter, felt tired. Doctor suggested vitamin D and iron-rich food.');
INSERT INTO lab_reports (user_id, taken_at, lab_name, log_entry_id, notes)
VALUES (@uid, '2025-03-10 08:30', 'Demo laboratory', LAST_INSERT_ID(), '[demo] End of winter, felt tired. Doctor suggested vitamin D and iron-rich food.');
SET @report = LAST_INSERT_ID();
INSERT INTO lab_results (report_id, lab_test_id, value, comparator, ref_low, ref_high)
SELECT @report, t.id, v.value, v.comparator, t.ref_low, t.ref_high
FROM lab_tests t
JOIN (VALUES
    ROW('vitamin_d', 17.8, NULL),
    ROW('vitamin_b12', 388, NULL),
    ROW('folate', 6.8, NULL),
    ROW('iron', 11.2, NULL),
    ROW('ferritin', 24, NULL),
    ROW('magnesium', 0.72, NULL),
    ROW('hemoglobin', 139, NULL),
    ROW('wbc', 8.9, NULL),
    ROW('tsh', 2.34, NULL),
    ROW('crp', 3.6, NULL)
) AS v (code, value, comparator) ON v.code = t.code;

-- 2025-09-22: 12 values
INSERT INTO log_entries (user_id, title, category, done_on, notes)
VALUES (@uid, 'Blood test', 'checkup', '2025-09-22', '[demo] After a summer of vitamin D 2000 IU a day.');
INSERT INTO lab_reports (user_id, taken_at, lab_name, log_entry_id, notes)
VALUES (@uid, '2025-09-22 08:05', 'Demo laboratory', LAST_INSERT_ID(), '[demo] After a summer of vitamin D 2000 IU a day.');
SET @report = LAST_INSERT_ID();
INSERT INTO lab_results (report_id, lab_test_id, value, comparator, ref_low, ref_high)
SELECT @report, t.id, v.value, v.comparator, t.ref_low, t.ref_high
FROM lab_tests t
JOIN (VALUES
    ROW('vitamin_d', 38.4, NULL),
    ROW('iron', 18.9, NULL),
    ROW('ferritin', 41, NULL),
    ROW('zinc', 12.4, NULL),
    ROW('hemoglobin', 151, NULL),
    ROW('wbc', 5.8, NULL),
    ROW('glucose', 5.1, NULL),
    ROW('cholesterol_total', 4.9, NULL),
    ROW('ldl', 2.9, NULL),
    ROW('hdl', 1.28, NULL),
    ROW('triglycerides', 1.22, NULL),
    ROW('crp', 0.7, NULL)
) AS v (code, value, comparator) ON v.code = t.code;

-- 2026-03-16: 20 values
INSERT INTO log_entries (user_id, title, category, done_on, notes)
VALUES (@uid, 'Blood test', 'checkup', '2026-03-16', '[demo] Stopped the supplements in December. Full panel again, incl. metals.');
INSERT INTO lab_reports (user_id, taken_at, lab_name, log_entry_id, notes)
VALUES (@uid, '2026-03-16 08:20', 'Demo laboratory', LAST_INSERT_ID(), '[demo] Stopped the supplements in December. Full panel again, incl. metals.');
SET @report = LAST_INSERT_ID();
INSERT INTO lab_results (report_id, lab_test_id, value, comparator, ref_low, ref_high)
SELECT @report, t.id, v.value, v.comparator, t.ref_low, t.ref_high
FROM lab_tests t
JOIN (VALUES
    ROW('vitamin_d', 27.1, NULL),
    ROW('vitamin_b12', 455, NULL),
    ROW('folate', 8.4, NULL),
    ROW('iron', 19.6, NULL),
    ROW('ferritin', 57, NULL),
    ROW('magnesium', 0.84, NULL),
    ROW('zinc', 14.0, NULL),
    ROW('calcium', 2.41, NULL),
    ROW('copper', 16.0, NULL),
    ROW('lead', 22, NULL),
    ROW('mercury', 3.1, NULL),
    ROW('hemoglobin', 153, NULL),
    ROW('wbc', 6.1, NULL),
    ROW('glucose', 5.3, NULL),
    ROW('cholesterol_total', 5.4, NULL),
    ROW('ldl', 3.4, NULL),
    ROW('hdl', 1.21, NULL),
    ROW('triglycerides', 1.58, NULL),
    ROW('tsh', 2.08, NULL),
    ROW('crp', 1.4, NULL)
) AS v (code, value, comparator) ON v.code = t.code;

-- 2026-09-15: 16 values
INSERT INTO log_entries (user_id, title, category, done_on, notes)
VALUES (@uid, 'Blood test', 'checkup', '2026-09-15', '[demo] Back on vitamin D since April; less fast food.');
INSERT INTO lab_reports (user_id, taken_at, lab_name, log_entry_id, notes)
VALUES (@uid, '2026-09-15 08:15', 'Demo laboratory', LAST_INSERT_ID(), '[demo] Back on vitamin D since April; less fast food.');
SET @report = LAST_INSERT_ID();
INSERT INTO lab_results (report_id, lab_test_id, value, comparator, ref_low, ref_high)
SELECT @report, t.id, v.value, v.comparator, t.ref_low, t.ref_high
FROM lab_tests t
JOIN (VALUES
    ROW('vitamin_d', 44.2, NULL),
    ROW('vitamin_b12', 471, NULL),
    ROW('iron', 21.3, NULL),
    ROW('ferritin', 64, NULL),
    ROW('magnesium', 0.86, NULL),
    ROW('zinc', 13.6, NULL),
    ROW('calcium', 2.38, NULL),
    ROW('hemoglobin', 155, NULL),
    ROW('wbc', 5.9, NULL),
    ROW('glucose', 5.0, NULL),
    ROW('cholesterol_total', 5.1, NULL),
    ROW('ldl', 3.1, NULL),
    ROW('hdl', 1.3, NULL),
    ROW('triglycerides', 1.31, NULL),
    ROW('tsh', 1.87, NULL),
    ROW('crp', 0.8, NULL)
) AS v (code, value, comparator) ON v.code = t.code;

COMMIT;
