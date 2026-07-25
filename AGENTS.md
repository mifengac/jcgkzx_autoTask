# AGENTS.md

## Purpose

This file gives coding agents the minimum project context needed to make safe, targeted changes in this repository.

Prefer small, explicit edits. Preserve existing behavior unless the task clearly requires a behavior change.

## Project Summary

JCGKZX AutoTask is an internal monitoring and notification platform with two main execution paths:

1. Theme monitoring: fetch one source once, filter the data into multiple topics, resolve receivers, render SMS content, and persist run/send logs.
2. Custom script tasks: upload a ZIP package, execute `run(context) -> list[dict]`, render templates, match receiver rules, and send SMS.

Primary stack:

- Backend: FastAPI, SQLAlchemy, APScheduler, Pydantic Settings
- Frontend: static HTML/CSS/JavaScript served directly by FastAPI
- Runtime integrations: Kingbase or PostgreSQL-compatible database; SMS via internal HTTP gateway `oracle-sms-gateway` (host port 5011)
- Deployment target: Docker on company-internal Ubuntu 22.04 hosts with no internet access
- Deploy order: **upgrade and start `oracle-sms-gateway` before this service** (this client sends `dedup_minutes`; old gateways ignore it and fall back to a multi-hour default). If the gateway is down, SMS sends fail with 502 and are logged, but task/theme runs still complete. Both sides need the same non-empty API token.

## Repository Map

- `autotask_api/main.py`: FastAPI entrypoint, startup and shutdown hooks, static asset mount
- `autotask_api/api/`: HTTP routers and response shaping
- `autotask_api/services/`: scheduler, task execution, theme execution, adapters, SMS gateway HTTP client
- `autotask_api/models.py`: SQLAlchemy models
- `autotask_api/schemas.py`: request and response schemas
- `autotask_api/api/contacts.py`: contact management API for SMS recipient configuration
- `frontend/assets/sections/contacts.js`: frontend UI for contact directory and manual contact editing
- `frontend/`: static frontend, no Node build step
- `manifest_templates/`: example manifests for uploaded script ZIP packages
- `tests/`: unittest-style tests that also run under `pytest`
- `DEPLOY.md`: offline Docker deployment notes

## Functional Modules

Key modules in active use include:

- Theme monitoring: source fetch, topic filtering, receiver resolution, deduplication, SMS enqueue, and run log persistence
- Custom script tasks: ZIP upload, manifest parsing, script execution, template rendering, receiver matching, and SMS sending
- Contact management for SMS recipients: `OrgContact` and `OrgContactPhone` data, `/api/contacts` CRUD, active/inactive status handling, mainland China mobile normalization, and frontend contact maintenance screens

## Local Development

Recommended local workflow:

- Install dependencies: `uv sync --index-url https://pypi.tuna.tsinghua.edu.cn/simple`
- Run the app: `uv run uvicorn autotask_api.main:app --host 0.0.0.0 --port 8000 --reload`
- Run tests: `pytest`
- Validate Docker config: `docker compose config`
- Build the image: `docker compose build`

Use Python 3.11 locally when possible. The README and `.env.example` assume that version.

## Environment and Runtime Constraints

- `autotask_api.database` creates the SQLAlchemy engine at import time. Set `DATABASE_URL` or the `KINGBASE_*` variables before importing modules that touch the database.
- Application startup calls `ensure_script_upload_dir()`, `init_db()`, and `scheduler_service.start()`. Avoid unintentionally starting the scheduler during tests.
- Default timezone is `Asia/Shanghai`. Preserve that unless the task explicitly changes scheduling behavior.
- The frontend is static and tightly coupled to current API shapes. Backend response changes can break the UI quickly.
- User-facing UI copy is currently Chinese. Do not rewrite existing product copy into English unless asked.
- Production usage is on company-internal Ubuntu 22.04 servers via Docker.
- The target runtime environment is offline. Do not assume outbound internet access for installs, downloads, API calls, or health checks.

## Testing Guidance

- Follow the existing test pattern when database-backed modules are imported: set `os.environ.setdefault("DATABASE_URL", "sqlite://")` before importing app code.
- Prefer focused tests using in-memory SQLite.
- If a test needs the configured schema name, mirror the current approach in `tests/test_theme_run_api.py` and attach an in-memory schema named `jcgkzx_autotask`.
- Do not require live Kingbase, Oracle, or SMS services for automated tests.
- After every code change, perform a functional verification of the changed logic. Use the closest realistic validation path available, such as a focused automated test, a syntax check, a dry run, a targeted API call, or a UI interaction check.

## Change Guidelines

- Keep routers thin in `autotask_api/api/`.
- Put orchestration and business logic in `autotask_api/services/`.
- Keep schema and transport changes in `autotask_api/schemas.py`.
- Preserve the uploaded ZIP contract: `manifest.json` plus a Python entrypoint compatible with `run(context) -> list[dict]`.
- Frontend edits should stay within plain HTML, CSS, and browser-side ES modules. There is no JS bundler in this repo.
- Treat the contact module as a core dependency of receiver matching and SMS delivery, not as an isolated admin-only feature.
- When changing contact logic, preserve these invariants unless the task explicitly changes them: imported contacts are read-only, active contacts must have at least one active phone, only one primary phone is allowed, and phone numbers must normalize to valid mainland China mobile numbers.
- If you change scheduler behavior, theme filtering, deduplication, receiver matching, or SMS send logic, update tests and call out the behavior change clearly.

## Done When

A task is done when all of the following are true:

- The requested behavior is implemented and the affected user flow works end to end.
- The change is consistent with the current deployment model: Docker on offline Ubuntu 22.04 in the company intranet.
- No existing startup, scheduling, database, contact-management, receiver-matching, or SMS-sending behavior is broken unintentionally.
- Tests were updated or added when behavior changed, and the relevant test command was run when feasible.
- The modified code path was functionally validated after the edit, not only reviewed statically.
- If tests could not be run because of environment constraints, that limitation is stated explicitly in the final handoff.
- Documentation or configuration examples were updated when the change altered operator-facing behavior, runtime assumptions, or integration requirements.

## Safety Notes

- Never hardcode or log secrets. Treat `.env` and `.env.example` values as environment-specific configuration, not values to duplicate into code.
- Be careful with startup and scheduler changes. Many regressions only appear at runtime after the app boots.
- Preserve offline deployment assumptions documented in `DEPLOY.md`.
- Keep deployment changes compatible with offline Docker delivery on Ubuntu 22.04.
- Prefer incremental changes over broad refactors unless the task explicitly asks for a structural rewrite.

## Good First Reads

Before making non-trivial changes, read these files first:

- `README.md`
- `autotask_api/main.py`
- the relevant module under `autotask_api/services/`
- the closest existing test under `tests/`
- If the code path involves `http://68.253.2.111` or `/dsjfx/` interfaces, read `dsjjqfx.md` first and use the matching endpoint section before writing or changing code.
