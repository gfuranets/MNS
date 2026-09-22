# MNS — Medical Notification System

FastAPI + SQLAlchemy + MySQL. Currently implemented: **the user system only**
(signup, login, profile). Blood samples, notifications and the medical card
come next.

## Project layout

```
StartSchool_2026/
├── query.sql           schema — the `users` table
├── requirements.txt
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
    └── static/         frontend (served by FastAPI)
        ├── index.html  dashboard
        ├── login.html
        ├── signup.html
        ├── auth.js     shared: token storage + api() helper
        ├── script.js   dashboard logic
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

| Method | Path | Auth | Purpose |
|---|---|---|---|
| POST | `/api/signup` | — | create an account |
| POST | `/api/login` | — | exchange email + password for a JWT |
| GET | `/api/me` | Bearer | the logged-in user's profile |

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
SELECT id, email, name, surname FROM users;
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
