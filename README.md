# Doctor Matching Agent

Production-quality MVP foundation for a doctor matching application.

This scaffold includes:

- Next.js App Router frontend in `apps/web`
- FastAPI backend in `apps/api`
- PostgreSQL 16 with pgvector in `infra/docker-compose.yml`
- Basic health check endpoint
- Alembic migrations and a sample PostgreSQL doctor data layer
- CSV-backed MVP doctor recommendation endpoint with optional GPT-4o-mini concept extraction and explanation writing

The app includes opt-in case memory and LangGraph task orchestration. Embeddings, account login, and direct GPT doctor search are not implemented yet.

## Online Demo（Render）

- 網頁：[Doctor Matching Agent](https://doctor-matching-agent-web.onrender.com)
- API 文件：[Swagger UI](https://doctor-matching-agent-api.onrender.com/docs)
- API 健康檢查：[Health](https://doctor-matching-agent-api.onrender.com/health)

Render 免費後端閒置後首次請求可能需要較長時間啟動。部署設定與更新方式請見 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 對話追問與條件記憶

首頁以對話整理就醫需求，只追問尚未確認的症狀／科別、初複診、日期範圍與時段。條件完整後自動推薦醫師，並將相同條件帶入每張醫師卡片的掛號助理。

網站右上角提供繁體中文／English 切換，以獨立的 `doctorAgentLanguage` 儲存語言偏好。切換只更新畫面，不重建個案、不變更掛號 enum 值，也不發出掛號請求；輸入中的資料會保留。介面、已知系統訊息、時段與科別名稱提供英文，醫療概念使用資料集中的英文名稱；醫師姓名、使用者對話原文與未有對照的院方欄位保留原文。英文快捷回覆具有本機解析對照；一般自由輸入沿用既有模型／本機解析流程。

- 例如先說「膝蓋疼痛，想下週下午看診」，再回答「我是複診」；後續說「週三不行」時，保留原症狀、日期與下午偏好，只排除星期三。「改成上午」則只改時段。
- 支援明確的「日期不限」「時段不限」「不確定初複診」，不會反覆追問已確認的項目。要求其他醫院時會說明目前僅支援林口長庚，不直接套用錯誤院區。
- `POST /api/intake/chat` 接收 `message` 與上一輪回傳的 `state`，回傳更新後條件、下一個必要問題、快捷回答與 `ready`。相對日期以台北日期計算。
- 有 OpenAI 設定時使用結構化條件擷取，明確日期與星期編輯由本地程式校正；未設定或模型失敗時採本地解析。不明確或衝突的條件會要求澄清，不直接視為已接受。
- 未建立個案時，對話與條件只存於目前網頁的記憶體，重新整理或清除對話會重設。勾選同意並建立可追蹤個案後，對話、條件與任務會保存到後端資料庫；localStorage 僅保存匿名存取憑證與選定個案 ID，不保存健康描述。有 API 設定時，症狀與條件仍會送交模型解析，請勿在對話填入掛號證號、生日或驗證碼。
- 日期、時段、星期與初複診修改後會重新查詢可掛號醫師，不會只因症狀相同就沿用舊推薦。院方掛號處理期間暫停對話修改。

## 個案、任務與 LangGraph

- 「我的就醫個案」可建立、切換、結案、重新開啟及刪除個案。不同對象／問題應建立不同個案，例如「自己／膝蓋疼痛」與「媽媽／眼睛問題」。目前由使用者選擇個案，不會自動合併健康問題。
- 新增 `agent_owners`、`care_cases`、`agent_tasks` 與 `case_messages` 四張資料表。匿名憑證只以 SHA-256 雜湊保存，所有個案 API 都檢查所屬者；這是同瀏覽器存取能力，不是跨裝置帳號登入。清除瀏覽器資料將失去憑證；要移除後端健康資料，請先刪除個案。
- LangGraph 在需求整理、醫師推薦與時段準備之間路由；缺少條件、等待選醫師、等待患者資料時使用 interrupt。每個任務以自己的 UUID 作為 thread_id，由持久 checkpoint 保存流程狀態。已完成回合與等待輸入的節點，可在程序重啟後接續。
- 使用 `AGENT_DATABASE_URL`，未設定時沿用 `DATABASE_URL`。本機兩者皆未設定才使用 `var/agent-memory.sqlite3`；Render 必須使用 PostgreSQL，不會退回容易遺失的本機檔案。首次啟用會建立四張新表及 LangGraph 管理的 checkpoint 表，不修改既有醫師資料。
- 同個案採版本檢查、操作 ID 去重與鎖定，避免不同分頁互相覆蓋。刪除個案同時清除訊息、任務與該任務的 LangGraph checkpoints；目前沒有排程自動刪除資料。
- 掛號證號、生日、驗證碼、院方 Cookie 與掛號 token 不寫入圖狀態／個案資料表。只回報已確認的結果、掛號序號與狀態。真正送出掛號仍在獨立、短期的掛號工作階段，不能因圖恢復而自動重播。
- 院方結果不明時會停止；先至官網查詢，確認未掛號後才可在對話輸入「已向院方確認未掛號，重新安排」。重新整理時不會自動重送已進入確認／送出流程的掛號。

### 資料關係

```mermaid
erDiagram
    AGENT_OWNERS ||--o{ CARE_CASES : owns
    CARE_CASES ||--o{ AGENT_TASKS : tracks
    CARE_CASES ||--o{ CASE_MESSAGES : contains
    AGENT_TASKS ||--o{ CASE_MESSAGES : records
    AGENT_TASKS ||..o{ LANGGRAPH_CHECKPOINTS : "logical thread_id"
```

### Agent 流程

```mermaid
flowchart TD
    A[選擇個案並驗證存取憑證] --> B[載入個案條件與任務 checkpoint]
    B --> C[LangGraph：整理需求]
    C --> D{條件完整？}
    D -->|否| E[interrupt：等待補充]
    E -->|新訊息| C
    D -->|是| F[既有醫師推薦服務]
    F --> G[interrupt：等待選醫師]
    G -->|修改條件| C
    G -->|選定醫師| H[既有時段查詢與頁面確認服務]
    H --> I{找到時段？}
    I -->|否| G
    I -->|是| J[interrupt：等待患者資料]
    J --> K[獨立短期掛號表單：人工輸入驗證碼並確認]
    K --> L{院方結果}
    L -->|確認成功| M[記錄序號並完成任務]
    L -->|不明或特殊流程| N[停止操作，交由使用者確認]
    C -.狀態保存.-> DB[(個案資料庫與 checkpoints)]
    H -.狀態保存.-> DB
    M -.結果保存.-> DB
    N -.進度保存.-> DB
```

Render PostgreSQL 設定與本機測試方式見 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 林口長庚掛號整合

推薦醫師卡片提供「掛號助理」：依日期範圍、星期、上午／下午／夜診與初複診條件查詢四週門診，選出最早符合的時段，重新讀取院方患者資料頁確認；候選頁面失效時最多改查三個時段，不會自行放寬條件。

顯示卡片前會先檢查最多 12 位相關候選醫師，以每批 3 位查詢；僅保留至少一個符合條件且患者資料頁已確認的醫師，最多顯示 3 位。額滿、資格不符、沒有符合時段或無法確認的醫師會排除，並由後續相關候選遞補。卡片附已確認時段與確認時間；確認不代表保留名額，安排及送出時仍會重新驗證。院方暫時無法連線時不會顯示未驗證醫師冒充可掛號。

使用者可在本站填寫證號、生日與院方驗證碼，明確同意後由後端維持獨立院方 Cookie 與表單權杖，先進行患者驗證，再送出掛號表單。院方若回傳可辨識的後續表單，會在本站要求使用者補充或再次確認。圖片驗證碼由使用者自行輸入，不會自動辨識或繞過。

- `GET /api/doctors/{doctor_id}/appointments` 使用推薦資料中的醫師 ID，不接受外部 URL。
- `POST /api/recommendations` 接受 `preferences`（日期、星期、時段、初複診）；未提供時只檢查一般資格時段。`POST /api/doctors/{doctor_id}/appointments/search` 依同一條件篩選其他候選時段，選取時再確認患者資料頁。舊個案中尚未有時段驗證的推薦不會顯示卡片，可輸入「維持目前條件」重新查詢。
- `POST /api/doctors/{doctor_id}/appointments/prepare` 接收 `patient_type`、`date_from`、`date_to`、`sessions` 與 `weekdays`（週一為 0），執行查詢、條件篩選、候選頁面驗證與改選。
- `POST /api/booking/sessions` 建立獨立的院方工作階段與驗證碼。`/api/booking/submit`、`/continue`、`/captcha` 以 `X-Booking-Token` 識別工作階段；`DELETE /api/booking/session` 清除本站暫存，不會取消院方掛號。
- 公開頁面快取約 2 分鐘，回傳資料取得時間；初診與科初診限制會保留顯示，時段不保證保留名額。
- 掛號證號、生日與驗證碼不傳給語言模型、不寫入本專案資料庫或檔案；院方 Cookie、掛號表單資料與權杖只在單一 API 程序記憶體暫存，10 分鐘後自動清除。已同意儲存的個案對話與症狀描述則保存於個案資料庫。不得為掛號端點開啟 request-body 日誌或第三方表單追蹤。
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
