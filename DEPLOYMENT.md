# Deployment

This project has two deployable services:

- `apps/api`: FastAPI backend for concept extraction and doctor recommendations.
- `apps/web`: static-exported Next.js frontend that calls the backend API.

The recommendation UI currently uses the processed CSV files under `data/processed`.
PostgreSQL is not required for the deployed recommendation UI unless you also want to use the database-backed doctor endpoints.

PostgreSQL **is required on Render for opt-in care-case memory and persistent LangGraph tasks**. Without it, the existing page-local conversation and recommendation flow stays available, but persistent cases remain disabled.

## Recommended Option: Render

Render is the simplest option for this repository because it can deploy both services from the same GitHub repo using `render.yaml`.

1. Push the latest code to GitHub.
2. In Render, create a new Blueprint from the GitHub repository.
3. Render will read `render.yaml` and create:
   - `doctor-matching-agent-api`
   - `doctor-matching-agent-web`
4. After deployment, open the web service URL:

```text
https://doctor-matching-agent-web.onrender.com
```

If Render gives either service a different URL, update these environment variables in Render:

- API service: `FRONTEND_ORIGINS`
- Web service: `NEXT_PUBLIC_API_BASE_URL`

## Updating the Existing Render Deployment

The existing services use the same GitHub repository:

- Website: https://doctor-matching-agent-web.onrender.com
- API: https://doctor-matching-agent-api.onrender.com
- Source: https://github.com/wenxxi/doctor-matching-agent

Push changes to `main`. If both services have **Auto-Deploy → On Commit** enabled and track `main`, Render rebuilds and deploys them automatically. Check each service's **Deploys** page for the deployed commit and result.

If automatic deployment is disabled, open each service in the [Render Dashboard](https://dashboard.render.com/) and select **Manual Deploy → Deploy latest commit**. Update both the API and website for the appointment integration.

After deployment, confirm:

1. The API `/health` returns `{"status":"ok"}`.
2. The API `/docs` includes `GET /api/doctors/{doctor_id}/appointments`.
3. A recommendation card shows the appointment assistant. Set preferences, let it select and verify a slot, then confirm that the on-site patient form receives a CGMH captcha. This read-only check does not submit a registration.

The booking workflow uses short-lived in-memory sessions. Run the API with **one worker and one instance**; a restart or deploy expires active sessions. Do not configure horizontal scaling until a shared expiring session store and distributed submission lock are implemented. Never enable request-body logging, form analytics, or tracing that captures patient fields or booking tokens. Booking responses use `Cache-Control: no-store`.

Real registration requires the user's own patient details, manual captcha entry, and explicit consent. Automated tests mock the hospital's responses; they do not prove a real registration was accepted. Cross-hospital record consent and unsupported hospital forms stop the flow. An unknown result after submission must be checked through the hospital's registration query before any retry.

## Enable Persistent Cases on Render

1. In [Render Dashboard](https://dashboard.render.com/), choose **New → Postgres**, or reuse an existing PostgreSQL instance. Choose the same region as `doctor-matching-agent-api`; select a plan appropriate for the desired retention and budget. This repository does not create a paid database automatically.
2. Once the database is available, open its **Connect** menu and copy the **Internal Database URL**. Keep the URL private; do not paste it into chat, GitHub, or the frontend environment.
3. Open **doctor-matching-agent-api → Environment → Add variable**. Add `AGENT_DATABASE_URL` with that internal URL as its value. Plain `postgresql://` and `postgres://` connection URLs are normalized to the Psycopg driver by the application.
4. Choose **Save and deploy**. Only the API needs this secret; do not add it to `doctor-matching-agent-web` or prefix it with `NEXT_PUBLIC_`.
5. Open `https://doctor-matching-agent-api.onrender.com/api/agent/status`. It should return `{"available":true,"storage":"postgresql"}`. The API lazily creates the four new application tables and LangGraph checkpoint tables on first access; the database role must have table-creation privileges.
6. Refresh the website, provide a case label and subject label, check the storage-consent box, and click **建立可追蹤個案**. Send a symptom query, reload the page, and verify that the conversation, preferences and task progress return. Create a second case to verify separation, then delete a test case to remove its messages, tasks and checkpoints.

The first four application tables are `agent_owners`, `care_cases`, `agent_tasks`, and `case_messages`. Migration `0002_add_care_cases_tasks` also declares these tables for Alembic-managed installations; it skips tables already bootstrapped. LangGraph manages its own checkpoint tables. If `AGENT_DATABASE_URL` and `DATABASE_URL` point to different databases, the existing Alembic command still targets `DATABASE_URL`; use the correct target when managing future schema changes.

Anonymous access tokens and the selected case ID are stored in this browser's localStorage; health content is stored in the backend database after consent. This is not a cross-device account system. Deleting browser storage does not delete database records and loses the access token; delete unwanted cases through the UI first. There is no scheduled retention cleanup yet.

The case workflow can resume at saved checkpoints, especially its explicit human-input pauses. The patient registration session remains short-lived and cannot be resumed after expiration or restart. In particular, graph recovery must never replay a registration POST. After an uncertain result, query the hospital before retrying.

### Local Verification

Use a dedicated SQLite file for local case testing even if the doctor's database is PostgreSQL. From `apps/api`:

```bash
uv sync
AGENT_DATABASE_URL=sqlite:////tmp/doctor-agent-memory.sqlite3 uv run uvicorn app.main:app --reload
```

SQLite is for local development only; a `/tmp` file is also temporary. For normal local persistence, choose a private durable path or omit both database URL variables to use ignored `var/agent-memory.sqlite3`. Do not commit database files or live connection strings. Start `apps/web` with `npm run dev`, then check the case creation, reload, separation, resolve/reopen and deletion flows. Tests use isolated SQLite files and do not submit real registrations.

Render connection and environment steps follow the [Render Postgres guide](https://render.com/docs/postgresql-creating-connecting) and [environment-variable guide](https://render.com/docs/configure-environment-variables).

## OpenAI-Generated Reasons

The app works without `OPENAI_API_KEY` by using keyword matching. In that mode, doctor cards show deterministic reasons such as `符合概念`.

To enable generated doctor descriptions, add this secret to the API service environment:

```text
OPENAI_API_KEY=your_api_key
```

Do not commit API keys to the repo.

After adding or changing this value in Render, redeploy the API service.
