# Doctor Matching Agent

Production-quality MVP foundation for a doctor matching application.

This scaffold includes:

- Next.js App Router frontend in `apps/web`
- FastAPI backend in `apps/api`
- PostgreSQL 16 with pgvector in `infra/docker-compose.yml`
- Basic health check endpoint
- Alembic migrations and a first doctor data layer

No doctor matching logic, OpenAI integration, scraping, or authentication is implemented yet.

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

### 6. Import sample doctors

```bash
cd apps/api
uv run python scripts/import_doctors.py
```

The importer reads `data/sample_doctors.csv`, inserts sample doctors, splits `raw_expertise` into `doctor_expertise` rows, and is safe to run more than once.

### 7. Run frontend

```bash
cd apps/web
npm run dev
```

The frontend runs at `http://localhost:3000`.

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
