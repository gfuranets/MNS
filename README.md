# MNS — Medical Notification System

FastAPI + SQLAlchemy + MySQL, with a mobile-first web frontend in English and
Latvian. A preventive-health companion:

- **Recommended checks.** From your birth date, gender, country and the
  conditions you or your family have, it works out which screenings,
  check-ups and vaccinations apply to you, and when each is due.
- **Your own plan.** Add appointments, vaccine shots, tests... repeating
  ("every 2 weeks") or on dates you pick, with the doctor's name and specialty.
- **Reminders that don't give up.** Every day until an item is marked done,
  in the app (a pop-up you have to Accept) and/or by SMS.
- **Preparation guides.** A searchable library ("gastroscopy": stop eating,
  take your passport, arrange a lift) with a checklist and timed reminders.
- **Log and vaccination passport.** Everything done or missed, by category,
  with photos/PDFs of results.

## Project layout

```
StartSchool_2026/
├── query.sql           schema + seed data: guidelines, procedure library (safe to re-run)
├── migrations/         one-off upgrades for databases made by an older query.sql
├── requirements.txt
├── tests/              pytest - planner, reminder rules, LV grammar, phone numbers
├── venv/               (gitignored)
└── app/
    ├── .env            DB credentials + JWT secret (gitignored)
    ├── .env.example    copy this to .env
    ├── main.py         routes
    ├── database.py     engine + session
    ├── models.py       SQLAlchemy tables
    ├── schema.py       Pydantic request/response shapes
    ├── crud.py         database reads/writes
    ├── auth.py         password hashing + JWT
    ├── planner.py      guidelines + your tasks + log -> late / upcoming / up to date
    ├── reminders.py    background loop: daily reminders + preparation reminders
    ├── texts.py        reminder / SMS wording in EN and LV
    ├── notifications.py  phone normalization + Twilio
    ├── uploads/        photos/PDFs attached to log entries (gitignored)
    └── static/         frontend (served by FastAPI)
        ├── login.html  sign in, language picker
        ├── signup.html onboarding step 1 (consent and profile follow in the app)
        ├── index.html  the app shell - screens switch by URL hash
        ├── script.js   every screen
        ├── i18n.js     every UI string in EN and LV, dates, Latvian number grammar
        ├── icons.js    inline SVG icons
        ├── auth.js     token storage + api() helper
        └── style.css   design tokens from design_test
```

## 1. Install MySQL

```bash
sudo apt update
sudo apt install mysql-server
sudo systemctl enable --now mysql     # start it, and start it on every boot
systemctl status mysql                # should say "active (running)"
```

## 2. Create the database and tables

On Ubuntu, MySQL's root account uses `auth_socket`: whoever is root on the
operating system is root inside MySQL, with no password. That is why every
admin command below uses `sudo`, and why plain `mysql` as yourself is denied.

```bash
cd ~/gkf/hackathons/StartSchool_2026
sudo mysql < query.sql
```

**Upgrading an existing database?** Run the migrations you have not run yet,
in order, each exactly once, then `query.sql` again for the new seed data:

```bash
sudo mysql < migrations/001_health_tracker.sql      # only if you still have users.birth_date + address/city
sudo mysql < migrations/002_plans_and_procedures.sql
sudo mysql < query.sql
```

Both keep every account. 002 turns `birth_year` into a birth date of
1 January that year (fix it in Profile), maps the old family risk factors to
the new personal/family ones, and drops the snooze table: reminders now
repeat daily until done. Existing users are shown the consent screen once.

## 3. Create the application's database user

The app does not connect as root. Give it its own limited account, which may
only touch the `MNS` database:

```bash
sudo mysql
```

Then, at the `mysql>` prompt:

```sql
CREATE USER IF NOT EXISTS 'mns_user'@'localhost' IDENTIFIED BY 'Mns-Dev-2026';
GRANT ALL PRIVILEGES ON MNS.* TO 'mns_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;
```

The username and password must match `app/.env`.

If MySQL answers `ERROR 1819 ... does not satisfy the current policy
requirements`, the `validate_password` plugin is active. Check its rules with
`SHOW VARIABLES LIKE 'validate_password%';` — at `MEDIUM` a password needs 8+
characters, upper *and* lower case, a digit, and a special character.
`Mns-Dev-2026` satisfies that.

Check it worked:

```bash
mysql -u mns_user -p MNS -e "DESCRIBE users;"
```

## 4. Configure the app

```bash
cp app/.env.example app/.env
```

Edit `app/.env` and set `DB_PASSWORD` to the password from step 3, then
generate a signing key for the tokens:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

Paste that as `JWT_SECRET`. Anyone holding this value can forge a login, so
`.env` is gitignored — never commit it.

## 5. Install the Python dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

A venv stores absolute paths, so it breaks if you rename or move the project
folder (`bad interpreter: No such file or directory`). Fix: `rm -rf venv` and
redo this step.

## 6. Run it

```bash
source venv/bin/activate
cd app
uvicorn main:app --reload
```

Run it from **inside `app/`**. The modules import each other flatly
(`import crud`), so `app/` has to be the working directory. `--reload`
restarts the server whenever you save a file.

| URL | What it is |
|---|---|
| http://127.0.0.1:8000/ | the app (redirects to login if you have no token) |
| http://127.0.0.1:8000/docs | interactive API docs — try endpoints here |

## API

All routes except signup/login need `Authorization: Bearer <token>`.
Full request/response shapes are at http://127.0.0.1:8000/docs.

| Method | Path | Screen | Purpose |
|---|---|---|---|
| POST | `/api/signup` | Sign up 1/3 | name, surname, email, password, phone?, language |
| POST | `/api/login` | Sign in | email + password -> JWT |
| GET | `/api/me` | — | you; `profile_complete: false` = onboarding unfinished |
| POST | `/api/me/consent` | Sign up 2/3 | agree to the plain-language data notice |
| PUT | `/api/me/profile` | Sign up 3/3, Profile | birth date, gender, country, personal/family conditions |
| PATCH | `/api/me/settings` | Profile > Reminders | language, daily reminders on/off, how early, push/SMS, phone |
| GET / DELETE | `/api/me/export`, `/api/me` | Privacy | download everything / delete the account |
| GET | `/api/home` | Home | pop-up, status strip counts, coming up, preparations |
| GET | `/api/schedule?source=all\|recommended\|mine` | Schedule | every item with last done and due date |
| GET | `/api/calendar?month=2026-09` | Schedule | everything dated in a month (due, done, missed, appointments) |
| GET | `/api/checkups/{id}` | Item | guideline, source, more info, prep, your history |
| POST | `/api/checkups/{id}/done` | Item | mark done (today or a past date) - clears its reminders |
| GET / POST | `/api/tasks` | Add | your own tasks: repeating or manual dates, doctor, specialty |
| GET / DELETE | `/api/tasks/{id}` | Task | one task with all its dates |
| POST | `/api/tasks/{id}/dates` | Task | add a manual date |
| POST | `/api/task-events/{id}/done`, `/missed` | Task, pop-up | finish one date; a repeating task gets its next one |
| GET | `/api/categories` | Log | categories you have anything in |
| GET / POST | `/api/log?category=` | Log | done + missed, newest first / "add your own" entry |
| DELETE | `/api/log/{id}` | Log | remove an entry |
| POST / GET | `/api/log/{id}/attachment` | Log | upload / download a photo or PDF (≤10 MB) |
| GET | `/api/vaccinations` | Passport | each vaccine: doses, renew-by date |
| GET | `/api/procedures?q=` | Info | search the preparation library (EN or LV) |
| GET | `/api/procedures/{id}` | Info | guide + checklist + your plans for it |
| POST | `/api/procedures/{id}/plans` | Info | "Set reminder": appointment time + which lines to remind about |
| GET | `/api/prep-plans` | Home, Info | upcoming preparations |
| PATCH / DELETE | `/api/prep-items/{id}`, `/api/prep-plans/{id}` | Info | tick a checklist line / remove a plan |
| GET | `/api/reminders/pending` | pop-up | reminders waiting for Accept |
| POST | `/api/notifications/{id}/accept`, `/accept-all` | pop-up, inbox | accept |
| GET | `/api/notifications` | Inbox | every in-app reminder |
| POST | `/api/notifications/check` | Profile > Reminders | run the reminder check for yourself now |
| GET / POST | `/api/notifications/recipients`, `/send` | Message all patients | SMS broadcast |

The AI screen is interface only for now - there is no backend call yet.

### How the schedule is worked out

`checkup_types` is the guideline catalog, seeded by `query.sql`. Each row says
how often (`interval_months`) and for whom (`min_age`, `max_age`, `sex`,
`country`). A `risk_factor` (cancer, diabetes, heart) either makes the item
exist only for people who have it personally or in the family (`risk_only`),
or starts it earlier and repeats it more often (`risk_min_age`,
`risk_interval_months`) - e.g. cholesterol every 5 years from 40, but yearly
from 20 with heart disease in the family.

`planner.py` merges those with your own tasks: due date = last logged +
interval, or the date you gave. Late if that is past, upcoming within 30 days,
up to date otherwise. A recommended check never logged counts as due today -
"no record yet", not "late".

> The seeded guidelines and preparation steps are **demo content**. They have
> not been reviewed by a clinician, and the Latvian texts have not been
> proofread by a native speaker. Edit `query.sql` and re-run it to change
> them; the inserts are upserts.

### Reminders

`reminders.py` runs in the background every `REMINDER_EVERY_MINUTES`
(default 5, `0` = off) and does two things:

- **Daily reminders.** Anything late, or due within the user's "start
  reminding" window (default 1 week), gets a reminder **once a day, every
  day, until it is marked done**, from `REMINDER_SEND_HOUR` (default 9:00).
  In the app it is a pop-up with Accept / Mark as done / Not now; until
  accepted it keeps popping up. SMS is one combined text a day.
- **Preparation reminders.** Checklist lines you asked to be reminded about
  go out at their time (e.g. "stop eating" 8 hours before), once. If that
  time has already passed when you set it, they go out straight away.

Marking an item done deletes its waiting reminders and shows "Great job
taking care of yourself!". Every reminder is stored in `notifications`, and
"already reminded today?" is read from that table, so restarting the server
never sends a second batch. Reminder texts are written in the user's language
at send time (`texts.py`).

### SMS

Numbers are normalized to E.164 before sending: a number that already starts
with `+` is used as is, otherwise the user's country supplies the dial code
(`020123456` + Latvia -> `+37120123456`). Anything that cannot be resolved is
skipped and reported - one unusable number never costs the others their
message.

**Twilio is optional.** Leave `TWILIO_SID`, `TWILIO_TOKEN` and `TWILIO_FROM`
empty in `app/.env` and SMS runs in **dry run**: each message is logged to the
server console and recorded with status `dry_run`. Fill all three in and it
sends for real - no code change needed.

## Tests

```bash
venv/bin/python3 -m pytest
```

Login returns a token. The frontend stores it and sends it on every later
request as `Authorization: Bearer <token>`. To protect a new route, add the
dependency:

```python
@app.get("/api/something")
def something(user: User = Depends(auth.get_current_user)):
    ...   # `user` is the logged-in User row
```

## Useful MySQL commands

```bash
sudo mysql                                  # admin shell
mysql -u mns_user -p MNS                    # as the app's user

# inside the shell:
SHOW DATABASES;
USE MNS;
SHOW TABLES;
SELECT id, email, name, surname, birth_date, country FROM users;
SELECT * FROM notifications ORDER BY id DESC LIMIT 20;  # what reminders went out
DELETE FROM users WHERE email = 'test@example.com';   # remove a test account
DROP DATABASE MNS;                                    # start over, then rerun step 2
```

## Adding a new table

1. Write the `CREATE TABLE` in `query.sql`, and apply it with `sudo mysql < query.sql`.
2. Add the matching class to `models.py`.
3. Add its request/response shapes to `schema.py`.
4. Add its reads/writes to `crud.py`.
5. Add routes to `main.py`.

`query.sql` stays the source of truth for the schema — keep it and `models.py`
in step with each other.
