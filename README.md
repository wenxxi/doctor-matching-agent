# Doctor Matching Agent

Production-quality MVP foundation for a doctor matching application.

This scaffold includes:

- Next.js App Router frontend in `apps/web`
- FastAPI backend in `apps/api`
- PostgreSQL 16 with pgvector in `infra/docker-compose.yml`
- Basic health check endpoint
- Alembic migrations and a sample PostgreSQL doctor data layer
- CSV-backed MVP doctor recommendation endpoint with optional GPT-4o-mini concept extraction and explanation writing

No embeddings, chat history, authentication, scraping workflow, or direct GPT doctor search is implemented yet.

## Prerequisites

- Node.js 20+
- Python 3.11+
- uv
- Docker Desktop or Docker Engine with Docker Compose

### Install Docker Desktop

On macOS or Windows:

1. Download Docker Desktop from `https://www.docker.com/products/docker-desktop/`.
2. Install and launch Docker Desktop.
3. Wait until Docker reports that it is running.
4. Verify Docker Compose is available:

```bash
docker compose version
```

On Linux, install Docker Engine and the Docker Compose plugin from `https://docs.docker.com/engine/install/`.

### Install uv

Install uv with the official installer:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

Restart your terminal, or update your current shell path:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then verify:

```bash
uv --version
```

## Setup

Run all commands from the repository root unless noted.

### 1. Install frontend dependencies

```bash
cd apps/web
npm install
cd ../..
```

### 2. Install backend dependencies

```bash
cd apps/api
uv sync --python 3.11
cd ../..
```

From the repository root, create the backend environment file:

```bash
cp apps/api/.env.example apps/api/.env
```

### 3. Start PostgreSQL

```bash
docker compose -f infra/docker-compose.yml up -d
```

PostgreSQL runs on `localhost:5432` with:

- Database: `doctor_matching`
- User: `doctor_user`
- Password: `doctor_password`

These are local development credentials from `infra/docker-compose.yml`; do not reuse them in production.

The backend uses this SQLAlchemy URL from `apps/api/.env`:

```bash
DATABASE_URL=postgresql+psycopg://doctor_user:doctor_password@localhost:5432/doctor_matching
```

### 4. Run backend

```bash
cd apps/api
uv run uvicorn app.main:app --reload
```

### 5. Run migrations

```bash
cd apps/api
uv run alembic upgrade head
```

### 6. Import sample doctors into PostgreSQL

```bash
cd apps/api
uv run python scripts/import_doctors.py
```

The importer reads `data/sample_doctors.csv`, inserts sample doctors, splits `raw_expertise` into `doctor_expertise` rows, and is safe to run more than once.

This PostgreSQL dataset is demo/sample data for the `/api/doctors` endpoint. The recommendation endpoint uses the processed CSV files under `data/processed/` as its current source of doctor matching data.

### 7. Run frontend

```bash
cd apps/web
npm run dev
```

The frontend runs at `http://localhost:3000`.

Open `http://localhost:3000` in a browser to use the recommendation UI. Enter a symptom or health concern, for example:

```text
我膝蓋運動後疼痛，可能韌帶受傷
```

Submit the form to see matched concepts and recommended doctors. The frontend calls the backend at `http://localhost:8000` by default; change `NEXT_PUBLIC_API_BASE_URL` in `apps/web/.env.local` if your backend runs somewhere else.

### 8. Test the health endpoints

```bash
curl http://localhost:8000/health
```

Expected response:

```json
{"status":"ok"}
```

`/health` is an app-only health check and does not require PostgreSQL.

Test PostgreSQL connectivity:

```bash
curl http://localhost:8000/db/health
```

Expected response when PostgreSQL is reachable:

```json
{"status":"ok","database":"connected"}
```

If `DATABASE_URL` is missing or PostgreSQL is unavailable, the endpoint returns HTTP 503 with a JSON body explaining the issue.

### 9. Call the doctors endpoint

This endpoint reads from PostgreSQL.

List doctors:

```bash
curl "http://localhost:8000/api/doctors"
```

Filter by department:

```bash
curl "http://localhost:8000/api/doctors?department=Cardiology"
```

Filter by expertise keyword:

```bash
curl "http://localhost:8000/api/doctors?keyword=stroke"
```

Supported optional filters are `hospital`, `campus`, `department`, and `keyword`.

### 10. Test concept extraction

Use this endpoint to test concept extraction from a symptom query.

```bash
curl -X POST "http://localhost:8000/api/concepts/extract" \
  -H "Content-Type: application/json" \
  -d '{"query":"我跑步後膝蓋卡卡的，蹲下會痛"}'
```

The response includes matched medical concepts and basic diagnostic metadata.

### 11. Call the recommendation endpoint

The recommendation endpoint accepts a symptom query and returns matched concepts plus recommended doctors. If `OPENAI_API_KEY` is configured, the backend can use GPT-4o-mini for concept extraction and explanation writing. If OpenAI is not configured or a request fails, the app uses the local fallback path.

Current data source: this endpoint reads from `data/processed/doctors_normalized.csv`, `data/processed/medical_concepts.csv`, and `data/processed/doctor_concept_map.csv`. It does not read the PostgreSQL `doctors` table yet.

```bash
curl -X POST "http://localhost:8000/api/recommendations" \
  -H "Content-Type: application/json" \
  -d '{"query":"我膝蓋運動後疼痛，可能韌帶受傷","limit":3}'
```

The response is capped by `limit` and includes matched medical concepts, recommended doctors, reasons, and optional diagnostic metadata.

## Local Verification Checklist

Run these commands from the repository root after setup.

Check PostgreSQL:

```bash
docker compose -f infra/docker-compose.yml ps
docker compose -f infra/docker-compose.yml exec -T postgres pg_isready -U doctor_user -d doctor_matching
```

Check pgvector:

```bash
docker compose -f infra/docker-compose.yml exec -T postgres psql -U doctor_user -d doctor_matching -c "SELECT extname, extversion FROM pg_extension WHERE extname = 'vector';"
```

Check backend:

```bash
cd apps/api
uv run pytest
uv run alembic upgrade head
uv run python scripts/import_doctors.py
uv run uvicorn app.main:app --reload
```

In another terminal:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/db/health
curl "http://localhost:8000/api/doctors"
curl "http://localhost:8000/api/doctors?department=Cardiology"
curl "http://localhost:8000/api/doctors?keyword=stroke"
curl -X POST "http://localhost:8000/api/concepts/extract" -H "Content-Type: application/json" -d '{"query":"我跑步後膝蓋卡卡的，蹲下會痛"}'
curl -X POST "http://localhost:8000/api/recommendations" -H "Content-Type: application/json" -d '{"query":"我膝蓋運動後疼痛，可能韌帶受傷","limit":3}'
```

Check frontend:

```bash
cd apps/web
npm run dev
```

In another terminal:

```bash
curl -s -i http://localhost:3000 -o /tmp/doctor-matching-agent-web.html
grep "Doctor Matching Agent" /tmp/doctor-matching-agent-web.html
```

## Environment Files

Copy the example files before local development if you want local `.env` files:

```bash
cp apps/web/.env.example apps/web/.env.local
```

## Useful Commands

Stop PostgreSQL:

```bash
docker compose -f infra/docker-compose.yml down
```

Run backend tests:

```bash
cd apps/api
uv run pytest
```

Run database migrations:

```bash
cd apps/api
uv run alembic upgrade head
```

Import sample doctors:

```bash
cd apps/api
uv run python scripts/import_doctors.py
```
