# Doctor Matching Agent

Production-quality MVP foundation for a doctor matching application.

This scaffold includes:

- Next.js App Router frontend in `apps/web`
- FastAPI backend in `apps/api`
- PostgreSQL 16 with pgvector in `infra/docker-compose.yml`
- Basic health check endpoint
- Alembic migrations and a sample PostgreSQL doctor data layer
- CSV-backed MVP doctor recommendation endpoint with optional GPT-4o-mini concept extraction and explanation writing

No embeddings, authentication, persistent conversation storage, or direct GPT doctor search is implemented yet.

## Online Demo（Render）

- 網頁：[Doctor Matching Agent](https://doctor-matching-agent-web.onrender.com)
- API 文件：[Swagger UI](https://doctor-matching-agent-api.onrender.com/docs)
- API 健康檢查：[Health](https://doctor-matching-agent-api.onrender.com/health)

Render 免費後端閒置後首次請求可能需要較長時間啟動。部署設定與更新方式請見 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 對話追問與條件記憶

首頁以對話整理就醫需求，只追問尚未確認的症狀／科別、初複診、日期範圍與時段。條件完整後自動推薦醫師，並將相同條件帶入每張醫師卡片的掛號助理。

- 例如先說「膝蓋疼痛，想下週下午看診」，再回答「我是複診」；後續說「週三不行」時，保留原症狀、日期與下午偏好，只排除星期三。「改成上午」則只改時段。
- 支援明確的「日期不限」「時段不限」「不確定初複診」，不會反覆追問已確認的項目。要求其他醫院時會說明目前僅支援林口長庚，不直接套用錯誤院區。
- `POST /api/intake/chat` 接收 `message` 與上一輪回傳的 `state`，回傳更新後條件、下一個必要問題、快捷回答與 `ready`。相對日期以台北日期計算。
- 有 OpenAI 設定時使用結構化條件擷取，明確日期與星期編輯由本地程式校正；未設定或模型失敗時採本地解析。不明確或衝突的條件會要求澄清，不直接視為已接受。
- 對話與條件只存於目前網頁的記憶體，不使用 localStorage、sessionStorage 或後端對話資料庫。重新整理、點「清除對話與條件」或輸入「清除記憶」會重設；聊天內容可含健康資訊，有 API 設定時症狀與條件會送交模型解析，請勿在對話填入掛號證號、生日或驗證碼。
- 日期、時段與星期修改會清除舊的掛號候選，避免沿用舊條件。院方掛號處理期間暫停對話修改；僅改時段而症狀相同時沿用已取得的醫師推薦。

## 林口長庚掛號整合

推薦醫師卡片提供「掛號助理」：依日期範圍、星期、上午／下午／夜診與初複診條件查詢四週門診，選出最早符合的時段，重新讀取院方患者資料頁確認；候選頁面失效時最多改查三個時段，不會自行放寬條件。

使用者可在本站填寫證號、生日與院方驗證碼，明確同意後由後端維持獨立院方 Cookie 與表單權杖，先進行患者驗證，再送出掛號表單。院方若回傳可辨識的後續表單，會在本站要求使用者補充或再次確認。圖片驗證碼由使用者自行輸入，不會自動辨識或繞過。

- `GET /api/doctors/{doctor_id}/appointments` 使用推薦資料中的醫師 ID，不接受外部 URL。
- `POST /api/doctors/{doctor_id}/appointments/prepare` 接收 `patient_type`、`date_from`、`date_to`、`sessions` 與 `weekdays`（週一為 0），執行查詢、條件篩選、候選頁面驗證與改選。
- `POST /api/booking/sessions` 建立獨立的院方工作階段與驗證碼。`/api/booking/submit`、`/continue`、`/captcha` 以 `X-Booking-Token` 識別工作階段；`DELETE /api/booking/session` 清除本站暫存，不會取消院方掛號。
- 公開頁面快取約 2 分鐘，回傳資料取得時間；初診與科初診限制會保留顯示，時段不保證保留名額。
- 患者資料不傳給語言模型、不寫入本專案資料庫或檔案；院方 Cookie、表單資料與權杖只在單一 API 程序記憶體暫存，10 分鐘後自動清除。不得為掛號端點開啟 request-body 日誌或第三方表單追蹤。
- 掛號送出逾時會標示「結果無法確認」，不自動重試；後續確認步驟帶有一次性步驟權杖，避免重複送出。只有在院方成功訊息、所選醫師／日期／時段與掛號序號皆可辨識時才顯示成功。
- 目前以健保身分、到院看診送出。跨院病歷同意、附件、複雜動態表單或無法辨識的院方回覆會停止，提示使用者至院方查詢或完成作業。這是依公開網站表單串接的試用功能，並非院方正式 API；院方格式變動可能需要更新解析器。
- 自動測試使用模擬院方回覆；真實連線驗證僅涵蓋公開時段、表單及驗證碼取得，不會使用測試身分或代使用者建立真實掛號。完整成功流程仍須由使用者以本人的真實掛號需求驗證。

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
