# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

InsFlow — Django service for an online insurance broker. Handles the full lifecycle of insurance quote requests on leased assets: parse incoming Excel application, generate a request email body, collect insurer offers (manually or by parsing each insurer's Excel response), and export the resulting summary (full + simplified client version).

UI, model labels, status names, and most user-facing strings are in **Russian** (Cyrillic). Preserve existing Cyrillic verbose names and choice labels — do not anglicize them.

## Tech stack

- Python 3.11 (Docker), Django 4.2
- PostgreSQL in prod, SQLite for local dev (toggled via `DB_ENGINE`)
- pandas + openpyxl + xlrd for Excel I/O
- Gunicorn + Nginx + Certbot for production (docker-compose)

## Common commands

```bash
# Local setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

# DB + auth groups (required — auth model depends on these groups)
python manage.py migrate
python manage.py setup_user_groups
python manage.py create_default_users --create-test-user   # optional

# Run dev server
python manage.py runserver

# Tests — full suite
python manage.py test
# Tests — CI smoke subset (matches .github/workflows/tests.yml)
python manage.py test insurance_requests.tests summaries.test_company_matcher summaries.test_templatetags
# Single test
python manage.py test summaries.test_company_matcher.CompanyMatcherTests.test_exact_match

# Maintenance commands
python manage.py auto_close_stale_summaries [--dry-run] [--days=30]
python manage.py backup_db --format pgdump --output-dir /app/backups --keep 10
```

## Architecture

### Apps

- `onlineservice/` — project config: settings, root URL conf, custom middleware (domain routing + HTTPS), landing view, context processors.
- `insurance_requests/` — incoming requests: model, Excel ingestion entrypoint, email body generation, auth middleware, role decorators.
- `summaries/` — quote summaries and individual offers, Excel exports, multiple-file response upload, analytics dashboards.
- `core/` — shared services: `excel_utils.ExcelReader` (parses incoming applications), `templates.py` (email body templater), branch-name normalization map.
- `backup/` — admin-only DB backup management command (`backup_db`); the model is `managed = False` and exists purely so the action shows up in Django admin.

### Domain routing (important)

`onlineservice.middleware.DomainRoutingMiddleware` splits traffic by `Host`:

- `MAIN_DOMAINS` (e.g. `insflow.ru`, `insflow.tw1.su`) → landing page only; the app URLs return 404 with a redirect hint.
- `SUBDOMAINS` (e.g. `zs.insflow.ru`, `zs.insflow.tw1.su`) → full Django app.
- `DEVELOPMENT_DOMAINS` (`localhost`, `127.0.0.1`, `testserver`) → full app, no HTTPS redirect.

When changing URL routes, remember that root `/` is dispatched by `domain_aware_redirect` in `onlineservice/urls.py` based on the host, not statically.

### Auth model

Access is gated by two Django groups: **`Администраторы`** and **`Пользователи`** (Cyrillic, exact match). Decorators in `insurance_requests/decorators.py` (`admin_required`, `user_required`) check group membership; `insurance_requests.middleware.AuthenticationMiddleware` blocks anonymous traffic except for a public allowlist (`/login/`, `/logout/`, `/admin/login/`, `/static/`, `/media/`, `/healthz/`, `/landing/`). Login rate limiting is configurable via `LOGIN_*` env vars.

### Excel ingestion

`core.excel_utils.ExcelReader` is parameterised on two axes:

- `application_format`: `casco_equipment` (КАСКО / спецтехника) vs `property` (имущество).
- `application_type`: `legal_entity` vs `individual_entrepreneur` — the IP variant applies a row offset to the same template.

Invalid values fall back to `legal_entity` / `casco_equipment` with a warning. Branch names are normalized via the `BRANCH_MAPPING` dict at the top of `excel_utils.py` — extend that dict when new full-form branch names appear.

### Insurer offer ingestion and the company-name contract

- Single-file upload: `summaries/services/excel_services.py`.
- Bulk upload: `summaries/services/multiple_file_processor.py` — caps: **10 files max, 1 MB per file, 10 MB total, `.xlsx` only**.
- Every `InsuranceOffer.save()` runs `full_clean()`, which calls `summaries.constants.is_valid_company_name`. The set of valid names comes from the `InsuranceCompany` model, with `FALLBACK_INSURANCE_COMPANIES` in `summaries/constants.py` as a hard-coded backstop. **Saving an offer with a name not in that set raises `ValidationError`** — when adding a new insurer, create the `InsuranceCompany` row (or use `'другое'`) before importing offers.
- `InsuranceOffer` has `unique_together = ['summary', 'company_name', 'insurance_year']` — one offer per (summary, company, year). Multi-year offers are modelled as multiple rows with the same `company_name`.

### Workflow / status machine

```
InsuranceRequest:  uploaded → email_generated → emails_sent
InsuranceSummary:  collecting → ready → sent → completed_accepted | completed_rejected
```

A summary can only be created after the request is in `emails_sent` (see `InsuranceRequest.can_create_summary`). Email sending is **not** wired to SMTP — the "send" action only flips the status. `completed_accepted` requires `selected_company` (and `selected_franchise_variant` when the company has both variants — see `InsuranceSummary.requires_variant_choice`).

### Time zones

Server runs `Europe/Moscow`. Models persist UTC, but many methods (`*_moscow` properties, `to_dict`, `response_deadline` default) explicitly convert via `pytz`. Use the `*_moscow` accessors when rendering deadlines and creation times.

### HTTPS / security

`ENABLE_HTTPS` env flag toggles the whole HTTPS stack: HSTS, secure cookies, `SECURE_SSL_REDIRECT`, `SECURE_PROXY_SSL_HEADER`, and *renames* session/CSRF cookies to `sessionid_secure` / `csrftoken_secure`. CSRF trusted origins are auto-derived from `ALLOWED_HOSTS` if not set explicitly. `HTTPSSecurityMiddleware` adds the response headers.

## Deployment

`main` is the deploy branch. Pushing to `main` triggers `.github/workflows/deploy_timeweb.yml`, which builds an image to GHCR and SSHes into the Timeweb host to redeploy. Do not push to `main` casually — it ships to production. The deploy script auto-detects SSL availability and falls back to HTTP-only by rewriting `.env` in place if Let's Encrypt fails.

For DB backups before migrations, the workflow calls `python manage.py backup_db` inside the web container (pgdump, falls back to JSON).

## Specs and historical context

`.kiro/specs/<feature-name>/` contains `requirements.md` / `design.md` / `tasks.md` per initiative. When picking up a feature whose name matches one of those folders, read the spec first — it captures decisions and edge cases that aren't in the code.

## Conventions

- Don't introduce a REST API or SMTP integration — both are intentionally out of scope (see `README.md` "Важные текущие ограничения").
- File upload limit is 10 MB (`FILE_UPLOAD_MAX_MEMORY_SIZE`); raising it requires changing both Django settings and Nginx.
- Use `verbose_name` / `help_text` in Russian for new model fields to match the surrounding code.
- Logging: per-feature handlers are configured in `settings.LOGGING` (e.g. `summaries.services.multiple_file_processor`, `onlineservice.middleware`, `onlineservice.views`). Prefer logging through these named loggers over the root logger.
