# MNS — Medical Notification System

FastAPI + SQLAlchemy + MySQL. A preventive-health tracker: you tell it your
birth year, sex, country and family risk factors, it works out which
screenings, check-ups and vaccinations apply to you, tracks when you last did
each one, and reminds you (in-app and by SMS) when something is overdue or
coming up.

## Project layout

```
StartSchool_2026/
├── query.sql           schema + the guideline catalog (safe to re-run)
├── migrations/         one-off upgrades for databases made by an older query.sql
├── requirements.txt
├── tests/              pytest - planner, reminder rules, phone numbers
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
    ├── planner.py      guidelines + log -> overdue / due soon / up to date
    ├── reminders.py    background loop that sends reminders
    ├── notifications.py  phone normalization + Twilio
    ├── uploads/        photos/PDFs attached to log entries (gitignored)
    └── static/         frontend (served by FastAPI)
        ├── index.html  the app shell (one page, screens switch by URL hash)
        ├── login.html
        ├── signup.html onboarding step 1
        ├── auth.js     shared: token storage + api() helper
        ├── script.js   every screen: home, schedule, item detail, log,
        │               prep, settings, inbox, passport, privacy, broadcast
        └── style.css
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

**Upgrading a database made by the old, user-system-only `query.sql`?** Run
the migration once first, then `query.sql` again:

```bash
sudo mysql < migrations/001_health_tracker.sql   # reshapes `users` - run ONCE
sudo mysql < query.sql                           # new tables + catalog
```

The migration keeps every account. It converts `birth_date` to `birth_year`
and drops `surname`, `address` and `city`, which the new onboarding no longer
asks for.

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
| POST | `/api/signup` | Sign in | create an account (email, password, name, optional phone) |
| POST | `/api/login` | Sign in | exchange email + password for a JWT |
| GET | `/api/me` | — | your profile + settings; `profile_complete: false` → show onboarding |
| PUT | `/api/me/profile` | Profile setup | birth year, sex, country, risk factors (+ "Other" text) |
| PATCH | `/api/me/settings` | Settings | notifications style, push/SMS channels, language, phone |
| GET | `/api/me/export` | Privacy & data | everything we hold about you, as JSON |
| DELETE | `/api/me` | Privacy & data | delete the account, log and uploaded files |
| GET | `/api/home` | Home | counts, the urgent card, "coming up", unread count |
| GET | `/api/schedule?coverage=all\|state\|private` | Schedule | every applicable item, most urgent first |
| GET | `/api/checkups/{id}` | Item detail | status, guideline text, more info, prep, your history |
| POST | `/api/checkups/{id}/done` | Item detail | "Mark as done" (today, or a given date) |
| POST | `/api/checkups/{id}/snooze` | Item detail | "Remind me later" (`{"days": 30}`) |
| GET | `/api/checkup-types` | Log | catalog for the "What did you do?" picker |
| GET/POST | `/api/log` | Log | list / add entries - backdating allowed, future dates rejected |
| DELETE | `/api/log/{id}` | Log | remove an entry |
| POST/GET | `/api/log/{id}/attachment` | Log | upload / download a photo or PDF (≤10 MB) |
| GET | `/api/prep` | Prep | preparation guides for what is overdue or due soon |
| GET | `/api/vaccinations` | Vaccination passport | each vaccine, every dose, next due |
| GET | `/api/notifications` | inbox | in-app reminders, newest first, + unread count |
| POST | `/api/notifications/{id}/read`, `/read-all` | inbox | mark read |
| POST | `/api/notifications/check` | — | run the reminder check for yourself now |
| GET | `/api/notifications/recipients` | Send Notification | how many users have a phone number |
| POST | `/api/notifications/send` | Send Notification | broadcast an SMS to everyone with a number |

### How the schedule is worked out

`checkup_types` is the guideline catalog, seeded by `query.sql`. Each row says
how often (`interval_months`) and for whom (`min_age`, `max_age`, `sex`,
`country`). A `risk_factor` either makes the item exist only for people who
ticked that box (`risk_only`), or starts it earlier and repeats it more often
(`risk_min_age`, `risk_interval_months`) — e.g. cholesterol every 5 years from
40, but yearly from 20 if heart disease runs in the family.

`planner.py` combines that with your log: due date = last done + interval.
Overdue if that is past, due soon within 30 days, up to date otherwise. An item
never logged counts as due today — "no record yet", not "overdue".

> The seeded guidelines are **demo data**. They have not been reviewed by a
> clinician — check them against vmnvd.gov.lv before relying on them. Edit
> `query.sql` and re-run it to change them; the insert is an upsert.

### Reminders

`reminders.py` runs in the background (started with the server) every
`REMINDER_EVERY_MINUTES` (default 60, `0` = off). For each user it looks at
the schedule and sends a reminder for items that are overdue or coming up:

| Setting | Reminds about | Repeats at most |
|---|---|---|
| `off` | nothing | — |
| `gentle` (default) | overdue, and due within 7 days | once a month per item |
| `frequent` | overdue, and due within 30 days | once a week per item |

- **push** → a row in `notifications`, shown by `GET /api/notifications`
- **sms** → one combined text per run (not one per item)
- **"Remind me later"** silences an item completely until the snooze ends;
  logging the item clears the snooze.

Every reminder is stored in `notifications`, and the cooldown is read from
that same table, so restarting the server never sends a second batch.

### SMS

Numbers are normalized to E.164 before sending: a number that already starts
with `+` is used as is, otherwise the user's country supplies the dial code
(`020123456` + Latvia → `+37120123456`). Anything that cannot be resolved is
skipped and reported — one unusable number never costs the other recipients
their message.

**Twilio is optional.** Leave `TWILIO_SID`, `TWILIO_TOKEN` and `TWILIO_FROM`
empty in `app/.env` and SMS runs in **dry run**: each message is logged to the
server console and recorded with status `dry_run`, so nothing is actually
sent. Fill all three in and it starts sending for real — no code change needed.

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
SELECT id, email, name, birth_year, country FROM users;
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
