# PinIt
A web app for your notes

[Link to live site]()

![Hero image]()


## Table of content

- [Architecture](#architecture)

- [Features](#features)

- [Security](#security)

- [Accessibility](#accessibility)

- [Testing](#testing)
  - [Tests](#tests)
  - [Validator Testing](#validator-testing)
  - [Fixed bugs](#fixed-bugs)
  - [Unfixed bugs](#unfixed-bugs)

- [Deployment](#deployment)
  - [Live Website](#live-website)
  - [Local Deployment](#local-deployment)
  - [Production](#production)
  - [Database migrations](#database-migrations)
  - [Environment variables](#environment-variables)
  - [Testing emails with Mailtrap](#testing-emails-with-mailtrap)
  - [Formatting templates](#formatting-templates)
  - [JavaScript bundle](#javascript-bundle)

- [Technologies used](#technologies-used)
  - [Languages](#languages)
  - [Backend](#backend)
  - [Frontend](#frontend)
  - [Tooling](#tooling)
  - [Hosting](#hosting)

- [Acknowledgements](#acknowledgements)


## Architecture

The app uses Flask’s **application factory** (`create_app` in `app/__init__.py`). Extensions (SQLAlchemy, Migrate, Login, Limiter, Mailman) are created in `app/extensions.py` and initialized there, then blueprints are registered:

| Blueprint | Role |
|-----------|------|
| `main` | Home / entry routing for signed-in users |
| `auth` | Register, login, logout, email verification, change password, delete account |
| `profile` | View and update username / email |
| `dashboards` | Create, rename, delete, and leave boards; settings |
| `notes` | Create, update, and delete notes; toggle checklist items |
| `invites` | Owner sends, resends, and revokes dashboard invitations |
| `invitations` | Invitee opens a signed invite link and accepts or declines |

### Layout

| Path | Role |
|------|------|
| `app/models/` | SQLAlchemy models (`User`, `Dashboard`, `Note`, `Invite`) |
| `app/routes/` | Blueprint handlers |
| `app/helpers/` | Shared domain logic (access checks, invites, email, account deletion, validation) |
| `app/templates/` | Jinja templates |
| `static/` | CSS and JS (esbuild bundle under `static/scripts/`) |
| `migrations/` | Flask-Migrate / Alembic schema history |
| `tests/` | Pytest suite |

### Data model

- **User** — account credentials, email verification flag, owned dashboards and authored notes.
- **Dashboard** — a named board owned by one user. Each account gets a default `Home` board on register. Collaboration is not a separate membership table: an accepted, non-revoked `Invite` grants access.
- **Invite** — email + optional `user_id`, status (`pending` / `accepted` / `rejected`), and soft revoke via `deleted_at`. Unique per `(dashboard_id, email)`. Tokenized invite links are handled under `invitations`.
- **Note** — belongs to a dashboard and (usually) an author (`owner_id`). Content is a flat JSON list of **storage blocks** (`paragraph` / `todo` in `Notes.content_json`). The client maps those to and from Editor.js save JSON (`paragraph` + checklist `list` blocks) in `static/scripts/note-editor.js` and `app/routes/notes.py`.

Access helpers in `app/helpers/dashboard_access.py` decide who can open a board and who can edit or delete a note: the note author or the dashboard owner.

### Sharing and collaborations

Dashboard owners invite collaborators by email. Known users can accept or decline from an invite page; pending invites for unregistered emails wait until that address signs up. Leaving a board or revoking a collaborator soft-deletes the invite (`deleted_at`) without removing notes the collaborator already created.

### Account deletion

Permanent deletion is password-confirmed under `auth` and orchestrated in `app/helpers/account_deletion.py` in one transaction:

1. Notes the user authored on **other people's** dashboards are kept: `owner_id` is cleared and `owner_deleted_at` is set (a check constraint requires exactly one of those fields).
2. Dashboards the user owns are deleted; database cascades remove those boards' notes and invites (including notes written by collaborators).
3. The user row is deleted; their membership invites cascade away.

Surviving notes with a deleted author remain manageable by the dashboard owner.

[Back to the top](#pinit)

## Features

- **Authentication** — Register, log in, and log out with session-based auth (Flask-Login)
- **Email verification** — Verify email address and resend the link from the profile (Flask-Mailman)
- **Change password** — Update password after confirming the current one
- **Delete account** — Permanently delete the account; owned dashboards and their notes are removed, while notes authored on others’ boards stay and are marked as from a deleted user
- **Profile** — View and update username and email inline
- **Dashboards** — Organize notes into named boards (including a default `Home`), switch between them, rename, and delete non-default boards
- **Dashboard sharing** — Invite collaborators by email, accept or decline invite links, and see shared boards in the nav
- **Collaborator management** — Revoke access from settings, or leave a shared board; notes the collaborator already created stay on the board
- **Notes** — Create, edit, and delete notes; title plus rich body content. Collaborators can add notes; the dashboard owner can manage any note on their board
- **Editor.js editor** — Block editing for paragraphs and checklists (`--` shortcut to start a checklist item)
- **Checklist todos** — Toggle items from the note view without a full page reload
- **Modals** — Confirm logout, add or delete a dashboard, leave a board, revoke a collaborator, and delete a note in accessible dialogs
- **Flash messages** — Success and error feedback after actions

[Back to the top](#pinit)

## Security

- **CSRF** — State-changing forms include a CSRF token; requests without a valid token are rejected
- **Rate limiting** — Auth routes are limited with Flask-Limiter to slow brute-force attempts
- **Sessions** — Cookies use `HttpOnly`, `SameSite=Lax`, and `Secure`; `SECRET_KEY` signs the session. `Secure` is on unless `SESSION_COOKIE_SECURE=false` (needed only for local development over plain http)
- **XSS** — Jinja autoescaping is on for all templates. Note content is stored as plain text and HTML-escaped before it is handed to Editor.js, whose tools render block text via `innerHTML`. Form values echoed back after a validation error are the sanitized blocks, never the raw request body
- **Content Security Policy** — Every response sends a CSP that allows scripts only from the app and the pinned CDNs (`script-src` has no `'unsafe-inline'`, and `script-src-attr 'none'` blocks inline event handlers), so no inline `<script>` or `onclick=` is allowed in templates. Adding a new third-party asset (CDN, font, icon kit) means adding its domain to `CONTENT_SECURITY_POLICY` in `app/__init__.py`. `style-src` does include `'unsafe-inline'` because Editor.js and the Font Awesome kit inject `<style>` elements at runtime. Responses also send `X-Content-Type-Options: nosniff` and `Referrer-Policy: same-origin`

[Back to the top](#pinit)

## Accessibility

The UI is built with keyboard and screen-reader use in mind. Highlights:

- **Landmarks** — `lang` on `<html>`, a skip link to `#main-content`, labelled `<nav>` regions, and a single primary page `<h1>`.
- **Names** — Icon-only controls use `aria-label`; decorative Font Awesome icons use `aria-hidden="true"`. Tooltips are visual aids only and also show on `:focus-within`.
- **Forms** — Inputs have real labels; validation uses `aria-invalid`, `aria-describedby`, and `role="alert"`, with focus moved to the error or invalid field.
- **Dialogs** — Modals use `role="dialog"`, `aria-modal`, `aria-labelledby`, background `inert` while open, Escape to close, and focus return to the trigger. Dialog titles are `<h2>`.
- **Menus** — Options and dashboards toggles expose `aria-expanded` / `aria-controls`, close on Escape (and outside click), and manage focus on open/close.
- **Focus** — Global `:focus-visible` outlines. Opening add/edit note focuses the title after Editor.js is ready (`autofocus: false`) so the field is actually editable.
- **Live updates** — Flash messages use `role="status"` / `aria-live`. Async checklist toggle failures announce via `#a11y-status`.
- **Motion** — Page transitions, menus, and tooltips respect `prefers-reduced-motion`.

Editor.js checklists are enhanced for keyboard use (Tab between items; Space/Enter on checkboxes).

During development, Cursor loads project accessibility guidance from `.cursor/rules/accessibility.mdc`. For a full review, use the project skill in `.cursor/skills/accessibility-audit/` (e.g. ask the agent to run an accessibility audit).

[Back to the top](#pinit)

## Testing 

### Validator Testing

[Back to the top](#pinit)

## Deployment

### Live Website

The live version of this program is available here.

[Click here to open]()


### Local Deployment
  - For first time local deployment follow these steps:
    - Clone the repository
    - Create a new virtual environment `python3 -m venv .venv`
    - Activate virtual environment `source .venv/bin/activate`
    - Install packages with `pip install -r requirements-dev.txt` (includes the runtime packages in `requirements.txt`, plus local tools such as djLint and python-dotenv). Production and hosting should install only `pip install -r requirements.txt`.
    - Create a PostgreSQL database and configure its URL. Copy `.env.example` to a local `.env` file, then replace the placeholder values. The database URL format is `postgresql+psycopg2://USERNAME:PASSWORD@HOST:5432/DATABASE_NAME`.
    - Create or update the database schema with `flask --app run db upgrade`.
    - Run locally using `python run.py`

  - For subsequent runs simply:
    - Start postgres `brew services start postgresql@18`
    - Activate virtual environment `source .venv/bin/activate`
    - Run locally using `python run.py`


  - To stop running locally
    - Ctrl + C
    - Deactivate virtual environment `deactivate`
    - Quit postgres `\q`
    - Stop postgres `brew services stop postgresql@18`

  
  #### Create a Postgres Local db for the first time
  - Install postgresql `brew install postgresql@18`
  - Start `brew services start postgresql@18`
  - List users `\du+`
  - Login with admin role `/opt/homebrew/opt/postgresql@18/bin/psql -d postgres`
  - Check current user `SELECT current_user;`
  - Create new user `CREATE ROLE pinitt_user LOGIN PASSWORD 'choose-a-new-password';`
  - Create a db `CREATE DATABASE pinit OWNER pinit_user;`
  - Exit `\q`
  - Restore secure local authentication in `/opt/homebrew/var/postgresql@18/pg_hba.conf` by changing both trust values back to `scram-sha-256`
  - then restart `brew services restart postgresql@18`
  - Login with new user `/opt/homebrew/opt/postgresql@18/bin/psql -U pinit_user -d pinit -W`


### Production

The live app runs on [Render](https://render.com/) with [Neon](https://neon.tech/) as the PostgreSQL database. Leave Render's root directory empty. Render installs `requirements.txt` during the build and injects environment variables into the process. Start command:

```bash
gunicorn --bind 0.0.0.0:$PORT "app:create_app()"
```

`python run.py` is for local development only. `load_dotenv()` lives in `run.py` and is not part of this process. Set `DATABASE_URL`, `SECRET_KEY`, and any mail variables in the Render service settings. `create_app()` reads them from the environment.

For the running app, set `DATABASE_URL` to Neon’s pooled connection string (the host contains `-pooler`) and use the `postgresql+psycopg2://` scheme. Apply schema changes with the direct Neon URL, not the pooler:

```bash
flask --app run db upgrade
```

The pooler is PgBouncer in transaction mode, and Flask-Migrate’s advisory lock needs a direct connection.


### Database migrations

Database schema changes are tracked with Flask-Migrate and Alembic.

1. Update the SQLAlchemy model(s).
2. Generate a migration:
   ```bash
   flask --app run db migrate -m "describe the schema change"
   ```
3. Review the new file in `migrations/versions/` before applying it.
4. Apply the migration:
   ```bash
   flask --app run db upgrade
   ```

Never edit an already-applied migration. Create a new migration for every later schema change, and back up production data before running `db upgrade`.


### Environment variables

The app requires `DATABASE_URL` to connect to PostgreSQL and `SECRET_KEY` to securely sign sessions and CSRF tokens. Optional mail settings (`MAIL_*`) and `FLASK_DEBUG` are listed in `.env.example`.

Locally, copy `.env.example` to `.env` and fill in real values. `run.py` calls `load_dotenv()` before creating the app, so `python run.py` and `flask --app run …` read that file. python-dotenv is a development dependency (`requirements-dev.txt`); it does not override variables that are already set in the shell.

When deploying, set the same names in the hosting provider's secret/configuration settings. The committed `.env.example` only documents the required format.

### Testing emails with Mailtrap

Locally, emails (such as verification links) are sent to a [Mailtrap](https://mailtrap.io/) sandbox inbox instead of real addresses. Mailtrap catches every message, so you can open and click links without spamming anyone.

1. Create a free Mailtrap account and open **Email Testing → Inboxes**, then select (or create) an inbox.
2. Open the inbox's **Integration** tab, choose **SMTP**, and copy the host, port, username and password.
3. Set the mail variables in your local `.env`:
   ```bash
   MAIL_SERVER=sandbox.smtp.mailtrap.io
   MAIL_PORT=2525
   MAIL_USE_TLS=true
   MAIL_USERNAME=your_mailtrap_username
   MAIL_PASSWORD=your_mailtrap_password
   MAIL_DEFAULT_SENDER=PinIt <noreply@example.com>
   MAIL_BACKEND=smtp
   ```
   `MAIL_BACKEND=smtp` is required. The `.env.example` default, `console`, prints emails in the terminal instead of sending them.
4. Restart the app (`python run.py`) so the new values are loaded.

To test the flow, do any of the following, then open the Mailtrap inbox:

- Register a new account.
- On the profile page, click the button that resends the verification email.
- Change your email address from the profile page.

Click the verification link in the email. Links point to the host the app is running on (e.g. `http://127.0.0.1:5000/verify-email/...`), so the app must still be running when you open them.

If no email arrives, check the terminal. SMTP errors are caught and shown as a flash message rather than crashing the request. The usual causes are wrong credentials, `MAIL_BACKEND` still set to `console`, or a port other than 25, 465, 587 or 2525.

Automated tests don't use Mailtrap. `tests/conftest.py` sets `MAIL_BACKEND` to `locmem`, which keeps sent messages in memory for assertions.

### Formatting templates

Jinja templates are linted and formatted with [djLint](https://djlint.com/). Defaults live in `pyproject.toml` (`profile = "jinja"`, `files = ["app/templates"]`). djLint is a development dependency: install it with `pip install -r requirements-dev.txt`.

With the virtual environment activated:

```bash
# Check formatting without changing files
djlint - --check

# Reformat templates
djlint - --reformat

# Lint templates
djlint - --lint
```

The `-` source is required when `files` is set in the config; djLint then uses `app/templates` automatically.

In Cursor/VS Code, install the djLint extension and set it as the default formatter for Jinja/HTML files if you want format-on-save.

### JavaScript bundle

`app.js` is the esbuild entry and imports:

- `ui-common.js` — shared helpers (button loading, form errors, skip link)
- `page-transitions.js` — same-origin navigation transitions
- `disclosures.js` — options and dashboards menus
- `modals.js` — dialog open/close and AJAX submit
- `note-editor.js` — Editor.js note body and checklist toggles
- `notes-ui.js` — add / edit / cancel note forms
- `profile-inline.js` — profile inline field editor

For any change, edit the source files, then rebuild.

First time (and after `package.json` changes):

```bash
npm install
npm run build
```

While iterating, rebuild on save:

```bash
npm run watch
```

`node_modules/` is gitignored. The generated bundle is committed so `python run.py` works without Node. Commit an updated `app.bundle.js` with any JavaScript source change.

[Back to the top](#pinit)

## Technologies used

### Languages

- Python
- HTML / Jinja2 templates
- CSS
- JavaScript

### Backend

- [Flask](https://flask.palletsprojects.com/) — web framework (application factory pattern)
- [Gunicorn](https://gunicorn.org/) — production WSGI server
- [Flask-SQLAlchemy](https://flask-sqlalchemy.palletsprojects.com/) — ORM integration
- [SQLAlchemy](https://www.sqlalchemy.org/) — database models and queries
- [Flask-Migrate](https://flask-migrate.readthedocs.io/) / [Alembic](https://alembic.sqlalchemy.org/) — database migrations
- [Flask-Login](https://flask-login.readthedocs.io/) — session-based authentication
- [Flask-Limiter](https://flask-limiter.readthedocs.io/) — rate limiting on auth routes
- [Flask-Mailman](https://flask-mailman.readthedocs.io/) — outbound email (verification and invites)
- [Werkzeug](https://werkzeug.palletsprojects.com/) — password hashing
- [psycopg2](https://www.psycopg.org/) — PostgreSQL driver
- [PostgreSQL](https://www.postgresql.org/) — primary database

### Frontend

- [Jinja2](https://jinja.palletsprojects.com/) — server-rendered templates
- [Editor.js](https://editorjs.io/) — block-style note content editing (paragraphs and checklists)
- [jQuery](https://jquery.com/) — client-side interactions (modals, forms, options menu)
- [esbuild](https://esbuild.github.io/) — bundles custom JS into `app.bundle.js`
- [Font Awesome](https://fontawesome.com/) — icons
- [Google Fonts](https://fonts.google.com/) — Mulish and Shadows Into Light

### Tooling

- [Cursor](https://cursor.com/) — AI-assisted development (rules and skills for accessibility and workflows)
- [pytest](https://docs.pytest.org/) / [pytest-flask](https://pytest-flask.readthedocs.io/) — test suite (listed in `requirements-dev.txt`)
- [djLint](https://djlint.com/) — Jinja/HTML template linting and formatting (listed in `requirements-dev.txt`)
- [python-dotenv](https://github.com/theskumar/python-dotenv) — loads local `.env` in `run.py` (listed in `requirements-dev.txt`)
- [Mailtrap](https://mailtrap.io/) — local email sandbox for verification and invite testing
- Virtualenv — local Python environment
- `requirements.txt` — runtime packages for running and deploying the app
- `requirements-dev.txt` — runtime packages plus local development tools
- `package.json` — esbuild for the client JS bundle (`npm run build` / `npm run watch`)

### Hosting

- [Render](https://render.com/) — production web service
- [Neon](https://neon.tech/) — production PostgreSQL

[Back to the top](#pinit)

## Acknowledgements
