# CityCare Hospital — Explainable FOL Information Platform

CityCare is a responsive Flask application for a fictional hospital-information domain. It answers supported questions with the existing deterministic query processor, JSON knowledge base, and `pyDatalog` First-Order Logic engine. It does not use an LLM, external AI API, or fabricated hospital information, and it is not a medical diagnosis or treatment system.

## Start the application

From the project source folder:

```powershell
python -m pip install -r requirements.txt
python app.py
```

Open `http://127.0.0.1:5000/`.

## Application flow and routes

- `/` — public landing page with platform overview, workflow, and FAQ entry point.
- `/login` — administrator-only sign-in page for the secure CityCare workspace.
- `/roles` — compatibility redirect to the administrator login flow.
- `/dashboard` — authenticated administrator dashboard.
- `/faq`, `/doctors`, `/departments`, `/services`, `/reasoning`, `/about` — public/read-only information and explainability views.
- `/analytics` — live knowledge-base metrics and charts.
- `/knowledge-base`, `/admin/workspace` — administrator-only knowledge and account operations.

The authenticated sidebar is administrator-focused and all access restrictions are enforced by Flask routes and APIs.

## Roles and permissions

Only the `admin` role is supported. The login endpoint verifies the account’s password hash and stored role before creating a session, and all protected dashboard, knowledge-base, and administrative routes require administrator access.

## Accounts and first-admin setup

Accounts are persisted in SQLite (`citycare_users.db`) and use Werkzeug password hashes. There is no public registration. An authenticated administrator provisions accounts in **Admin → Provision an account**.

For compatibility with the prior academic prototype, first run seeds the pre-existing local demo administrator from `CITYCARE_ADMIN_USERNAME` / `CITYCARE_ADMIN_PASSWORD` (defaults remain `admin` / `admin123`). The credential is not displayed in the UI. Set these values and `CITYCARE_SECRET_KEY` to strong, unique values before any shared deployment. For HTTPS also set `CITYCARE_SECURE_COOKIES=1`.

Login failures use a generic response and are throttled per client address. Sessions are rotated at login, are HTTP-only and SameSite, logout clears the session, and all state-changing browser/API requests require a CSRF token.

## FOL architecture

```text
Browser → Flask route/API → query_processor.py → inference_engine.py (pyDatalog)
                                           ↘ reasoning_trace.py
knowledge_base.json ← knowledge_base.py (validation, atomic persistence, backups)
```

Facts are stored as predicates such as `specializes(kumar, orthopedics)`. Rules in `inference_engine.py` derive allowed conclusions, such as:

```text
works_in(D, Dep) <= specializes(D, Dep)
available_facility(H, F) <= has_facility(H, F) & facility(F)
```

The FAQ API calls `reasoning_trace.answer_question()` directly. Its expandable trace only presents logical queries, stored facts, rules, and conclusions confirmed by the actual engine.

## Theme and UI

The app uses centralized CSS variables for light and dark palettes. Theme selection is stored in `localStorage` as `citycare-theme`, honors system preference only when unset, applies before rendering, and redraws Chart.js labels/grid colors after changes. The application supports keyboard focus states, reduced motion, responsive side navigation, cards, charts, forms, and tables.

## Tests

```powershell
python -m unittest -v
```

The suite preserves original FOL/persistence regressions and adds Flask, authentication, role, CSRF, authorization, logout, account-provisioning, and route coverage. Test persistence uses temporary knowledge-base/account stores where relevant.

## Deployment limitations

This is a local academic prototype. Before production use, replace the Flask development server with a production WSGI deployment, use HTTPS, configure unique secrets and bootstrap credentials, move rate limits to a shared store, add audit logs/database migration controls, and bundle Chart.js locally if browser use must be completely offline.
